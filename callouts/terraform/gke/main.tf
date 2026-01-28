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
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
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
    "container.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# NETWORKING SETUP FOR REGIONAL EXTERNAL LOAD BALANCER
# ===================================================================
resource "google_compute_network" "vpc_network" {
  name                    = "service-extensions-vpc-gke"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "main_subnet" {
  name          = "main-subnet-gke"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id

  # Secondary IP ranges for GKE pods and services
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/16"
  }
}

# Required for regional external load balancers
resource "google_compute_subnetwork" "proxy_only_subnet" {
  name          = "proxy-only-subnet-gke"
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
# GKE CLUSTER
# ===================================================================
resource "google_container_cluster" "main" {
  name     = "service-extensions-cluster"
  location = var.region

  # Use regional cluster for high availability
  node_locations = []

  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc_network.name
  subnetwork = google_compute_subnetwork.main_subnet.name

  # IP allocation for pods and services
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Enable Workload Identity
  workload_identity_config {
    workload_pool = "${data.google_project.project.project_id}.svc.id.goog"
  }

  # Release channel for automatic updates
  release_channel {
    channel = "REGULAR"
  }

  # Disable deletion protection for easier testing
  deletion_protection = false

  depends_on = [google_project_service.apis]
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = var.region
  cluster    = google_container_cluster.main.name
  node_count = 1

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  node_config {
    machine_type = "e2-medium"

    # Google recommends custom service accounts that have cloud-platform scope and permissions granted via IAM Roles.
    service_account = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    tags = ["gke-node", "service-extensions-cluster"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# Configure kubernetes provider
data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.main.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.main.master_auth[0].cluster_ca_certificate)
}

# ===================================================================
# PART 1A: TRAFFIC EXTENSION CALLOUT SERVICE (GKE)
# ===================================================================

resource "kubernetes_deployment" "callout_service" {
  metadata {
    name = "callout-service-traffic"
    labels = {
      app = "callout-service-traffic"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "callout-service-traffic"
      }
    }

    template {
      metadata {
        labels = {
          app = "callout-service-traffic"
        }
      }

      spec {
        container {
          name  = "callout-container"
          image = var.callout_image

          port {
            name           = "grpc"
            container_port = 443
            protocol       = "TCP"
          }

          port {
            name           = "health"
            container_port = 80
            protocol       = "TCP"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }

  depends_on = [google_container_node_pool.primary_nodes]
}

resource "kubernetes_service" "callout_service" {
  metadata {
    name = "callout-service-traffic"
    annotations = {
      "cloud.google.com/neg" = jsonencode({
        exposed_ports = {
          "443" = {
            name = "callout-neg"
          }
        }
      })
    }
  }

  spec {
    type = "ClusterIP"

    selector = {
      app = "callout-service-traffic"
    }

    port {
      name        = "grpc"
      port        = 443
      target_port = 443
      protocol    = "TCP"
    }

    port {
      name        = "health"
      port        = 80
      target_port = 80
      protocol    = "TCP"
    }
  }

  depends_on = [kubernetes_deployment.callout_service]
}

# For GKE, we need to use zonal NEGs that are auto-created
# We'll create a backend service that references the NEG by name pattern
resource "google_compute_region_health_check" "callout_service_hc" {
  name   = "callout-service-hc"
  region = var.region

  http_health_check {
    port         = 80
    request_path = "/"
  }

  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3
}

resource "google_compute_region_backend_service" "callout_backend_service" {
  name                  = "callout-service-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  port_name             = "grpc"
  health_checks         = [google_compute_region_health_check.callout_service_hc.id]

  lifecycle {
    ignore_changes = [backend]
  }
}

# ===================================================================
# PART 1B: ROUTE EXTENSION CALLOUT SERVICE (GKE)
# ===================================================================

resource "kubernetes_deployment" "route_callout_service" {
  metadata {
    name = "callout-service-route"
    labels = {
      app = "callout-service-route"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "callout-service-route"
      }
    }

    template {
      metadata {
        labels = {
          app = "callout-service-route"
        }
      }

      spec {
        container {
          name  = "route-callout-container"
          image = var.callout_image

          port {
            name           = "grpc"
            container_port = 443
            protocol       = "TCP"
          }

          port {
            name           = "health"
            container_port = 80
            protocol       = "TCP"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }

  depends_on = [google_container_node_pool.primary_nodes]
}

resource "kubernetes_service" "route_callout_service" {
  metadata {
    name = "callout-service-route"
    annotations = {
      "cloud.google.com/neg" = jsonencode({
        exposed_ports = {
          "443" = {
            name = "route-neg"
          }
        }
      })
    }
  }

  spec {
    type = "ClusterIP"

    selector = {
      app = "callout-service-route"
    }

    port {
      name        = "grpc"
      port        = 443
      target_port = 443
      protocol    = "TCP"
    }

    port {
      name        = "health"
      port        = 80
      target_port = 80
      protocol    = "TCP"
    }
  }

  depends_on = [kubernetes_deployment.route_callout_service]
}

# Backend service for route extension callout
resource "google_compute_region_health_check" "route_callout_service_hc" {
  name   = "route-callout-service-hc"
  region = var.region

  http_health_check {
    port         = 80
    request_path = "/"
  }

  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3
}

resource "google_compute_region_backend_service" "route_callout_backend_service" {
  name                  = "route-callout-service-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  port_name             = "grpc"
  health_checks         = [google_compute_region_health_check.route_callout_service_hc.id]

  lifecycle {
    ignore_changes = [backend]
  }
}

# ===================================================================
# PART 2: THE MAIN APPLICATION (GKE)
# ===================================================================

resource "kubernetes_deployment" "main_app" {
  metadata {
    name = "main-web-app"
    labels = {
      app = "main-web-app"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "main-web-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "main-web-app"
        }
      }

      spec {
        container {
          name  = "main-app-container"
          image = var.main_app_image

          port {
            name           = "http"
            container_port = 8080
            protocol       = "TCP"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }

  depends_on = [google_container_node_pool.primary_nodes]
}

resource "kubernetes_service" "main_app" {
  metadata {
    name = "main-web-app"
    annotations = {
      "cloud.google.com/neg" = jsonencode({
        exposed_ports = {
          "80" = {
            name = "main-app-neg"
          }
        }
      })
    }
  }

  spec {
    type = "ClusterIP"

    selector = {
      app = "main-web-app"
    }

    port {
      name        = "http"
      port        = 80
      target_port = 8080
      protocol    = "TCP"
    }
  }

  depends_on = [kubernetes_deployment.main_app]
}

# Backend service for main app
resource "google_compute_region_health_check" "main_app_hc" {
  name   = "main-app-hc"
  region = var.region

  http_health_check {
    port         = 8080
    request_path = "/"
  }

  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3
}

resource "google_compute_region_backend_service" "main_app_backend_service" {
  name                  = "main-web-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  port_name             = "http"
  health_checks         = [google_compute_region_health_check.main_app_hc.id]

  lifecycle {
    ignore_changes = [backend]
  }
}

# ===================================================================
# PART 3: SECONDARY APPLICATION (GKE - for route extension demo)
# ===================================================================

resource "kubernetes_deployment" "secondary_app" {
  metadata {
    name = "secondary-web-app"
    labels = {
      app = "secondary-web-app"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "secondary-web-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "secondary-web-app"
        }
      }

      spec {
        container {
          name  = "secondary-app-container"
          image = var.secondary_app_image

          port {
            name           = "http"
            container_port = 8080
            protocol       = "TCP"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }

  depends_on = [google_container_node_pool.primary_nodes]
}

resource "kubernetes_service" "secondary_app" {
  metadata {
    name = "secondary-web-app"
    annotations = {
      "cloud.google.com/neg" = jsonencode({
        exposed_ports = {
          "80" = {
            name = "secondary-app-neg"
          }
        }
      })
    }
  }

  spec {
    type = "ClusterIP"

    selector = {
      app = "secondary-web-app"
    }

    port {
      name        = "http"
      port        = 80
      target_port = 8080
      protocol    = "TCP"
    }
  }

  depends_on = [kubernetes_deployment.secondary_app]
}

# Backend service for secondary app
resource "google_compute_region_health_check" "secondary_app_hc" {
  name   = "secondary-app-hc"
  region = var.region

  http_health_check {
    port         = 8080
    request_path = "/"
  }

  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3
}

resource "google_compute_region_backend_service" "secondary_app_backend_service" {
  name                  = "secondary-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  port_name             = "http"
  health_checks         = [google_compute_region_health_check.secondary_app_hc.id]

  lifecycle {
    ignore_changes = [backend]
  }
}

# ===================================================================
# PART 4: FIREWALL RULES
# ===================================================================
resource "google_compute_firewall" "allow_proxy_to_backends" {
  name    = "allow-proxy-to-backends-gke"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "8080", "443"]
  }

  source_ranges = ["10.0.2.0/24"]
  target_tags   = ["gke-node"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "allow-health-checks-gke"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "8080", "443"]
  }

  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["gke-node"]
}

resource "google_compute_firewall" "allow_external_lb" {
  name      = "allow-external-lb-traffic-gke"
  network   = google_compute_network.vpc_network.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["gke-node"]
}

# ===================================================================
# PART 5: LOAD BALANCER
# ===================================================================
resource "google_compute_address" "main_lb_ip" {
  name         = "main-app-lb-ip-gke"
  region       = var.region
  address_type = "EXTERNAL"
}

resource "tls_private_key" "self_signed_key" {
  algorithm = "RSA"
}

resource "tls_self_signed_cert" "self_signed_cert" {
  private_key_pem       = tls_private_key.self_signed_key.private_key_pem
  subject {
    common_name = "main-app.example.com"
  }
  validity_period_hours = 12
  allowed_uses          = ["server_auth"]
}

resource "google_compute_region_ssl_certificate" "self_signed" {
  name        = "main-app-cert-gke"
  region      = var.region
  private_key = tls_private_key.self_signed_key.private_key_pem
  certificate = tls_self_signed_cert.self_signed_cert.cert_pem
}

resource "google_compute_region_url_map" "main_url_map" {
  name            = "main-app-url-map-gke"
  region          = var.region
  default_service = google_compute_region_backend_service.main_app_backend_service.id

  host_rule {
    hosts        = ["*"]
    path_matcher = "main-matcher"
  }

  path_matcher {
    name            = "main-matcher"
    default_service = google_compute_region_backend_service.main_app_backend_service.id

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
  name             = "main-app-https-proxy-gke"
  region           = var.region
  url_map          = google_compute_region_url_map.main_url_map.id
  ssl_certificates = [google_compute_region_ssl_certificate.self_signed.id]
}

resource "google_compute_forwarding_rule" "main_forwarding_rule" {
  name                  = "main-app-fwd-rule-gke"
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
# PART 6: SERVICE EXTENSIONS
# ===================================================================

# Route Extension - Called BEFORE routing decision
resource "google_network_services_lb_route_extension" "route_extension" {
  name                  = "regional-route-extension-gke"
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

# Traffic Extension - Called AFTER routing decision
resource "google_network_services_lb_traffic_extension" "traffic_extension" {
  name                  = "regional-traffic-extension-gke"
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