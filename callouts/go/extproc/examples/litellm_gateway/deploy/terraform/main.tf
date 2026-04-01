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
    "compute.googleapis.com",
    "iam.googleapis.com",
    "networkservices.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# NETWORKING — VPC + SUBNETS FOR REGIONAL EXTERNAL LOAD BALANCER
# ===================================================================

resource "google_compute_network" "vpc" {
  name                    = "litellm-gateway-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "main" {
  name          = "litellm-gateway-main-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# Required for regional external managed load balancers.
resource "google_compute_subnetwork" "proxy_only" {
  name          = "litellm-gateway-proxy-subnet"
  ip_cidr_range = "10.0.2.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

# ===================================================================
# SECRET MANAGER — GEMINI API KEY
# ===================================================================

resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "litellm-gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

# Grant the Cloud Run service account access to the secret.
resource "google_secret_manager_secret_iam_member" "gemini_key_accessor" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# ===================================================================
# CLOUD RUN — LITELLM GATEWAY CALLOUT (Go ext_proc + LiteLLM sidecar)
# ===================================================================

resource "google_cloud_run_v2_service" "litellm_gateway" {
  name                = "litellm-gateway-callout"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    # Go ext_proc callout — the ingress container.
    containers {
      name  = "callout"
      image = var.callout_image
      ports {
        name           = "h2c"
        container_port = 8080
      }
      env {
        name  = "EXAMPLE_TYPE"
        value = "litellm_gateway"
      }
      env {
        name  = "LITELLM_BASE_URL"
        value = "http://localhost:4000"
      }
      env {
        name  = "ENABLE_CORS"
        value = var.enable_cors ? "true" : "false"
      }
      env {
        name  = "SEC_KEYWORDS"
        value = var.sec_keywords
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

    # LiteLLM proxy sidecar — routes to Gemini/OpenAI/etc.
    containers {
      name  = "litellm"
      image = var.litellm_image
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
      startup_probe {
        http_get {
          path = "/health/liveliness"
          port = 4000
        }
        initial_delay_seconds = 15
        period_seconds        = 10
        failure_threshold     = 6
      }
      liveness_probe {
        http_get {
          path = "/health/liveliness"
          port = 4000
        }
        period_seconds = 30
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.gemini_api_key,
    google_secret_manager_secret_iam_member.gemini_key_accessor,
  ]
}

# Allow the load balancer to invoke the Cloud Run service.
resource "google_cloud_run_v2_service_iam_member" "callout_public_invoker" {
  name     = google_cloud_run_v2_service.litellm_gateway.name
  location = google_cloud_run_v2_service.litellm_gateway.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Serverless NEG to connect Cloud Run to the load balancer.
resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "litellm-gateway-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.litellm_gateway.name
  }
}

# Backend service for the callout — used by Service Extensions.
resource "google_compute_region_backend_service" "callout_backend" {
  name                  = "litellm-gateway-callout-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  backend {
    group           = google_compute_region_network_endpoint_group.callout_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# CLOUD RUN — UPSTREAM APPLICATION (receives non-LLM traffic)
# ===================================================================

resource "google_cloud_run_v2_service" "upstream_app" {
  name                = "litellm-gateway-upstream"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.upstream_app_image
      ports {
        container_port = 8080
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "upstream_public_invoker" {
  name     = google_cloud_run_v2_service.upstream_app.name
  location = google_cloud_run_v2_service.upstream_app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "upstream_neg" {
  name                  = "litellm-gateway-upstream-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.upstream_app.name
  }
}

resource "google_compute_region_backend_service" "upstream_backend" {
  name                  = "litellm-gateway-upstream-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group           = google_compute_region_network_endpoint_group.upstream_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# LOAD BALANCER — REGIONAL EXTERNAL HTTPS
# ===================================================================

resource "google_compute_address" "lb_ip" {
  name         = "litellm-gateway-lb-ip"
  region       = var.region
  address_type = "EXTERNAL"
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "litellm-gateway.example.com"
  }
  validity_period_hours = 8760 # 1 year
  allowed_uses          = ["server_auth"]
}

resource "google_compute_region_ssl_certificate" "lb_cert" {
  name        = "litellm-gateway-cert"
  region      = var.region
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

resource "google_compute_region_url_map" "url_map" {
  name            = "litellm-gateway-url-map"
  region          = var.region
  default_service = google_compute_region_backend_service.upstream_backend.id
}

resource "google_compute_region_target_https_proxy" "https_proxy" {
  name             = "litellm-gateway-https-proxy"
  region           = var.region
  url_map          = google_compute_region_url_map.url_map.id
  ssl_certificates = [google_compute_region_ssl_certificate.lb_cert.id]
}

resource "google_compute_forwarding_rule" "forwarding_rule" {
  name                  = "litellm-gateway-fwd-rule"
  region                = var.region
  port_range            = "443"
  target                = google_compute_region_target_https_proxy.https_proxy.id
  ip_address            = google_compute_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  network               = google_compute_network.vpc.id

  depends_on = [google_compute_subnetwork.proxy_only]
}

# ===================================================================
# SERVICE EXTENSIONS — TRAFFIC EXTENSION FOR LLM ROUTING
# ===================================================================

resource "google_network_services_lb_traffic_extension" "litellm_gateway" {
  name                  = "litellm-gateway-traffic-ext"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "litellm-gateway-chain"
    match_condition {
      cel_expression = "request.path in ['/v1/chat/completions', '/v1/completions', '/v1/embeddings', '/v1/models', '/chat/completions', '/completions', '/embeddings']"
    }
    extensions {
      name             = "litellm-gateway-callout"
      service          = google_compute_region_backend_service.callout_backend.self_link
      authority        = "litellm-gateway.example.com"
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
  value       = google_compute_address.lb_ip.address
}

output "callout_service_url" {
  description = "The URL of the LiteLLM Gateway callout Cloud Run service."
  value       = google_cloud_run_v2_service.litellm_gateway.uri
}

output "upstream_service_url" {
  description = "The URL of the upstream application Cloud Run service."
  value       = google_cloud_run_v2_service.upstream_app.uri
}

output "curl_test_command" {
  description = "Example curl command to test the LiteLLM gateway through the load balancer."
  value       = <<-EOT
    curl -sk -X POST https://${google_compute_address.lb_ip.address}/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model": "gemini", "messages": [{"role": "user", "content": "Hello"}]}'
  EOT
}
