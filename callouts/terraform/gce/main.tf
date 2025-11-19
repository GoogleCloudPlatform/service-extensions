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
    "networkservices.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# ===================================================================
# NETWORKING SETUP FOR REGIONAL EXTERNAL LOAD BALANCER
# ===================================================================
resource "google_compute_network" "vpc_network" {
  name                    = "service-extensions-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main_subnet" {
  name          = "main-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
}

# Required for regional external load balancers
resource "google_compute_subnetwork" "proxy_only_subnet" {
  name          = "proxy-only-subnet"
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
# PART 1A: TRAFFIC EXTENSION CALLOUT SERVICE (GCE MIG)
# ===================================================================
resource "google_compute_instance_template" "callout_app_template" {
  name_prefix  = "callout-gce-template-"
  machine_type = "e2-small"
  region       = var.region
  tags         = ["allow-lb-health-check"]

  disk {
    source_image = "cos-cloud/cos-stable"
  }

  service_account {
    email  = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  metadata = {
    gce-container-declaration = <<-EOT
spec:
  containers:
    - name: callout-container
      image: var.callout_image
      ports:
        - containerPort: 80
          hostPort: 80
        - containerPort: 8080
          hostPort: 8080
        - containerPort: 443
          hostPort: 443
      stdin: false
      tty: false
  restartPolicy: Always
EOT
    google-logging-enabled = "true"
  }

  network_interface {
    network    = google_compute_network.vpc_network.id
    subnetwork = google_compute_subnetwork.main_subnet.id
    access_config {}
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_compute_region_instance_group_manager" "callout_app_mig" {
  name               = "callout-gce-mig"
  region             = var.region
  version {
    instance_template = google_compute_instance_template.callout_app_template.id
  }
  base_instance_name = "callout-gce-vm"
  target_size        = 1

  named_port {
    name = "grpc"
    port = 443
  }

  named_port {
    name = "health"
    port = 80
  }
}

resource "google_compute_region_health_check" "callout_app_hc" {
  name   = "callout-gce-hc"
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
  name                  = "callout-gce-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  port_name             = "grpc"
  health_checks         = [google_compute_region_health_check.callout_app_hc.id]
  backend {
    group           = google_compute_region_instance_group_manager.callout_app_mig.instance_group
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 1B: ROUTE EXTENSION CALLOUT SERVICE (GCE MIG)
# ===================================================================
resource "google_compute_instance_template" "route_callout_template" {
  name_prefix  = "route-callout-template-"
  machine_type = "e2-small"
  region       = var.region
  tags         = ["allow-lb-health-check"]

  disk {
    source_image = "cos-cloud/cos-stable"
  }

  service_account {
    email  = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  metadata = {
    gce-container-declaration = <<-EOT
spec:
  containers:
    - name: route-callout-container
      image: var.callout_image
      ports:
        - containerPort: 80
          hostPort: 80
        - containerPort: 443
          hostPort: 443
      stdin: false
      tty: false
  restartPolicy: Always
EOT
    google-logging-enabled = "true"
  }

  network_interface {
    network    = google_compute_network.vpc_network.id
    subnetwork = google_compute_subnetwork.main_subnet.id
    access_config {}
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_compute_region_instance_group_manager" "route_callout_mig" {
  name               = "route-callout-mig"
  region             = var.region
  version {
    instance_template = google_compute_instance_template.route_callout_template.id
  }
  base_instance_name = "route-callout-vm"
  target_size        = 1

  named_port {
    name = "grpc"
    port = 443
  }

  named_port {
    name = "health"
    port = 80
  }
}

resource "google_compute_region_health_check" "route_callout_hc" {
  name   = "route-callout-hc"
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
  name                  = "route-callout-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP2"
  port_name             = "grpc"
  health_checks         = [google_compute_region_health_check.route_callout_hc.id]
  backend {
    group           = google_compute_region_instance_group_manager.route_callout_mig.instance_group
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 2: THE MAIN APPLICATION (GCE MIG)
# ===================================================================
resource "google_compute_instance_template" "main_app_template" {
  name_prefix  = "main-web-app-template-"
  machine_type = "e2-small"
  region       = var.region
  tags         = ["allow-lb-health-check"]

  disk {
    source_image = var.main_app_image
  }

  service_account {
    email  = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = "sudo apt-get update && sudo apt-get -y install nginx && echo '<h1>Main Application</h1>' | sudo tee /var/www/html/index.html"

  network_interface {
    network    = google_compute_network.vpc_network.id
    subnetwork = google_compute_subnetwork.main_subnet.id
    access_config {}
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_region_instance_group_manager" "main_app_mig" {
  name               = "main-web-app-mig"
  region             = var.region
  version {
    instance_template = google_compute_instance_template.main_app_template.id
  }
  base_instance_name = "main-web-app-vm"
  target_size        = 1

  named_port {
    name = "http"
    port = 80
  }
}

resource "google_compute_region_health_check" "main_app_hc" {
  name   = "main-web-app-hc"
  region = var.region
  http_health_check {
    port = 80
  }
}

resource "google_compute_region_backend_service" "main_app_backend_service" {
  name                  = "main-web-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  port_name             = "http"
  health_checks         = [google_compute_region_health_check.main_app_hc.id]
  backend {
    group           = google_compute_region_instance_group_manager.main_app_mig.instance_group
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 3: SECONDARY APPLICATION (for route extension demo)
# ===================================================================
resource "google_compute_instance_template" "secondary_app_template" {
  name_prefix  = "secondary-app-template-"
  machine_type = "e2-small"
  region       = var.region
  tags         = ["allow-lb-health-check"]

  disk {
    source_image = var.secondary_app_image
  }

  service_account {
    email  = "${data.google_project.project.number}-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = "sudo apt-get update && sudo apt-get -y install nginx && echo '<h1>Secondary Application - Routed via Extension</h1>' | sudo tee /var/www/html/index.html"

  network_interface {
    network    = google_compute_network.vpc_network.id
    subnetwork = google_compute_subnetwork.main_subnet.id
    access_config {}
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_region_instance_group_manager" "secondary_app_mig" {
  name               = "secondary-app-mig"
  region             = var.region
  version {
    instance_template = google_compute_instance_template.secondary_app_template.id
  }
  base_instance_name = "secondary-app-vm"
  target_size        = 1

  named_port {
    name = "http"
    port = 80
  }
}

resource "google_compute_region_health_check" "secondary_app_hc" {
  name   = "secondary-app-hc"
  region = var.region
  http_health_check {
    port = 80
  }
}

resource "google_compute_region_backend_service" "secondary_app_backend_service" {
  name                  = "secondary-app-be"
  region                = var.region
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  port_name             = "http"
  health_checks         = [google_compute_region_health_check.secondary_app_hc.id]
  backend {
    group           = google_compute_region_instance_group_manager.secondary_app_mig.instance_group
    capacity_scaler = 1.0
  }
}

# ===================================================================
# PART 4: FIREWALL RULES
# ===================================================================
resource "google_compute_firewall" "allow_proxy_to_backends" {
  name    = "allow-proxy-to-backends"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["80", "8080", "443"]
  }

  source_ranges = ["10.0.2.0/24"]
  target_tags   = ["allow-lb-health-check"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "main-app-fw-allow-health-checks"
  network = google_compute_network.vpc_network.name
  allow {
    protocol = "tcp"
    ports    = ["80", "8080"]
  }
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["allow-lb-health-check"]
}

resource "google_compute_firewall" "allow_external_lb" {
  name      = "allow-external-lb-traffic"
  network   = google_compute_network.vpc_network.name
  direction = "INGRESS"
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["allow-lb-health-check"]
}

# ===================================================================
# PART 5: LOAD BALANCER
# ===================================================================
resource "google_compute_address" "main_lb_ip" {
  name         = "main-app-lb-ip-gce"
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
  name        = "main-app-cert-gce"
  region      = var.region
  private_key = tls_private_key.self_signed_key.private_key_pem
  certificate = tls_self_signed_cert.self_signed_cert.cert_pem
}

resource "google_compute_region_url_map" "main_url_map" {
  name            = "main-app-url-map-gce"
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
  name             = "main-app-https-proxy-gce"
  region           = var.region
  url_map          = google_compute_region_url_map.main_url_map.id
  ssl_certificates = [google_compute_region_ssl_certificate.self_signed.id]
}

resource "google_compute_forwarding_rule" "main_forwarding_rule" {
  name                  = "main-app-fwd-rule-gce"
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
  name                  = "regional-route-extension-gce"
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
  name                  = "regional-traffic-extension-gce"
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
      name             = "callout-gce-service-traffic"
      service          = google_compute_region_backend_service.callout_backend_service.id
      authority        = "callout-service.example.com"
      supported_events = ["REQUEST_HEADERS"]
      timeout          = "5s"
    }
  }
  depends_on = [google_project_service.apis]
}