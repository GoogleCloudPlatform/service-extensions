# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.15.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0.0"
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
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "networkservices.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

locals {
  callout_service_account = coalesce(
    var.callout_service_account,
    "${data.google_project.project.number}-compute@developer.gserviceaccount.com",
  )
}

# ===================================================================
# FIRESTORE: BLOCKED STATE STORE
# ===================================================================

resource "google_firestore_database" "default" {
  count       = var.create_firestore_database ? 1 : 0
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

resource "google_project_iam_member" "callout_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${local.callout_service_account}"
}

resource "google_project_iam_member" "callout_iam_admin" {
  # Scoped narrowly in production; this sample grants project-level IAM
  # admin so the Actuator can patch roles/iap.egressor bindings on
  # arbitrary registered MCP resources.
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# CLOUD RUN: CALLOUT (gRPC ext_proc, hot path)
# ===================================================================

resource "google_cloud_run_v2_service" "callout" {
  name                = "agent-breakglass-callout"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = local.callout_service_account
    containers {
      name  = "callout"
      image = var.callout_image
      ports {
        name           = "h2c"
        container_port = 8080
      }
      env { name = "GCP_PROJECT_ID" value = var.project_id }
      env { name = "FAIL_OPEN" value = var.fail_open ? "true" : "false" }
      env { name = "DRY_RUN" value = var.dry_run ? "true" : "false" }
      env { name = "EXEMPT_AGENTS" value = join(",", var.exempt_agents) }
      env { name = "MIN_SEVERITY_VERTEX_ANOMALY" value = tostring(var.min_severity_vertex_anomaly) }
      env { name = "MIN_SEVERITY_SCC" value = tostring(var.min_severity_scc) }
      env { name = "MIN_SEVERITY_WIZ" value = tostring(var.min_severity_wiz) }
      env { name = "FIRESTORE_COLLECTION" value = var.firestore_collection }
      env { name = "STATE_CACHE_TTL_SECONDS" value = tostring(var.state_cache_ttl_seconds) }
      env { name = "MCP_RESOURCE_LIST" value = join(",", var.mcp_resource_list) }
      env { name = "WIZ_WEBHOOK_SHARED_SECRET" value = var.wiz_webhook_shared_secret }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      startup_probe {
        http_get { path = "/" port = 80 }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 3
      }
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.default,
    google_project_iam_member.callout_firestore_user,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "callout_public_invoker" {
  name     = google_cloud_run_v2_service.callout.name
  location = google_cloud_run_v2_service.callout.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "agent-breakglass-callout-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout.name
  }
}

resource "google_compute_backend_service" "callout_backend" {
  name                  = "agent-breakglass-callout-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  backend {
    group = google_compute_region_network_endpoint_group.callout_neg.id
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ===================================================================
# CLOUD RUN: INGESTION (same image, HTTP webhooks + poll endpoint)
# ===================================================================
#
# Same container image and entrypoint as the callout service above -- the
# process always starts both listeners (gRPC on 8080, FastAPI ingestion on
# 8090). This second Cloud Run service just exposes the ingestion port
# publicly for SCC/Wiz webhooks and the Cloud Scheduler poll trigger,
# without routing LB traffic through it.

resource "google_cloud_run_v2_service" "ingestion" {
  name                = "agent-breakglass-ingestion"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = local.callout_service_account
    containers {
      name  = "ingestion"
      image = var.callout_image
      ports {
        container_port = 8090
      }
      env { name = "GCP_PROJECT_ID" value = var.project_id }
      env { name = "DRY_RUN" value = var.dry_run ? "true" : "false" }
      env { name = "EXEMPT_AGENTS" value = join(",", var.exempt_agents) }
      env { name = "MIN_SEVERITY_VERTEX_ANOMALY" value = tostring(var.min_severity_vertex_anomaly) }
      env { name = "MIN_SEVERITY_SCC" value = tostring(var.min_severity_scc) }
      env { name = "MIN_SEVERITY_WIZ" value = tostring(var.min_severity_wiz) }
      env { name = "FIRESTORE_COLLECTION" value = var.firestore_collection }
      env { name = "MCP_RESOURCE_LIST" value = join(",", var.mcp_resource_list) }
      env { name = "VERTEX_ANOMALY_POLL_ENDPOINT" value = var.vertex_anomaly_poll_endpoint }
      env { name = "WIZ_WEBHOOK_SHARED_SECRET" value = var.wiz_webhook_shared_secret }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
  }

  depends_on = [google_project_service.apis, google_firestore_database.default]
}

resource "google_cloud_run_v2_service_iam_member" "ingestion_invoker" {
  name     = google_cloud_run_v2_service.ingestion.name
  location = google_cloud_run_v2_service.ingestion.location
  role     = "roles/run.invoker"
  member   = var.ingestion_allow_unauthenticated ? "allUsers" : "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# PUB/SUB: SCC PUSH SUBSCRIPTION
# ===================================================================

resource "google_pubsub_topic" "scc_findings" {
  name       = "agent-breakglass-scc-findings"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "scc_push" {
  name  = "agent-breakglass-scc-push"
  topic = google_pubsub_topic.scc_findings.name
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.ingestion.uri}/webhook/scc"
    oidc_token {
      service_account_email = local.callout_service_account
    }
  }
}

# ===================================================================
# CLOUD SCHEDULER: VERTEX ANOMALY DETECTION POLL
# ===================================================================

resource "google_cloud_scheduler_job" "anomaly_poll" {
  count       = var.vertex_anomaly_poll_endpoint != "" ? 1 : 0
  name        = "agent-breakglass-anomaly-poll"
  schedule    = var.anomaly_poll_schedule
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.ingestion.uri}/poll/anomaly-detection"
    oidc_token {
      service_account_email = local.callout_service_account
    }
  }
  depends_on = [google_project_service.apis]
}

# ===================================================================
# BACKEND: VERTEX AI (demo destination the authorization extension guards)
# ===================================================================

resource "google_compute_global_network_endpoint_group" "vertex_neg" {
  name                  = "agent-breakglass-vertex-neg"
  network_endpoint_type = "INTERNET_FQDN_PORT"
  default_port          = 443
  depends_on            = [google_project_service.apis]
}

resource "google_compute_global_network_endpoint" "vertex_endpoint" {
  global_network_endpoint_group = google_compute_global_network_endpoint_group.vertex_neg.name
  fqdn                          = "${var.region}-aiplatform.googleapis.com"
  port                          = 443
}

resource "google_compute_backend_service" "vertex_backend" {
  name                  = "agent-breakglass-vertex-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  timeout_sec           = 180
  backend {
    group           = google_compute_global_network_endpoint_group.vertex_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
  depends_on = [google_compute_global_network_endpoint.vertex_endpoint]
}

# ===================================================================
# LOAD BALANCER: GLOBAL EXTERNAL APPLICATION LB
# ===================================================================

resource "google_compute_global_address" "lb_ip" {
  name = "agent-breakglass-lb-ip"
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "agent-breakglass.example.com"
  }
  validity_period_hours = 8760
  allowed_uses          = ["server_auth"]
}

resource "google_compute_ssl_certificate" "lb_cert" {
  name        = "agent-breakglass-cert"
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

resource "google_compute_url_map" "url_map" {
  name            = "agent-breakglass-url-map"
  default_service = google_compute_backend_service.vertex_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "default"
  }

  path_matcher {
    name            = "default"
    default_service = google_compute_backend_service.vertex_backend.id

    route_rules {
      priority = 1
      match_rules {
        prefix_match = "/"
      }
      service = google_compute_backend_service.vertex_backend.id
      route_action {
        url_rewrite {
          host_rewrite = "${var.region}-aiplatform.googleapis.com"
        }
      }
    }
  }
}

resource "google_compute_target_https_proxy" "https_proxy" {
  name             = "agent-breakglass-https-proxy"
  url_map          = google_compute_url_map.url_map.id
  ssl_certificates = [google_compute_ssl_certificate.lb_cert.id]
}

resource "google_compute_global_forwarding_rule" "forwarding_rule" {
  name                  = "agent-breakglass-fwd-rule"
  port_range            = "443"
  target                = google_compute_target_https_proxy.https_proxy.id
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ===================================================================
# SERVICE EXTENSIONS: TRAFFIC EXTENSION (authorization role)
# ===================================================================
#
# REQUEST_HEADERS only: the callout answers ALLOW/DENY from the Blocked
# State Store lookup alone and never touches the body.

resource "google_network_services_lb_traffic_extension" "callout" {
  name                  = "agent-breakglass-traffic-ext"
  location              = "global"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_global_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "agent-breakglass-chain"
    match_condition {
      cel_expression = "true"
    }
    extensions {
      name             = "agent-breakglass-callout"
      service          = google_compute_backend_service.callout_backend.self_link
      authority        = "agent-breakglass.example.com"
      supported_events = ["REQUEST_HEADERS"]
      timeout          = "10s"
    }
  }
  depends_on = [google_project_service.apis]
}

# ===================================================================
# OUTPUTS
# ===================================================================

output "load_balancer_ip" {
  value = google_compute_global_address.lb_ip.address
}

output "callout_service_url" {
  value = google_cloud_run_v2_service.callout.uri
}

output "ingestion_service_url" {
  description = "Base URL for /webhook/scc, /webhook/wiz, /poll/anomaly-detection."
  value       = google_cloud_run_v2_service.ingestion.uri
}

output "scc_pubsub_topic" {
  description = "Point Security Command Center's notification config at this topic."
  value       = google_pubsub_topic.scc_findings.id
}
