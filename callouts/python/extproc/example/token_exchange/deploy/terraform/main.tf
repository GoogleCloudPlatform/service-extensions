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
    "iamcredentials.googleapis.com",
    "networkservices.googleapis.com",
    "run.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# SERVICE ACCOUNT: CALLOUT
# ===================================================================
#
# INBOUND mode mints Google Cloud access tokens via STS/WIF and (optionally)
# impersonates var.target_service_account, so this identity needs
# roles/iam.serviceAccountTokenCreator on that target SA. By default the
# project's default compute SA is used; for tighter scoping set
# var.callout_service_account.

locals {
  callout_service_account = coalesce(
    var.callout_service_account,
    "${data.google_project.project.number}-compute@developer.gserviceaccount.com",
  )
  backend_host = var.mode == "INBOUND" ? "${var.region}-aiplatform.googleapis.com" : var.outbound_target_host
}

# ===================================================================
# CLOUD RUN: CALLOUT (Python ext_proc service)
# ===================================================================

resource "google_cloud_run_v2_service" "callout" {
  name                = "token-exchange-callout"
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
        name  = "TOKEN_EXCHANGE_MODE"
        value = var.mode
      }
      env {
        name  = "FAIL_OPEN"
        value = var.fail_open ? "true" : "false"
      }
      env {
        name  = "WIF_AUDIENCE"
        value = var.wif_audience
      }
      env {
        name  = "TARGET_SERVICE_ACCOUNT"
        value = var.target_service_account
      }
      env {
        name  = "EXTERNAL_TOKEN_ENDPOINT"
        value = var.external_token_endpoint
      }
      env {
        name  = "EXTERNAL_CLIENT_ID"
        value = var.external_client_id
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

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "callout_public_invoker" {
  name     = google_cloud_run_v2_service.callout.name
  location = google_cloud_run_v2_service.callout.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_service_account_iam_member" "callout_impersonates_target" {
  count              = var.mode == "INBOUND" && var.target_service_account != "" ? 1 : 0
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.target_service_account}"
  role                = "roles/iam.serviceAccountTokenCreator"
  member              = "serviceAccount:${local.callout_service_account}"
}

resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "token-exchange-callout-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout.name
  }
}

resource "google_compute_backend_service" "callout_backend" {
  name                  = "token-exchange-callout-be"
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
# BACKEND: DESTINATION (Vertex AI for INBOUND, 3rd-party API for OUTBOUND)
# ===================================================================

resource "google_compute_global_network_endpoint_group" "destination_neg" {
  name                  = "token-exchange-destination-neg"
  network_endpoint_type = "INTERNET_FQDN_PORT"
  default_port          = 443
  depends_on            = [google_project_service.apis]
}

resource "google_compute_global_network_endpoint" "destination_endpoint" {
  global_network_endpoint_group = google_compute_global_network_endpoint_group.destination_neg.name
  fqdn                          = local.backend_host
  port                          = 443
}

resource "google_compute_backend_service" "destination_backend" {
  name                  = "token-exchange-destination-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  timeout_sec           = 180
  backend {
    group           = google_compute_global_network_endpoint_group.destination_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
  depends_on = [google_compute_global_network_endpoint.destination_endpoint]
}

# ===================================================================
# LOAD BALANCER: GLOBAL EXTERNAL APPLICATION LB
# ===================================================================

resource "google_compute_global_address" "lb_ip" {
  name = "token-exchange-lb-ip"
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "token-exchange.example.com"
  }
  validity_period_hours = 8760
  allowed_uses          = ["server_auth"]
}

resource "google_compute_ssl_certificate" "lb_cert" {
  name        = "token-exchange-cert"
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

resource "google_compute_url_map" "url_map" {
  name            = "token-exchange-url-map"
  default_service = google_compute_backend_service.destination_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "default"
  }

  path_matcher {
    name            = "default"
    default_service = google_compute_backend_service.destination_backend.id

    route_rules {
      priority = 1
      match_rules {
        prefix_match = "/"
      }
      service = google_compute_backend_service.destination_backend.id
      route_action {
        url_rewrite {
          host_rewrite = local.backend_host
        }
      }
    }
  }
}

resource "google_compute_target_https_proxy" "https_proxy" {
  name             = "token-exchange-https-proxy"
  url_map          = google_compute_url_map.url_map.id
  ssl_certificates = [google_compute_ssl_certificate.lb_cert.id]
}

resource "google_compute_global_forwarding_rule" "forwarding_rule" {
  name                  = "token-exchange-fwd-rule"
  port_range            = "443"
  target                = google_compute_target_https_proxy.https_proxy.id
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ===================================================================
# SERVICE EXTENSIONS: TRAFFIC EXTENSION
# ===================================================================
#
# The callout only handles REQUEST_HEADERS -- it swaps the Authorization
# header's token and never touches the body. No clear_route_cache: the URL
# map already picked the destination backend before this extension runs.

resource "google_network_services_lb_traffic_extension" "callout" {
  name                  = "token-exchange-traffic-ext"
  location              = "global"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_global_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "token-exchange-chain"
    match_condition {
      cel_expression = "true"
    }
    extensions {
      name             = "token-exchange-callout"
      service          = google_compute_backend_service.callout_backend.self_link
      authority        = "token-exchange.example.com"
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
  description = "The external IP address of the load balancer."
  value       = google_compute_global_address.lb_ip.address
}

output "callout_service_url" {
  description = "The URL of the Python ext_proc callout Cloud Run service."
  value       = google_cloud_run_v2_service.callout.uri
}

output "destination_host" {
  description = "The FQDN this deployment forwards exchanged-credential traffic to."
  value       = local.backend_host
}
