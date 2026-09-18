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
