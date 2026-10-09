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

variable "project_id" {
  description = "Target Google Cloud Project ID."
  type        = string
}

variable "project_number" {
  description = "Target Google Cloud Project Number (used in WIF audience)."
  type        = string
}

variable "region" {
  description = "GCP region for regional ALB, proxy subnet, and Agent Engine PSC NEG."
  type        = string
  default     = "us-central1"
}

variable "network" {
  description = "Existing VPC network name or self_link."
  type        = string
  default     = "default"
}

variable "proxy_subnet_cidr" {
  description = "CIDR range for the Envoy proxy-only subnet (purpose = \"REGIONAL_MANAGED_PROXY\")."
  type        = string
  default     = "10.0.0.0/23"
}

variable "wif_pool_id" {
  description = "Workload Identity Pool ID configured for token exchange."
  type        = string
}

variable "wif_provider_id" {
  description = "Workload Identity Provider ID inside the pool."
  type        = string
}

variable "ext_proc_image_uri" {
  description = "Full Artifact Registry container URI for service_callout_example.py."
  type        = string
}

variable "fail_closed" {
  description = "When true, the callout returns HTTP 403 if token exchange fails or credentials are missing/invalid. Defaults to false (fail-open)."
  type        = bool
  default     = false
}

variable "ssl_certificate_id" {
  description = "Optional existing regional SSL certificate self_link. If null, a self-signed certificate is automatically generated for sandbox testing."
  type        = string
  default     = null
}

