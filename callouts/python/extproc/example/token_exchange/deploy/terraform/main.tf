terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
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

resource "google_cloud_run_v2_service" "ext_proc_service" {
  name     = "token-exchange-ext-proc"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    containers {
      image = var.image_uri
      ports {
        container_port = 8080
        name           = "h2c"
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
      env {
        name  = "OUTBOUND_CLIENT_SECRET"
        value = var.outbound_client_secret
      }
    }
  }
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
      name             = "ext-proc-authz"
      authority        = "ext-proc-authz.google.com"
      service          = google_compute_backend_service.ext_proc_backend.self_link
      timeout          = "10s"
      fail_open        = true
      supported_events = ["REQUEST_HEADERS"]
    }
  }
}

# -----------------------------------------------------------------------------
# TEST INFRASTRUCTURE: ECHO BACKEND & GLOBAL APPLICATION LOAD BALANCER
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "echo_backend" {
  name     = "token-exchange-echo-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  template {
    containers {
      image = "mccutchen/go-httpbin:v2.23.1"
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
