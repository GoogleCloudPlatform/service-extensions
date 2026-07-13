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

variable "region" {
  type    = string
  default = "us-central1"
}

variable "firestore_location" {
  description = "Firestore multi-region or region, e.g. nam5, us-central1."
  type        = string
  default     = "nam5"
}

variable "create_firestore_database" {
  description = "Whether to create the project's default Firestore database. Set false if one already exists."
  type        = bool
  default     = true
}

variable "callout_image" {
  description = "The container image for the Python callout service (used for both the gRPC callout and the ingestion HTTP app)."
  type        = string
}

variable "callout_service_account" {
  type    = string
  default = ""
}

variable "fail_open" {
  description = "If the Blocked State Store lookup itself fails, allow the request through (true) or deny it (false). Defaults to false: an unreachable kill switch must fail closed."
  type        = bool
  default     = false
}

variable "dry_run" {
  description = "Log intended containment actions without actually blocking any agent."
  type        = bool
  default     = false
}

variable "exempt_agents" {
  description = "Agent IDs that are never blocked regardless of findings (e.g. incident-response accounts)."
  type        = list(string)
  default     = []
}

variable "min_severity_vertex_anomaly" {
  type    = number
  default = 70
}

variable "min_severity_scc" {
  type    = number
  default = 60
}

variable "min_severity_wiz" {
  type    = number
  default = 60
}

variable "firestore_collection" {
  type    = string
  default = "breakglass_blocked_agents"
}

variable "state_cache_ttl_seconds" {
  type    = number
  default = 5
}

variable "mcp_resource_list" {
  description = "Cloud Resource Manager resource names to revoke roles/iap.egressor from on containment (defense-in-depth stage)."
  type        = list(string)
  default     = []
}

variable "vertex_anomaly_poll_endpoint" {
  description = "Vertex AI anomaly-detection poll URL. Leave empty to disable the Cloud Scheduler poll job."
  type        = string
  default     = ""
}

variable "anomaly_poll_schedule" {
  description = "Cron schedule for the Vertex anomaly-detection poll job."
  type        = string
  default     = "* * * * *"
}

variable "wiz_webhook_shared_secret" {
  description = "Shared secret for verifying Wiz webhook HMAC signatures."
  type        = string
  default     = ""
  sensitive   = true
}

variable "ingestion_allow_unauthenticated" {
  description = "Allow unauthenticated calls to the ingestion service. SCC Pub/Sub push and Cloud Scheduler both authenticate via OIDC instead, so this can usually stay false; set true only if a webhook source can't present an OIDC token."
  type        = bool
  default     = false
}
