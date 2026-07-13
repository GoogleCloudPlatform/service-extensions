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
    "compute.googleapis.com",
    "iam.googleapis.com",
    "networkservices.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
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
# GCS: RULES BUCKET (CONFIG_SOURCE=gcs)
# ===================================================================

resource "google_storage_bucket" "rules" {
  count                       = var.config_source == "gcs" ? 1 : 0
  name                        = "${var.project_id}-prompt-amender-rules"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning {
    enabled = true # lets you roll back a bad rules.yaml by restoring a prior generation
  }
  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_object" "initial_rules" {
  count  = var.config_source == "gcs" ? 1 : 0
  name   = "rules.yaml"
  bucket = google_storage_bucket.rules[0].name
  source = "${path.module}/../../rules.example.yaml"
}

resource "google_storage_bucket_iam_member" "callout_rules_viewer" {
  count  = var.config_source == "gcs" ? 1 : 0
  bucket = google_storage_bucket.rules[0].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# CLOUD RUN: CALLOUT (Python ext_proc service)
# ===================================================================

resource "google_cloud_run_v2_service" "callout" {
  name                = "prompt-amender-callout"
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
      env {
        name  = "FAIL_OPEN"
        value = var.fail_open ? "true" : "false"
      }
      env {
        name  = "CONFIG_SOURCE"
        value = var.config_source
      }
      env {
        name  = "GCS_RULES_URI"
        value = var.config_source == "gcs" ? "gs://${google_storage_bucket.rules[0].name}/rules.yaml" : ""
      }
      env {
        name  = "GIT_REPO_URL"
        value = var.git_repo_url
      }
      env {
        name  = "GIT_BRANCH"
        value = var.git_branch
      }
      env {
        name  = "POLL_INTERVAL_SECONDS"
        value = tostring(var.poll_interval_seconds)
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      startup_probe {
        http_get {
          path = "/"
          port = 80
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 3
      }
      liveness_probe {
        http_get {
          path = "/"
          port = 80
        }
        period_seconds = 10
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket_object.initial_rules,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "callout_public_invoker" {
  name     = google_cloud_run_v2_service.callout.name
  location = google_cloud_run_v2_service.callout.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "prompt-amender-callout-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout.name
  }
}

resource "google_compute_backend_service" "callout_backend" {
  name                  = "prompt-amender-callout-be"
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
# BACKEND: VERTEX AI
# ===================================================================

resource "google_compute_global_network_endpoint_group" "vertex_neg" {
  name                  = "prompt-amender-vertex-neg"
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
  name                  = "prompt-amender-vertex-be"
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
  name = "prompt-amender-lb-ip"
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "prompt-amender.example.com"
  }
  validity_period_hours = 8760
  allowed_uses          = ["server_auth"]
}

resource "google_compute_ssl_certificate" "lb_cert" {
  name        = "prompt-amender-cert"
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

resource "google_compute_url_map" "url_map" {
  name            = "prompt-amender-url-map"
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
  name             = "prompt-amender-https-proxy"
  url_map          = google_compute_url_map.url_map.id
  ssl_certificates = [google_compute_ssl_certificate.lb_cert.id]
}

resource "google_compute_global_forwarding_rule" "forwarding_rule" {
  name                  = "prompt-amender-fwd-rule"
  port_range            = "443"
  target                = google_compute_target_https_proxy.https_proxy.id
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ===================================================================
# SERVICE EXTENSIONS: TRAFFIC EXTENSION
# ===================================================================
#
# REQUEST_HEADERS + REQUEST_BODY: the callout decides per-request, via
# mode_override on the header-phase response, whether it actually needs the
# body (only when a rule matched). Unmatched traffic still incurs one
# header-phase round trip but never pays body-buffering cost.

resource "google_network_services_lb_traffic_extension" "callout" {
  name                  = "prompt-amender-traffic-ext"
  location              = "global"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_global_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "prompt-amender-chain"
    match_condition {
      cel_expression = "request.path.endsWith(':generateContent')"
    }
    extensions {
      name             = "prompt-amender-callout"
      service          = google_compute_backend_service.callout_backend.self_link
      authority        = "prompt-amender.example.com"
      supported_events = ["REQUEST_HEADERS", "REQUEST_BODY"]
      timeout          = "10s"
    }
  }
  depends_on = [google_project_service.apis]
}

# ===================================================================
# OUTPUTS
# ===================================================================

output "load_balancer_ip" {
  description = "The external IP address of the load balancer."
  value       = google_compute_global_address.lb_ip.address
}

output "callout_service_url" {
  description = "The URL of the Python ext_proc callout Cloud Run service."
  value       = google_cloud_run_v2_service.callout.uri
}

output "rules_bucket" {
  description = "The GCS bucket holding rules.yaml (only set when config_source = gcs)."
  value       = var.config_source == "gcs" ? google_storage_bucket.rules[0].name : null
}
