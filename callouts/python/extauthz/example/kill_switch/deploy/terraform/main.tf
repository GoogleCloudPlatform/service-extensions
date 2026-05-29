# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.15.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {
  project_id = var.project_id
}

# ===================================================================
# ENABLE REQUIRED APIS
# ===================================================================
resource "google_project_service" "apis" {
  for_each = toset([
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# SERVICE ACCOUNT
# ===================================================================
#
# Use the project's default compute SA. Override via var.kill_switch_service_account
# for tighter scoping. The kill-switch needs roles/iap.egressor revocation, but
# the broader projectIamAdmin role is intentionally NOT granted here — scope a
# narrower role at the resource level once the exact revocation surface is known.
locals {
  kill_switch_service_account = coalesce(
    var.kill_switch_service_account,
    "${data.google_project.project.number}-compute@developer.gserviceaccount.com",
  )
}

# ===================================================================
# NETWORK
# ===================================================================
resource "google_compute_network" "kill_switch_vpc" {
  name                    = "agent-gateway-vpc"
  auto_create_subnetworks = true
  depends_on              = [google_project_service.apis]
}

# ===================================================================
# STATE STORE (REDIS)
# ===================================================================
resource "google_redis_instance" "state_store" {
  name               = "agent-blocked-state-store"
  memory_size_gb     = 1
  region             = var.region
  tier               = "BASIC"
  authorized_network = google_compute_network.kill_switch_vpc.id
  depends_on         = [google_project_service.apis]
}

# ===================================================================
# CLOUD RUN — gRPC EXT_AUTHZ
# ===================================================================
resource "google_cloud_run_v2_service" "authz_service" {
  name                = "kill-switch-ext-authz"
  location            = var.region
  deletion_protection = false

  template {
    service_account = local.kill_switch_service_account

    containers {
      image = var.kill_switch_image

      ports {
        name           = "h2c"
        container_port = 8080
      }

      env {
        name  = "STATE_STORE_TYPE"
        value = "redis"
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.state_store.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.state_store.port)
      }
    }

    # Direct VPC Egress configuration for Redis access
    vpc_access {
      network_interfaces {
        network = google_compute_network.kill_switch_vpc.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }
  }

  depends_on = [google_project_service.apis]
}

# ===================================================================
# CLOUD RUN — HTTP WEBHOOKS
# ===================================================================
resource "google_cloud_run_v2_service" "webhook_service" {
  name                = "kill-switch-webhooks"
  location            = var.region
  deletion_protection = false

  template {
    service_account = local.kill_switch_service_account

    containers {
      image = var.kill_switch_image

      command = ["python3", "-u", "-m", "extauthz.example.kill_switch.run_webhooks"]

      ports {
        container_port = 8080
      }
      env {
        name  = "STATE_STORE_TYPE"
        value = "redis"
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.state_store.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.state_store.port)
      }

      # ---------------------------------------------------------
      # KILL SWITCH POLICY CONFIGURATION
      # ---------------------------------------------------------
      env {
        name  = "DRY_RUN"
        value = var.dry_run
      }
      env {
        name  = "EXEMPT_AGENTS"
        value = var.exempt_agents
      }
      env {
        name  = "SCC_THRESHOLD"
        value = var.scc_threshold
      }
      env {
        name  = "WIZ_THRESHOLD"
        value = var.wiz_threshold
      }
      env {
        name  = "VERTEX_THRESHOLD"
        value = var.vertex_threshold
      }

      # ---------------------------------------------------------
      # VERTEX AI ANOMALY DETECTION CONFIGURATION
      # ---------------------------------------------------------
      env {
        name  = "ENABLE_VERTEX_POLLING"
        value = var.enable_vertex_polling
      }
      env {
        name  = "VERTEX_ENDPOINT_ID"
        value = var.vertex_endpoint_id
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }

    # Direct VPC Egress configuration for Redis access
    vpc_access {
      network_interfaces {
        network = google_compute_network.kill_switch_vpc.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }
  }

  depends_on = [google_project_service.apis]
}

# Allow the compute SA (used by Pub/Sub push and Cloud Scheduler OIDC tokens)
# to invoke the webhook service.
resource "google_cloud_run_v2_service_iam_member" "webhook_invoker" {
  name     = google_cloud_run_v2_service.webhook_service.name
  location = google_cloud_run_v2_service.webhook_service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.kill_switch_service_account}"
}

# ===================================================================
# INGESTION TRIGGERS (PUB/SUB & SCHEDULER)
# ===================================================================
resource "google_pubsub_topic" "scc_alerts" {
  name       = "scc-agent-alerts"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "scc_webhook_push" {
  name  = "scc-webhook-push-sub"
  topic = google_pubsub_topic.scc_alerts.name

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.webhook_service.uri}/webhook/scc"
    oidc_token {
      service_account_email = local.kill_switch_service_account
    }
  }
}

resource "google_cloud_scheduler_job" "vertex_anomaly_poller" {
  name             = "vertex-anomaly-detection-poller"
  description      = "Triggers the Vertex AI anomaly detection polling endpoint"
  schedule         = "*/5 * * * *"
  attempt_deadline = "30s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.webhook_service.uri}/poll/anomaly-detection"
    oidc_token {
      service_account_email = local.kill_switch_service_account
    }
  }

  depends_on = [google_project_service.apis]
}
