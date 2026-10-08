# Copyright 2025 Google LLC.
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

# Enable all necessary APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "networkservices.googleapis.com",
    "run.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# NETWORKING SETUP FOR REGIONAL EXTERNAL LOAD BALANCER
# ===================================================================
resource "google_compute_network" "vpc_network" {
  name                    = "service-extensions-vpc-cloudrun"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main_subnet" {
  name          = "main-subnet-cloudrun"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
}

# Required for regional external load balancers
resource "google_compute_subnetwork" "proxy_only_subnet" {
  name          = "proxy-only-subnet-cloudrun"
  ip_cidr_range = "10.0.2.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"

  lifecycle {
    prevent_destroy = false
  }
}

# ===================================================================
# PART 1A: TRAFFIC EXTENSION CALLOUT SERVICE (CLOUD RUN)
# ===================================================================

# Cloud Run callout service for traffic extension
resource "google_cloud_run_v2_service" "callout_service" {
  name                = "callout-service-traffic"
  location            = var.region
  deletion_protection = false

  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.callout_image
      ports {
        name           = "http1"
        container_port = 8080
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "callout_service_public_invoker" {
  name     = google_cloud_run_v2_service.callout_service.name
  location = google_cloud_run_v2_service.callout_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# TEMPORARY: Using compute service account for development
resource "google_cloud_run_v2_service_iam_member" "callout_service_lb_invoker" {
  name     = google_cloud_run_v2_service.callout_service.name
  location = google_cloud_run_v2_service.callout_service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Serverless NEG for callout service
resource "google_compute_region_network_endpoint_group" "callout_service_neg" {
  name                  = "callout-service-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.callout_service.name
  }
}

# Backend service for callout
resource "google_compute_region_backend_service" "callout_backend_service" {
  name                  = "callout-service-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group           = google_compute_region_network_endpoint_group.callout_service_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 1B: ROUTE EXTENSION CALLOUT SERVICE (CLOUD RUN)
# ===================================================================

resource "google_cloud_run_v2_service" "route_callout_service" {
  name                = "callout-service-route"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.callout_image
      ports {
        name           = "http1"
        container_port = 8080
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "route_callout_service_public_invoker" {
  name     = google_cloud_run_v2_service.route_callout_service.name
  location = google_cloud_run_v2_service.route_callout_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# TEMPORARY: Using compute service account for development
resource "google_cloud_run_v2_service_iam_member" "route_callout_service_lb_invoker" {
  name     = google_cloud_run_v2_service.route_callout_service.name
  location = google_cloud_run_v2_service.route_callout_service.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_compute_region_network_endpoint_group" "route_callout_service_neg" {
  name                  = "route-callout-service-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.route_callout_service.name
  }
}

resource "google_compute_region_backend_service" "route_callout_backend_service" {
  name                  = "route-callout-service-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group           = google_compute_region_network_endpoint_group.route_callout_service_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 2: THE MAIN APPLICATION (CLOUD RUN)
# ===================================================================

resource "google_cloud_run_v2_service" "main_app" {
  name                = "main-web-app"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.main_app_image
      ports {
        container_port = 8080
      }
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "main_app_public_invoker" {
  name     = google_cloud_run_v2_service.main_app.name
  location = google_cloud_run_v2_service.main_app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# TEMPORARY: Using compute service account for development
resource "google_cloud_run_v2_service_iam_member" "main_app_lb_invoker" {
  name     = google_cloud_run_v2_service.main_app.name
  location = google_cloud_run_v2_service.main_app.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_compute_region_network_endpoint_group" "main_app_neg" {
  name                  = "main-app-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.main_app.name
  }
}

resource "google_compute_region_backend_service" "main_app_backend_service" {
  name                  = "main-web-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group           = google_compute_region_network_endpoint_group.main_app_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 3: SECONDARY APPLICATION (CLOUD RUN - for route extension demo)
# ===================================================================

resource "google_cloud_run_v2_service" "secondary_app" {
  name                = "secondary-web-app"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = var.secondary_app_image
      ports {
        container_port = 8080
      }
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "secondary_app_public_invoker" {
  name     = google_cloud_run_v2_service.secondary_app.name
  location = google_cloud_run_v2_service.secondary_app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# TEMPORARY: Using compute service account for development
resource "google_cloud_run_v2_service_iam_member" "secondary_app_lb_invoker" {
  name     = google_cloud_run_v2_service.secondary_app.name
  location = google_cloud_run_v2_service.secondary_app.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

resource "google_compute_region_network_endpoint_group" "secondary_app_neg" {
  name                  = "secondary-app-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.secondary_app.name
  }
}

resource "google_compute_region_backend_service" "secondary_app_backend_service" {
  name                  = "secondary-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  backend {
    group           = google_compute_region_network_endpoint_group.secondary_app_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 4: LOAD BALANCER
# ===================================================================
resource "google_compute_address" "main_lb_ip" {
  name         = "main-app-lb-ip-cloudrun"
  region       = var.region
  address_type = "EXTERNAL"
}

resource "tls_private_key" "self_signed_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "self_signed_cert" {
  private_key_pem = tls_private_key.self_signed_key.private_key_pem
  subject {
    common_name = "main-app.example.com"
  }
  validity_period_hours = 12
  allowed_uses          = ["server_auth"]
}

resource "google_compute_region_ssl_certificate" "self_signed" {
  name        = "main-app-cert-cloudrun"
  region      = var.region
  private_key = tls_private_key.self_signed_key.private_key_pem
  certificate = tls_self_signed_cert.self_signed_cert.cert_pem
}

resource "google_compute_region_url_map" "main_url_map" {
  name            = "main-app-url-map-cloudrun"
  region          = var.region
  default_service = google_compute_region_backend_service.main_app_backend_service.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "main-matcher"
  }

  path_matcher {
    name            = "main-matcher"
    default_service = google_compute_region_backend_service.main_app_backend_service.id

    # Route based on the header added by the route extension
    route_rules {
      priority = 1
      match_rules {
        header_matches {
          header_name = "x-route-to"
          exact_match = "secondary"
        }
      }
      service = google_compute_region_backend_service.secondary_app_backend_service.id
    }
  }
}

resource "google_compute_region_target_https_proxy" "main_https_proxy" {
  name             = "main-app-https-proxy-cloudrun"
  region           = var.region
  url_map          = google_compute_region_url_map.main_url_map.id
  ssl_certificates = [google_compute_region_ssl_certificate.self_signed.id]
}

resource "google_compute_forwarding_rule" "main_forwarding_rule" {
  name                  = "main-app-fwd-rule-cloudrun"
  region                = var.region
  port_range            = "443"
  target                = google_compute_region_target_https_proxy.main_https_proxy.id
  ip_address            = google_compute_address.main_lb_ip.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  network               = google_compute_network.vpc_network.id

  depends_on = [
    google_compute_subnetwork.proxy_only_subnet
  ]
}

# ===================================================================
# PART 5: SERVICE EXTENSIONS
# ===================================================================

resource "google_network_services_lb_route_extension" "route_extension" {
  name                  = "regional-route-extension-cloudrun"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_forwarding_rule.main_forwarding_rule.id
  ]
  extension_chains {
    name = "route-decision-chain"
    match_condition {
      cel_expression = "request.path.startsWith('/secondary')"
    }
    extensions {
      name      = "route-callout-service"
      service   = google_compute_region_backend_service.route_callout_backend_service.id
      authority = "route-callout.example.com"
      timeout   = "5s"
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_network_services_lb_traffic_extension" "traffic_extension" {
  name                  = "regional-traffic-extension-cloudrun"
  location              = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  forwarding_rules = [
    google_compute_forwarding_rule.main_forwarding_rule.id
  ]
  extension_chains {
    name = "main-traffic-chain"
    match_condition {
      cel_expression = "true"
    }
    extensions {
      name             = "callout-service-traffic"
      service          = google_compute_region_backend_service.callout_backend_service.id
      authority        = "callout-service.example.com"
      supported_events = ["REQUEST_HEADERS"]
      timeout          = "5s"
    }
  }
  depends_on = [google_project_service.apis]
}