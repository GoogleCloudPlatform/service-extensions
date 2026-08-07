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
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# VPC AND SUBNET (Direct VPC egress for Cloud Run + Memorystore)
# ===================================================================

resource "google_compute_network" "vpc" {
  name                    = "litellm-gateway-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "litellm-gateway-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# Regional external Application LBs (EXTERNAL_MANAGED) route through managed
# Envoy proxies, which require a proxy-only subnet (REGIONAL_MANAGED_PROXY)
# in the LB's region/VPC.
resource "google_compute_subnetwork" "proxy" {
  name          = "litellm-gateway-proxy-subnet"
  ip_cidr_range = "10.20.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

# Cloud NAT gives the managed Envoy proxies (and Cloud Run) outbound internet
# access so Internet NEG backends can reach external provider APIs
# (api.anthropic.com, api.groq.com, openrouter.ai). Even though the LB itself
# is external (EXTERNAL_MANAGED), its managed Envoy proxies still run inside
# the VPC and their egress to Internet NEG backends follows VPC routes, so
# NAT is what makes external provider fan-out work here.
resource "google_compute_router" "router" {
  name    = "litellm-gateway-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name   = "litellm-gateway-nat"
  router = google_compute_router.router.name
  region = var.region
  # ENDPOINT_TYPE_MANAGED_PROXY_LB NATs the regional LB's managed Envoy
  # proxies, giving the regional Internet NEG backends internet egress to
  # reach external provider APIs. A default (VM) NAT does not cover the
  # managed proxies.
  endpoint_types                     = ["ENDPOINT_TYPE_MANAGED_PROXY_LB"]
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ===================================================================
# MEMORYSTORE FOR REDIS (quota backend)
# ===================================================================
#
# The callout uses this instance for token-budget and rate-limit enforcement.
# The callout reads REDIS_HOST and REDIS_PORT from env vars set below.
#
# The instance has a private IP, so keys are seeded from inside the VPC. There
# are two ways, and both use seed_keys.py:
#   1. Terraform (no VPC access needed): define keys in the quota_keys
#      variable and run the litellm-gateway-seed-keys Cloud Run Job created
#      below. See the seed_job_command output.
#   2. By hand, from a machine with VPC access (a VM or Cloud Shell in this
#      network), for ad hoc changes:
#        cp keys.example.yaml keys.yaml
#        export REDIS_AUTH_STRING=<instance auth_string>   # auth is on
#        export REDIS_TLS=true
#        python seed_keys.py --host <redis-host> --file keys.yaml
# Key fields include token_budget, budget_duration (seconds), rpm_limit,
# tpm_limit, models, model_max_budget, expires, and soft_budget; see the
# README's "Seeding quota keys" section for the full field table.

resource "google_redis_instance" "quota" {
  name               = "litellm-gateway-quota"
  tier               = var.redis_tier
  memory_size_gb     = 1
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  # The instance holds spend counters and key config, so it takes a
  # generated AUTH string and TLS on the wire rather than relying on
  # VPC reachability alone. The callout and the seed job both read
  # the string from Secret Manager.
  auth_enabled            = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"
  depends_on              = [google_project_service.apis]
}
# The Memorystore AUTH string, kept in Secret Manager rather than inlined
# into the Cloud Run spec, so reading the service definition does not reveal
# the credential.
resource "google_secret_manager_secret" "redis_auth" {
  secret_id = "litellm-gateway-redis-auth"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "redis_auth" {
  secret      = google_secret_manager_secret.redis_auth.id
  secret_data = google_redis_instance.quota.auth_string
}

resource "google_secret_manager_secret_iam_member" "redis_auth_accessor" {
  secret_id = google_secret_manager_secret.redis_auth.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.callout_service_account}"
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

  # The OpenAI-compatible paths this gateway serves, including the aliases
  # served without the /v1 prefix.
  #
  # Both extensions must match on this same list. They are two hops on one
  # request, so a path matched by only one of them gets half the gateway:
  # a path the traffic extension matches but the route extension does not
  # is still served, but silently without model routing. Deriving both
  # conditions from one local keeps them from drifting apart.
  gateway_paths = [
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
    "/chat/completions",
    "/completions",
    "/embeddings",
  ]
  gateway_paths_cel = "request.path in ['${join("', '", local.gateway_paths)}']"

  # URL map matching only; both extension CELs keep the exact list above.
  # The versioned namespace is matched by prefix, so a /v1 endpoint added
  # to LLM_ENDPOINTS routes even before it is listed here. The unversioned
  # aliases share no prefix, so each is matched in full: that is the gap
  # the route extension exposed. An unimplemented /v1 path reaches a
  # provider and gets its 404 rather than the sample app's.
  gateway_prefix = "/v1/"
  gateway_matchers = concat(
    [{ prefix = local.gateway_prefix, full = null }],
    [for p in local.gateway_paths :
    { prefix = null, full = p } if !startswith(p, local.gateway_prefix)],
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
  # map matches the gateway paths + x-model-id header with a provider prefix
  # (e.g. anthropic/...) to pick the right backend. Vertex AI is below
  # as a separate resource.
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
  secret_id = "litellm-gateway-${each.key}-api-key"
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
# SECRET MANAGER: GATEWAY CONFIG (mounted into the callout)
# ===================================================================
#
# var.gateway_config rendered as the YAML the callout reads from
# GATEWAY_CONFIG. This is where the routing feature flag lives: routing
# strategies are active only when router_settings gives them a non-empty
# table. An empty config (the default) leaves the callout as the plain
# translation gateway.

resource "google_secret_manager_secret" "gateway_config" {
  secret_id = "litellm-gateway-config"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gateway_config" {
  secret      = google_secret_manager_secret.gateway_config.id
  secret_data = yamlencode(var.gateway_config)
}

resource "google_secret_manager_secret_iam_member" "gateway_config_accessor" {
  secret_id = google_secret_manager_secret.gateway_config.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# SECRET MANAGER: QUOTA KEYS (input to the seed-keys job)
# ===================================================================
#
# var.quota_keys rendered as the YAML seed_keys.py expects, so the keys live
# in terraform.tfvars and there is no separate file to keep in sync. Mounted
# into the seed-keys job below, never into the callout (the callout reads key
# config from Redis, not from this secret).

resource "google_secret_manager_secret" "quota_keys" {
  secret_id = "litellm-gateway-quota-keys"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "quota_keys" {
  secret      = google_secret_manager_secret.quota_keys.id
  secret_data = yamlencode({ keys = var.quota_keys })
}

resource "google_secret_manager_secret_iam_member" "quota_keys_accessor" {
  secret_id = google_secret_manager_secret.quota_keys.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.callout_service_account}"
}

# ===================================================================
# CLOUD RUN JOB: SEED QUOTA KEYS
# ===================================================================
#
# Memorystore has a private IP, so seeding needs to run inside the VPC. This
# job reuses the callout image (it already ships seed_keys.py plus the redis
# and yaml libraries) with Direct VPC egress. Run it after apply, and any time
# you change quota_keys:
#   gcloud run jobs execute litellm-gateway-seed-keys --region <region>
# --replace rewrites each key hash, so removing a field from quota_keys also
# removes it from Redis.

resource "google_cloud_run_v2_job" "seed_keys" {
  name                = "litellm-gateway-seed-keys"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = local.callout_service_account
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.subnet.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image   = var.callout_image
        command = ["python3"]
        args = [
          "extproc/example/litellm_gateway/seed_keys.py",
          "--host", google_redis_instance.quota.host,
          "--port", tostring(google_redis_instance.quota.port),
          "--file", "/etc/keys/keys.yaml",
          "--replace",
        ]
        env {
          name = "REDIS_AUTH_STRING"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.redis_auth.secret_id
              version = "latest"
            }
          }
        }
        env {
          name  = "REDIS_TLS"
          value = "true"
        }
        volume_mounts {
          name       = "quota-keys"
          mount_path = "/etc/keys"
        }
      }
      volumes {
        name = "quota-keys"
        secret {
          secret = google_secret_manager_secret.quota_keys.secret_id
          items {
            version = "latest"
            path    = "keys.yaml"
          }
        }
      }
      max_retries = 1
    }
  }
  depends_on = [
    google_secret_manager_secret_version.quota_keys,
    google_secret_manager_secret_iam_member.quota_keys_accessor,
    google_redis_instance.quota,
    google_secret_manager_secret_version.redis_auth,
    google_secret_manager_secret_iam_member.redis_auth_accessor,
  ]
}

# ===================================================================
# CLOUD RUN: CALLOUT (Python ext_proc service)
# ===================================================================

resource "google_cloud_run_v2_service" "callout" {
  name                = "litellm-gateway-callout"
  location            = var.region
  deletion_protection = false
  # The callout trusts headers the route extension sets and meters
  # quota on the caller's virtual key, so a client able to reach it
  # directly could forge both. Only the load balancer may call it,
  # and the default run.app URI is switched off so there is no
  # address to reach it on besides the LB.
  ingress              = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default_uri_disabled = true

  template {
    service_account = local.callout_service_account

    # Direct VPC egress: allows the callout to reach Memorystore for Redis
    # on the private network without leaving Google's network.
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

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
      # Feature env vars: each is opt-in; the callout is inert if not set.
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.quota.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.quota.port)
      }
      env {
        name = "REDIS_AUTH_STRING"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_auth.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "REDIS_TLS"
        value = "true"
      }
      env {
        name  = "OTEL_EXPORTER_OTLP_ENDPOINT"
        value = var.otel_exporter_otlp_endpoint
      }
      env {
        name  = "GATEWAY_CONFIG"
        value = "/etc/gateway/config.yaml"
      }
      volume_mounts {
        name       = "gateway-config"
        mount_path = "/etc/gateway"
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

    volumes {
      name = "gateway-config"
      secret {
        secret = google_secret_manager_secret.gateway_config.secret_id
        items {
          # Pin the exact version rather than "latest". A mounted secret is
          # resolved when the revision starts, so with "latest" a change to
          # var.gateway_config would create a new secret version that the
          # running revision never picks up. Referencing the version here
          # makes the revision spec change too, which rolls a new revision
          # serving the new config.
          version = google_secret_manager_secret_version.gateway_config.version
          path    = "config.yaml"
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
    google_secret_manager_secret_version.gateway_config,
    google_secret_manager_secret_iam_member.gateway_config_accessor,
    google_redis_instance.quota,
    google_secret_manager_secret_version.redis_auth,
    google_secret_manager_secret_iam_member.redis_auth_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "callout_invoker" {
  name     = google_cloud_run_v2_service.callout.name
  location = google_cloud_run_v2_service.callout.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_compute_region_network_endpoint_group" "callout_neg" {
  name                  = "litellm-gateway-callout-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout.name
  }
}

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
  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ===================================================================
# CLOUD RUN: UPSTREAM APPLICATION (non-LLM traffic, e.g., chat UI)
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
  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ===================================================================
# VERTEX AI BACKEND: REGIONAL INTERNET NEG
# ===================================================================
#
# The provider APIs are reached through INTERNET_FQDN_PORT NEGs registered
# regionally (google_compute_region_network_endpoint_group) in the LB's
# region, behind regional backend services. That is what a regional external
# Application LB takes, so this chain is regional end to end and the URL map
# below references these backends by id.
#
# The global deployment in ../terraform expresses the same thing with the
# globally-scoped resources (google_compute_global_network_endpoint_group and
# google_compute_backend_service) to match its global LB. Outbound reach to
# these FQDNs depends on the Cloud NAT configured above.

resource "google_compute_region_network_endpoint_group" "vertex_neg" {
  name                  = "litellm-gateway-vertex-neg"
  region                = var.region
  network               = google_compute_network.vpc.id
  network_endpoint_type = "INTERNET_FQDN_PORT"
  depends_on            = [google_project_service.apis]
}

resource "google_compute_region_network_endpoint" "vertex_endpoint" {
  region_network_endpoint_group = google_compute_region_network_endpoint_group.vertex_neg.name
  region                        = var.region
  fqdn                          = "${var.region}-aiplatform.googleapis.com"
  port                          = 443
}

resource "google_compute_region_backend_service" "vertex_backend" {
  name                  = "litellm-gateway-vertex-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  timeout_sec           = 180
  backend {
    group           = google_compute_region_network_endpoint_group.vertex_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
  depends_on = [google_compute_region_network_endpoint.vertex_endpoint]
}

# ===================================================================
# THIRD-PARTY PROVIDER BACKENDS: REGIONAL INTERNET NEGs
# ===================================================================

resource "google_compute_region_network_endpoint_group" "provider_neg" {
  for_each              = local.third_party_providers
  name                  = "litellm-gateway-${each.key}-neg"
  region                = var.region
  network               = google_compute_network.vpc.id
  network_endpoint_type = "INTERNET_FQDN_PORT"
  depends_on            = [google_project_service.apis]
}

resource "google_compute_region_network_endpoint" "provider_endpoint" {
  for_each                      = local.third_party_providers
  region_network_endpoint_group = google_compute_region_network_endpoint_group.provider_neg[each.key].name
  region                        = var.region
  fqdn                          = each.value
  port                          = 443
}

resource "google_compute_region_backend_service" "provider_backend" {
  for_each              = local.third_party_providers
  name                  = "litellm-gateway-${each.key}-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  timeout_sec           = 180
  backend {
    group           = google_compute_region_network_endpoint_group.provider_neg[each.key].id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
  log_config {
    enable      = true
    sample_rate = 1.0
  }
  depends_on = [google_compute_region_network_endpoint.provider_endpoint]
}

# ===================================================================
# LOAD BALANCER: REGIONAL EXTERNAL APPLICATION LB
# ===================================================================
#
# Regional external Application LB uses regional resources:
#   google_compute_address (regional)
#   google_compute_region_ssl_certificate
#   google_compute_region_url_map
#   google_compute_region_target_https_proxy
#   google_compute_forwarding_rule (regional, no zone argument)
#
# The URL map references regional backend services throughout: the Cloud Run
# callout backend and the Internet NEG backends for the provider APIs.

resource "google_compute_address" "lb_ip" {
  name   = "litellm-gateway-lb-ip"
  region = var.region
}

resource "tls_private_key" "lb_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "lb_cert" {
  private_key_pem = tls_private_key.lb_key.private_key_pem
  subject {
    common_name = "litellm-gateway.example.com"
  }
  validity_period_hours = 8760
  allowed_uses          = ["server_auth"]
}

resource "google_compute_region_ssl_certificate" "lb_cert" {
  name        = "litellm-gateway-cert"
  region      = var.region
  private_key = tls_private_key.lb_key.private_key_pem
  certificate = tls_self_signed_cert.lb_cert.cert_pem
}

# URL map: header-based routing. The URL map picks the right provider backend
# by prefix-matching the client-supplied x-model-id header (which carries the
# LiteLLM model id, e.g. anthropic/claude-...). The Traffic Extension reads
# the body, transforms OpenAI to provider format, and rewrites :path for the
# upstream call.
#
# With the Route Extension enabled, the route extension runs first and can
# rewrite x-model-id (tier upgrade, bare-model normalization) before the URL
# map evaluates it.
#
# Rules:
#   gateway path + x-model-id starts with "anthropic/"  : Anthropic backend
#   gateway path + x-model-id starts with "groq/"       : Groq backend
#   gateway path + x-model-id starts with "openrouter/" : OpenRouter backend
#   any gateway path                                       : Vertex AI backend (default)
#   anything else                                 : upstream sample UI
resource "google_compute_region_url_map" "url_map" {
  name            = "litellm-gateway-url-map"
  region          = var.region
  default_service = google_compute_region_backend_service.upstream_backend.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "llm"
  }

  path_matcher {
    name            = "llm"
    default_service = google_compute_region_backend_service.upstream_backend.id

    route_rules {
      priority = 1
      dynamic "match_rules" {
        for_each = local.gateway_matchers
        content {
          prefix_match    = match_rules.value.prefix
          full_path_match = match_rules.value.full
          header_matches {
            header_name  = "x-model-id"
            prefix_match = "anthropic/"
          }
        }
      }
      service = google_compute_region_backend_service.provider_backend["anthropic"].id
      route_action {
        url_rewrite {
          host_rewrite = "api.anthropic.com"
        }
      }
    }

    route_rules {
      priority = 2
      dynamic "match_rules" {
        for_each = local.gateway_matchers
        content {
          prefix_match    = match_rules.value.prefix
          full_path_match = match_rules.value.full
          header_matches {
            header_name  = "x-model-id"
            prefix_match = "groq/"
          }
        }
      }
      service = google_compute_region_backend_service.provider_backend["groq"].id
      route_action {
        url_rewrite {
          host_rewrite = "api.groq.com"
        }
      }
    }

    route_rules {
      priority = 3
      dynamic "match_rules" {
        for_each = local.gateway_matchers
        content {
          prefix_match    = match_rules.value.prefix
          full_path_match = match_rules.value.full
          header_matches {
            header_name  = "x-model-id"
            prefix_match = "openrouter/"
          }
        }
      }
      service = google_compute_region_backend_service.provider_backend["openrouter"].id
      route_action {
        url_rewrite {
          host_rewrite = "openrouter.ai"
        }
      }
    }

    # Fallback for gateway paths with no header (or vertex_ai header) to Vertex AI.
    route_rules {
      priority = 4
      dynamic "match_rules" {
        for_each = local.gateway_matchers
        content {
          prefix_match    = match_rules.value.prefix
          full_path_match = match_rules.value.full
        }
      }
      service = google_compute_region_backend_service.vertex_backend.id
      route_action {
        url_rewrite {
          host_rewrite = "${var.region}-aiplatform.googleapis.com"
        }
      }
    }
  }
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
  depends_on            = [google_compute_subnetwork.proxy]
}

# ===================================================================
# SERVICE EXTENSIONS: TRAFFIC EXTENSION (regional)
# ===================================================================
#
# Traffic Extension on Regional LB. The callout sees REQUEST_BODY and does:
#   1. Body transform OpenAI to provider format (LiteLLM)
#   2. :path rewrite to the provider-specific path (LiteLLM's get_complete_url)
#   3. Auth header injection (Authorization for Vertex via ADC, x-api-key for
#      Anthropic, etc., all via LiteLLM's validate_environment)
#
# REQUEST_BODY is delivered BUFFERED (no streamed-request-body mode), so the
# callout parses the JSON in a single pass. The response body mode is chosen
# per request by the callout via mode_override (STREAMED for SSE, BUFFERED
# otherwise).

resource "google_network_services_lb_traffic_extension" "callout" {
  name                  = "litellm-gateway-traffic-ext"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "litellm-gateway-chain"
    match_condition {
      cel_expression = local.gateway_paths_cel
    }
    extensions {
      name             = "litellm-gateway-callout"
      service          = google_compute_region_backend_service.callout_backend.self_link
      authority        = "litellm-gateway.example.com"
      supported_events = ["REQUEST_HEADERS", "REQUEST_BODY", "RESPONSE_HEADERS", "RESPONSE_BODY"]
      # The callout blocks a worker on Redis for at most
      # _BRIDGE_TIMEOUT_S (service_callout_example.py). Keep that
      # constant below this timeout: a bridge budget above it parks
      # the worker past the point where the LB has given up.
      timeout = "10s"
    }
  }
  depends_on = [google_project_service.apis]
}

# ===================================================================
# SERVICE EXTENSIONS: ROUTE EXTENSION (regional)
# ===================================================================
# This resource runs the callout as a route extension. The callout's
# on_request_headers detects route mode from the per-extension metadata
# (mode=route, set in the extensions block below) and returns header
# rewrites plus clear_route_cache=true, allowing the URL map to re-evaluate
# x-model-id after the rewrite.

resource "google_network_services_lb_route_extension" "callout" {
  name                  = "litellm-gateway-route-ext"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_forwarding_rule.forwarding_rule.self_link
  ]
  extension_chains {
    name = "litellm-gateway-route-chain"
    match_condition {
      cel_expression = local.gateway_paths_cel
    }
    extensions {
      name             = "litellm-gateway-route-callout"
      service          = google_compute_region_backend_service.callout_backend.self_link
      authority        = "litellm-gateway.example.com"
      supported_events = ["REQUEST_HEADERS"]
      timeout          = "5s"
      metadata = {
        mode = "route"
      }
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
  description = "The URL of the Python ext_proc callout Cloud Run service."
  value       = google_cloud_run_v2_service.callout.uri
}

output "upstream_service_url" {
  description = "The URL of the upstream application Cloud Run service."
  value       = google_cloud_run_v2_service.upstream_app.uri
}

output "redis_host" {
  description = "The private IP of the Memorystore Redis instance (reachable via Direct VPC egress)."
  value       = google_redis_instance.quota.host
}

output "seed_job_command" {
  description = "Seeds the quota_keys into Memorystore. Run after apply, and after any change to quota_keys."
  value       = "gcloud run jobs execute litellm-gateway-seed-keys --region ${var.region} --project ${var.project_id}"
}

output "vertex_endpoint" {
  description = "The Vertex AI FQDN this deployment forwards LLM requests to."
  value       = "${var.region}-aiplatform.googleapis.com"
}

output "curl_test_command" {
  description = "Example curl command to test the LiteLLM gateway through the load balancer."
  value       = <<-EOT
    # Vertex AI (no header needed; default)
    curl -sk -X POST https://${google_compute_address.lb_ip.address}/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model": "vertex_ai/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hello"}]}'

    # Anthropic / Groq / OpenRouter: set x-model-id header with the model id
    curl -sk -X POST https://${google_compute_address.lb_ip.address}/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "x-model-id: anthropic/claude-haiku-4-5" \
      -d '{"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "Hello"}]}'
  EOT
}
