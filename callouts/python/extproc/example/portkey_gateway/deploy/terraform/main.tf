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
    "secretmanager.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# SERVICE ACCOUNT: CALLOUT
# ===================================================================
#
# The callout uses ADC (via the Cloud Run service identity) to mint Vertex AI
# bearer tokens. The SA therefore needs roles/aiplatform.user.
#
# By default the project's default compute SA is used (has roles/editor).
# For tighter scoping set var.callout_service_account.

locals {
  callout_service_account = coalesce(
    var.callout_service_account,
    "${data.google_project.project.number}-compute@developer.gserviceaccount.com",
  )

  api_keys_all = {
    anthropic  = var.anthropic_api_key
    groq       = var.groq_api_key
    openrouter = var.openrouter_api_key
  }
  active_providers = nonsensitive(toset([
    for k, v in local.api_keys_all : k if v != ""
  ]))

  # Each provider here gets an Internet NEG + backend on the LB. The URL
  # map matches `prefix=/v1/` + `x-model-id` prefix `<provider>/` to pick the
  # right backend. Vertex AI is below as a separate resource.
  third_party_providers = {
    anthropic  = "api.anthropic.com"
    groq       = "api.groq.com"
    openrouter = "openrouter.ai"
  }
}

# ===================================================================
# SECRET MANAGER: PROVIDER API KEYS
# ===================================================================

resource "google_secret_manager_secret" "api_keys" {
  for_each  = local.active_providers
  secret_id = "portkey-gateway-${each.key}-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "api_keys" {
  for_each    = local.active_providers
  secret      = google_secret_manager_secret.api_keys[each.key].id
  secret_data = local.api_keys_all[each.key]
}

resource "google_secret_manager_secret_iam_member" "callout_accessor" {
  for_each  = local.active_providers
  secret_id = google_secret_manager_secret.api_keys[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# CLOUD RUN: CALLOUT (Python ext_proc service)
# Multi-container: callout (ingress) + Portkey gateway sidecar
# ===================================================================

resource "google_cloud_run_v2_service" "callout" {
  name                = "portkey-gateway-callout"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = local.callout_service_account

    # Ingress container: the Python ext_proc callout. Must be listed first.
    containers {
      name  = "callout"
      image = var.callout_image
      ports {
        name           = "h2c"
        container_port = 8080
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "PORTKEY_BASE_URL"
        value = "http://127.0.0.1:8787"
      }
      dynamic "env" {
        for_each = local.active_providers
        content {
          name = "${upper(env.key)}_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.api_keys[env.key].secret_id
              version = "latest"
            }
          }
        }
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

    # Sidecar container: Portkey gateway. Reachable only via localhost from
    # the callout container. No `ports` block: only the ingress container
    # declares ports in Cloud Run v2 multi-container.
    containers {
      name  = "portkey-sidecar"
      image = var.portkey_image
      # Sidecar is reachable only via localhost from the callout container.
      # Do not declare a `ports` block. Only the ingress container declares ports.
      env {
        name  = "PORT"
        value = "8787"
      }
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.api_keys,
    google_secret_manager_secret_iam_member.callout_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "callout_public_invoker" {
  name     = google_cloud_run_v2_service.callout.name
  location = google_cloud_run_v2_service.callout.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "portkey-gateway-callout-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout.name
  }
}

resource "google_compute_backend_service" "callout_backend" {
  name                  = "portkey-gateway-callout-be"
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
# CLOUD RUN: UPSTREAM APPLICATION (non-LLM traffic, e.g., chat UI)
# ===================================================================

resource "google_cloud_run_v2_service" "upstream_app" {
  name                = "portkey-gateway-upstream"
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
  name                  = "portkey-gateway-upstream-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.upstream_app.name
  }
}

resource "google_compute_backend_service" "upstream_backend" {
  name                  = "portkey-gateway-upstream-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group = google_compute_region_network_endpoint_group.upstream_neg.id
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ===================================================================
# VERTEX AI BACKEND: GLOBAL INTERNET NEG
# ===================================================================

resource "google_compute_global_network_endpoint_group" "vertex_neg" {
  name                  = "portkey-gateway-vertex-neg"
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
  name                  = "portkey-gateway-vertex-be"
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
# THIRD-PARTY PROVIDER BACKENDS: GLOBAL INTERNET NEGs
# ===================================================================

resource "google_compute_global_network_endpoint_group" "provider_neg" {
  for_each              = local.third_party_providers
  name                  = "portkey-gateway-${each.key}-neg"
  network_endpoint_type = "INTERNET_FQDN_PORT"
  default_port          = 443
  depends_on            = [google_project_service.apis]
}

resource "google_compute_global_network_endpoint" "provider_endpoint" {
  for_each                      = local.third_party_providers
  global_network_endpoint_group = google_compute_global_network_endpoint_group.provider_neg[each.key].name
  fqdn                          = each.value
  port                          = 443
}

resource "google_compute_backend_service" "provider_backend" {
  for_each              = local.third_party_providers
  name                  = "portkey-gateway-${each.key}-be"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  timeout_sec           = 180
  backend {
    group           = google_compute_global_network_endpoint_group.provider_neg[each.key].id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
  depends_on = [google_compute_global_network_endpoint.provider_endpoint]
}

# ===================================================================
# LOAD BALANCER: GLOBAL EXTERNAL APPLICATION LB
# ===================================================================

resource "google_compute_global_address" "lb_ip" {
  name = "portkey-gateway-lb-ip"
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "portkey-gateway.example.com"
  }
  validity_period_hours = 8760
  allowed_uses          = ["server_auth"]
}

resource "google_compute_ssl_certificate" "lb_cert" {
  name        = "portkey-gateway-cert"
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

# URL map: model-id prefix routing. The URL map picks the provider backend
# by matching the client-supplied `x-model-id` header against the provider
# prefix (the first segment of the model id, e.g. `anthropic/` for
# `anthropic/claude-3-5-sonnet-...`). The Traffic Extension reads the body,
# transforms OpenAI to the provider format, and rewrites `:path` for the
# upstream call. It does NOT influence routing (Traffic Extensions can't
# switch backends post-decision).
#
# So the rules are:
#   /v1/* + x-model-id prefix `anthropic/`   -> Anthropic backend
#   /v1/* + x-model-id prefix `groq/`        -> Groq backend
#   /v1/* + x-model-id prefix `openrouter/`  -> OpenRouter backend
#   /v1/*                                    -> Vertex AI backend (default)
#   anything else                            -> upstream sample UI
resource "google_compute_url_map" "url_map" {
  name            = "portkey-gateway-url-map"
  default_service = google_compute_backend_service.upstream_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "llm"
  }

  path_matcher {
    name            = "llm"
    default_service = google_compute_backend_service.upstream_backend.id

    route_rules {
      priority = 1
      match_rules {
        prefix_match = "/v1/"
        header_matches {
          header_name  = "x-model-id"
          prefix_match = "anthropic/"
        }
      }
      service = google_compute_backend_service.provider_backend["anthropic"].id
      route_action {
        url_rewrite {
          host_rewrite = "api.anthropic.com"
        }
      }
    }

    route_rules {
      priority = 2
      match_rules {
        prefix_match = "/v1/"
        header_matches {
          header_name  = "x-model-id"
          prefix_match = "groq/"
        }
      }
      service = google_compute_backend_service.provider_backend["groq"].id
      route_action {
        url_rewrite {
          host_rewrite = "api.groq.com"
        }
      }
    }

    route_rules {
      priority = 3
      match_rules {
        prefix_match = "/v1/"
        header_matches {
          header_name  = "x-model-id"
          prefix_match = "openrouter/"
        }
      }
      service = google_compute_backend_service.provider_backend["openrouter"].id
      route_action {
        url_rewrite {
          host_rewrite = "openrouter.ai"
        }
      }
    }

    # Fallback for /v1/* with no matching x-model-id prefix: Vertex AI.
    route_rules {
      priority = 4
      match_rules {
        prefix_match = "/v1/"
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
  name             = "portkey-gateway-https-proxy"
  url_map          = google_compute_url_map.url_map.id
  ssl_certificates = [google_compute_ssl_certificate.lb_cert.id]
}

resource "google_compute_global_forwarding_rule" "forwarding_rule" {
  name                  = "portkey-gateway-fwd-rule"
  port_range            = "443"
  target                = google_compute_target_https_proxy.https_proxy.id
  ip_address            = google_compute_global_address.lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ===================================================================
# SERVICE EXTENSIONS: TRAFFIC EXTENSION
# ===================================================================
#
# Traffic Extension on Global LB. The callout sees REQUEST_BODY and does:
#   1. Body transform OpenAI → provider format (via Portkey gateway sidecar)
#   2. :path rewrite to the provider-specific path
#   3. Auth header injection (Authorization for Vertex via ADC, x-api-key
#      for Anthropic, etc.), all via the Portkey gateway.
#
# It does NOT influence routing. Routing was decided by the URL map based on
# the client's x-model-id header (prefix match on the provider segment).

resource "google_network_services_lb_traffic_extension" "callout" {
  name                  = "portkey-gateway-traffic-ext"
  location              = "global"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_global_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "portkey-gateway-chain"
    match_condition {
      cel_expression = "request.path in ['/v1/chat/completions', '/v1/completions', '/v1/embeddings']"
    }
    extensions {
      name             = "portkey-gateway-callout"
      service          = google_compute_backend_service.callout_backend.self_link
      authority        = "portkey-gateway.example.com"
      supported_events = ["REQUEST_HEADERS", "REQUEST_BODY", "RESPONSE_HEADERS", "RESPONSE_BODY"]
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

output "upstream_service_url" {
  description = "The URL of the upstream application Cloud Run service."
  value       = google_cloud_run_v2_service.upstream_app.uri
}

output "vertex_endpoint" {
  description = "The Vertex AI FQDN this deployment forwards LLM requests to."
  value       = "${var.region}-aiplatform.googleapis.com"
}

output "curl_test_command" {
  description = "Example curl command to test the Portkey gateway through the load balancer."
  value       = <<-EOT
    # Vertex AI (no header needed, default backend)
    curl -sk -X POST https://${google_compute_global_address.lb_ip.address}/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model": "vertex_ai/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hello"}]}'

    # Anthropic / Groq / OpenRouter: set x-model-id to the full model id.
    # The URL map matches on the provider prefix (e.g. `anthropic/`).
    curl -sk -X POST https://${google_compute_global_address.lb_ip.address}/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "x-model-id: anthropic/claude-haiku-4-5" \
      -d '{"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "Hello"}]}'
  EOT
}
