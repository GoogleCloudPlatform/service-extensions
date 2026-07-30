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

variable "upstream_app_image" {
  description = "The container image for the upstream application (receives non-LLM traffic)."
  type        = string
  default     = "gcr.io/google-samples/hello-app:1.0"
}

variable "callout_service_account" {
  description = "Email of the service account used by the callout Cloud Run service. Must have roles/aiplatform.user so LiteLLM's ADC flow can mint Vertex AI bearer tokens. If empty, the project's default compute SA is used."
  type        = string
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API key. Picked up by LiteLLM when the request model starts with 'anthropic/'."
  type        = string
  default     = ""
  sensitive   = true
}

variable "groq_api_key" {
  description = "Groq API key. Picked up by LiteLLM when the request model starts with 'groq/'."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "OpenRouter API key. Picked up by LiteLLM when the request model starts with 'openrouter/'."
  type        = string
  default     = ""
  sensitive   = true
}

variable "otel_exporter_otlp_endpoint" {
  description = "OTLP endpoint for OpenTelemetry traces. Empty disables tracing."
  type        = string
  default     = ""
}

variable "redis_tier" {
  description = "Memorystore tier (BASIC or STANDARD_HA)."
  type        = string
  default     = "BASIC"
}

# Gateway config mounted into the callout at GATEWAY_CONFIG. Sections mirror
# LiteLLM's own config.yaml:
#
#   router_settings   model_group_alias, tag_rules, weighted_groups,
#                     shuffle_groups. This is the routing feature flag: a
#                     strategy runs only when its table here is non-empty.
#   litellm_settings  redact_user_api_key_info
#   general_settings  quota_fail_open
#
# Empty by default, which leaves the callout as the plain translation gateway:
# the route extension rewrites nothing and the request body's model is always
# the one served.
variable "gateway_config" {
  description = "Gateway config (router_settings, litellm_settings, general_settings) mounted into the callout. Empty disables routing."
  type        = any
  default     = {}
}

# Virtual keys for quota enforcement. Memorystore has a private IP, so keys
# are written by the seed-keys Cloud Run Job rather than by Terraform itself:
# this variable is rendered into the YAML that job feeds to seed_keys.py.
#
# Defaults to an empty list, so a fresh deployment seeds nothing and quota
# stays effectively off (keyless requests pass through unmetered; a request
# presenting an unknown key gets 401). Define your own keys here, or seed
# them by hand with seed_keys.py; see terraform.tfvars.example for a set that
# exercises every enforcement path.
#
# The type is `any` on purpose. A typed object with optional() attributes
# emits unset fields as explicit YAML nulls, which the seeder would store as
# the strings "None" and "null": a key with an unset `models` field would then
# get a one-entry allowlist and reject every request with 403.
#
# Supported fields per entry (all optional except `key`, matching LiteLLM's
# /key/generate naming):
#   key              virtual key the client sends as `Authorization: Bearer`
#   token_budget     tokens allowed per budget_duration window
#   budget_duration  30s / 30m / 30h / 30d / 1mo
#   rpm_limit        requests per minute
#   tpm_limit        tokens per minute
#   soft_budget      log a warning past this, never block
#   expires          ISO-8601 timestamp; past means the key is rejected (401)
#   models           allowlist of exact model ids or `<provider>/*` wildcards
#   model_max_budget map of model id to { budget_limit, time_period }
variable "quota_keys" {
  description = "Virtual keys seeded into Memorystore by the seed-keys job. Empty (the default) seeds nothing."
  type        = any
  default     = []
  # Each entry's `key` is a bearer credential clients send as
  # `Authorization: Bearer <key>`. Marking this sensitive redacts it from
  # `terraform plan` / `apply` output.
  sensitive = true

  validation {
    condition     = alltrue([for k in var.quota_keys : can(k.key) && k.key != ""])
    error_message = "Every quota_keys entry needs a non-empty key attribute."
  }
}
