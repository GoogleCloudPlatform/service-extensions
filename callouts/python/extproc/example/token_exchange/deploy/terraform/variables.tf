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
  description = "The Google Cloud project ID where the resources will be created."
  type        = string
}

variable "region" {
  description = "The Google Cloud region for the resources."
  type        = string
  default     = "us-central1"
}

variable "callout_image" {
  description = "The container image for the Python ext_proc callout service."
  type        = string
}

variable "callout_service_account" {
  description = "Email of the service account used by the callout Cloud Run service. If empty, the project's default compute SA is used."
  type        = string
  default     = ""
}

variable "mode" {
  description = "INBOUND (3rd-party token -> GCP access token via STS/WIF) or OUTBOUND (GCP JWT -> 3rd-party native token)."
  type        = string
  default     = "INBOUND"
  validation {
    condition     = contains(["INBOUND", "OUTBOUND"], var.mode)
    error_message = "mode must be INBOUND or OUTBOUND."
  }
}

variable "fail_open" {
  description = "If the token exchange fails, pass the original credential through (true) rather than reject the request (false)."
  type        = bool
  default     = true
}

# --- INBOUND ---

variable "wif_audience" {
  description = "Workload Identity Federation pool provider audience, e.g. //iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/POOL/providers/PROVIDER. Required for mode=INBOUND."
  type        = string
  default     = ""
}

variable "target_service_account" {
  description = "Optional service account to impersonate after the STS exchange (INBOUND mode). If empty, the raw federated token is used."
  type        = string
  default     = ""
}

# --- OUTBOUND ---

variable "outbound_target_host" {
  description = "FQDN of the third-party API the load balancer forwards outbound traffic to (e.g. mycompany.my.salesforce.com). Required for mode=OUTBOUND."
  type        = string
  default     = ""
}

variable "external_token_endpoint" {
  description = "OAuth token endpoint of the external IdP (e.g. Salesforce). Required for mode=OUTBOUND."
  type        = string
  default     = ""
}

variable "external_client_id" {
  description = "Client ID registered with the external IdP, if required by its token endpoint."
  type        = string
  default     = ""
}
