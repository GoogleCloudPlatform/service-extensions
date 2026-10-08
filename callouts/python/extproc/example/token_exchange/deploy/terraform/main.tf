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
      version = ">= 7.7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# CORE LOGIC: EXT_PROC SERVICE (CLOUD RUN)
# -----------------------------------------------------------------------------

# Dedicated identity for the callout server, so that access to the client
# secret is granted to this service only.
resource "google_service_account" "ext_proc" {
  account_id   = "token-exchange-ext-proc"
  display_name = "Token exchange callout server"
}

# The OAuth client secret is read from Secret Manager at container start. The
# secret is created outside of Terraform (see the README), so its value is
# never written to the Terraform state or to the Cloud Run configuration.
resource "google_secret_manager_secret_iam_member" "ext_proc_secret_access" {
  count     = var.outbound_client_secret_id != "" ? 1 : 0
  secret_id = var.outbound_client_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ext_proc.email}"
}

resource "google_cloud_run_v2_service" "ext_proc_service" {
  name     = "token-exchange-ext-proc"
  location = var.region
  # The backend trusts the headers that the callout server sets, so a client
  # able to reach either service directly could forge them. Only the load
  # balancer may call the services, and the default run.app URI is switched
  # off, so there is no address to reach them on besides the load balancer.
  ingress              = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default_uri_disabled = true
  # Lets `terraform destroy` remove the example.
  deletion_protection = false

  template {
    service_account = google_service_account.ext_proc.email

    containers {
      image = var.image_uri
      ports {
        container_port = 8080
        name           = "h2c"
      }
      env {
        name  = "TOKEN_EXCHANGE_FAIL_CLOSED"
        value = tostring(var.fail_closed)
      }
      env {
        name  = "TOKEN_EXCHANGE_MODE"
        value = var.token_exchange_mode
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
      env {
        name  = "OUTBOUND_TOKEN_URL"
        value = var.outbound_token_url
      }
      env {
        name  = "OUTBOUND_CLIENT_ID"
        value = var.outbound_client_id
      }
      dynamic "env" {
        for_each = var.outbound_client_secret_id != "" ? [1] : []
        content {
          name = "OUTBOUND_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = var.outbound_client_secret_id
              version = var.outbound_client_secret_version
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.ext_proc_secret_access]
}

resource "google_compute_region_network_endpoint_group" "ext_proc_neg" {
  name                  = "token-exchange-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.ext_proc_service.name
  }
}

resource "google_compute_backend_service" "ext_proc_backend" {
  name                  = "token-exchange-backend"
  protocol              = "HTTP2"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.ext_proc_neg.id
  }
}

# -----------------------------------------------------------------------------
# NETWORK SECURITY: SERVICE EXTENSIONS LINK TO AUTOMATIC LOAD BALANCER
# -----------------------------------------------------------------------------

resource "google_network_services_lb_traffic_extension" "token_exchange_ext" {
  name     = "token-exchange-traffic-ext"
  location = "global"

  load_balancing_scheme = "EXTERNAL_MANAGED"

  forwarding_rules = [google_compute_global_forwarding_rule.verification_forwarding_rule.id]

  extension_chains {
    name = "token-exchange-chain"

    match_condition {
      cel_expression = "request.path.startsWith('/')"
    }

    extensions {
      name      = "ext-proc-authz"
      authority = "ext-proc-authz.google.com"
      service   = google_compute_backend_service.ext_proc_backend.self_link
      timeout   = "10s"
      # Whether requests are let through when the callout server itself is
      # unreachable or times out.
      fail_open        = !var.fail_closed
      supported_events = ["REQUEST_HEADERS"]
    }
  }
}

# -----------------------------------------------------------------------------
# TEST INFRASTRUCTURE: ECHO BACKEND & GLOBAL APPLICATION LOAD BALANCER
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "echo_backend" {
  name                 = "token-exchange-echo-backend"
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default_uri_disabled = true
  deletion_protection  = false
  template {
    containers {
      image = "mccutchen/go-httpbin:2.23.1"
      ports {
        container_port = 8080
      }
    }
  }
}

resource "google_compute_region_network_endpoint_group" "echo_neg" {
  name                  = "token-exchange-echo-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.echo_backend.name
  }
}

resource "google_compute_backend_service" "verification_backend" {
  name                  = "token-exchange-verification-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.echo_neg.id
  }
}

resource "google_compute_global_address" "lb_ip" {
  name = "token-exchange-verification-ip"
}

resource "google_compute_url_map" "verification_url_map" {
  name            = "token-exchange-verification-url-map"
  default_service = google_compute_backend_service.verification_backend.id
}

resource "google_compute_target_http_proxy" "verification_http_proxy" {
  name    = "token-exchange-verification-http-proxy"
  url_map = google_compute_url_map.verification_url_map.id
}

resource "google_compute_global_forwarding_rule" "verification_forwarding_rule" {
  name                  = "token-exchange-verification-forwarding-rule"
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.verification_http_proxy.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# -----------------------------------------------------------------------------
# IAM POLICIES: CLOUD RUN INVOKER ACCESS
# -----------------------------------------------------------------------------
#
# Service Extensions calls the callout server without an identity token, so
# there is no principal for IAM to match and the invoker role cannot be scoped
# more narrowly. The callouts documentation requires it: a Cloud Run callout
# backend "must allow unauthenticated access". Without this binding every
# request fails, because Cloud Run rejects the unauthenticated callout.
#
# Network controls restrict access instead. Both services only accept traffic
# from load balancers (INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER) and have
# their default run.app URI disabled, so there is no public path to them.
#
# For real-world usage, review whether unauthenticated invocation is allowed
# by your organization policy, and keep these network restrictions in place.

resource "google_cloud_run_v2_service_iam_member" "ext_proc_public" {
  project  = google_cloud_run_v2_service.ext_proc_service.project
  location = google_cloud_run_v2_service.ext_proc_service.location
  name     = google_cloud_run_v2_service.ext_proc_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "echo_public" {
  project  = google_cloud_run_v2_service.echo_backend.project
  location = google_cloud_run_v2_service.echo_backend.location
  name     = google_cloud_run_v2_service.echo_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "load_balancer_ip" {
  value       = google_compute_global_address.lb_ip.address
  description = "The public IP address of the verification load balancer."
}
