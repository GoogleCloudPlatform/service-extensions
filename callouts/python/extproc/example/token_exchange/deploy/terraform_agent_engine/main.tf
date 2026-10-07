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
  required_version = ">= 1.3"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
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

# ------------------------------------------------------------------------------
# 1. ENVOY PROXY-ONLY SUBNET (Required for Regional External ALB)
# ------------------------------------------------------------------------------
resource "google_compute_subnetwork" "proxy_subnet" {
  name          = "agent-gateway-proxy-subnet"
  ip_cidr_range = var.proxy_subnet_cidr
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
  region        = var.region
  network       = var.network
}

# ------------------------------------------------------------------------------
# 2. EXT_PROC SERVICE (Cloud Run Service Extension)
# ------------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "ext_proc" {
  name                 = "agent-identity-gateway-proc"
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default_uri_disabled = true
  deletion_protection  = false

  template {
    containers {
      image = var.ext_proc_image_uri
      ports {
        container_port = 8080
        name           = "h2c"
      }
      env {
        name  = "TOKEN_EXCHANGE_MODE"
        value = "INBOUND"
      }
      env {
        name  = "TOKEN_EXCHANGE_FAIL_CLOSED"
        value = tostring(var.fail_closed)
      }
      env {
        name  = "WIF_POOL_ID"
        value = var.wif_pool_id
      }
      env {
        name  = "WIF_PROVIDER_ID"
        value = var.wif_provider_id
      }
      env {
        name  = "WIF_PROJECT_NUMBER"
        value = var.project_number
      }
    }
  }
}

# NOTE: Granting `roles/run.invoker` to `allUsers` is used here for sample
# simplicity. For production environments, scope invocation according to your
# organization's security policy.
resource "google_cloud_run_v2_service_iam_member" "ext_proc_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.ext_proc.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "ext_proc_neg" {
  name                  = "agent-gateway-ext-proc-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.ext_proc.name
  }
}

resource "google_compute_region_backend_service" "ext_proc_backend" {
  name                  = "agent-gateway-ext-proc-backend"
  region                = var.region
  protocol              = "HTTP2"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.ext_proc_neg.id
    capacity_scaler = 1.0
  }
}

# ------------------------------------------------------------------------------
# 3. PRIVATE SERVICE CONNECT (PSC) NEG TO AGENT ENGINE
# ------------------------------------------------------------------------------
resource "google_compute_region_network_endpoint_group" "agent_engine_psc_neg" {
  name                  = "agent-engine-psc-neg"
  region                = var.region
  network_endpoint_type = "PRIVATE_SERVICE_CONNECT"
  psc_target_service    = "${var.region}-aiplatform.googleapis.com"
}

resource "google_compute_region_backend_service" "agent_engine_backend" {
  name                  = "agent-engine-backend-service"
  region                = var.region
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group           = google_compute_region_network_endpoint_group.agent_engine_psc_neg.id
    capacity_scaler = 1.0
  }
}

# ------------------------------------------------------------------------------
# 4. REGIONAL EXTERNAL HTTPS LOAD BALANCER
# ------------------------------------------------------------------------------

# Generate in-memory self-signed certificate for sandbox testing if no external cert is provided
resource "tls_private_key" "gateway_key" {
  count     = var.ssl_certificate_id == null ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "tls_self_signed_cert" "gateway_cert" {
  count           = var.ssl_certificate_id == null ? 1 : 0
  private_key_pem = tls_private_key.gateway_key[0].private_key_pem

  subject {
    common_name  = "agent-gateway"
    organization = "Google Cloud Service Extensions"
  }

  validity_period_hours = 8760

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "google_compute_region_ssl_certificate" "gateway_ssl" {
  count       = var.ssl_certificate_id == null ? 1 : 0
  name        = "agent-gateway-ssl-cert"
  region      = var.region
  private_key = tls_private_key.gateway_key[0].private_key_pem
  certificate = tls_self_signed_cert.gateway_cert[0].cert_pem

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_region_url_map" "gateway_url_map" {
  name            = "agent-gateway-url-map"
  region          = var.region
  default_service = google_compute_region_backend_service.agent_engine_backend.id
}

resource "google_compute_region_target_https_proxy" "gateway_https_proxy" {
  name    = "agent-gateway-https-proxy"
  region  = var.region
  url_map = google_compute_region_url_map.gateway_url_map.id
  ssl_certificates = [
    var.ssl_certificate_id != null ? var.ssl_certificate_id : google_compute_region_ssl_certificate.gateway_ssl[0].id
  ]
}

resource "google_compute_forwarding_rule" "gateway_forwarding_rule" {
  name                  = "agent-gateway-forwarding-rule"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  network               = var.network
  network_tier          = "PREMIUM"
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_region_target_https_proxy.gateway_https_proxy.id
  depends_on            = [google_compute_subnetwork.proxy_subnet]
}

# ------------------------------------------------------------------------------
# 5. SERVICE EXTENSION ATTACHMENT
# ------------------------------------------------------------------------------
resource "google_network_services_lb_traffic_extension" "gateway_extension" {
  name                  = "agent-token-exchange-extension"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules      = [google_compute_forwarding_rule.gateway_forwarding_rule.id]

  extension_chains {
    name = "agent-token-swap-chain"
    match_condition {
      cel_expression = "request.path.startsWith('/')"
    }
    extensions {
      name             = "ext-proc-authz"
      authority        = "ext-proc-authz.google.com"
      service          = google_compute_region_backend_service.ext_proc_backend.self_link
      timeout          = "5s"
      fail_open        = !var.fail_closed
      supported_events = ["REQUEST_HEADERS"]
    }
  }
}

output "gateway_ip" {
  value       = google_compute_forwarding_rule.gateway_forwarding_rule.ip_address
  description = "The regional external HTTPS load balancer IP address for the Agent Engine gateway."
}

