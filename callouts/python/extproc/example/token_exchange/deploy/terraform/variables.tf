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
  type = string
}

variable "project_number" {
  type = string
}

variable "region" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "token_exchange_mode" {
  type        = string
  default     = "INBOUND"
  description = "INBOUND or OUTBOUND"
}

variable "wif_pool_id" {
  type    = string
  default = ""
}

variable "wif_provider_id" {
  type    = string
  default = ""
}

variable "outbound_token_url" {
  type    = string
  default = ""
}

variable "outbound_client_id" {
  type    = string
  default = ""
}

variable "outbound_client_secret_id" {
  type        = string
  default     = ""
  description = "ID of an existing Secret Manager secret that holds the OAuth client secret for outbound mode. Leave empty if the token endpoint needs no client secret."
}

variable "outbound_client_secret_version" {
  type        = string
  default     = "latest"
  description = "Version of the Secret Manager secret to expose to the callout server."
}

variable "fail_closed" {
  type        = bool
  default     = false
  description = "If true, requests whose token could not be exchanged are rejected instead of being passed through to the backend."
}
