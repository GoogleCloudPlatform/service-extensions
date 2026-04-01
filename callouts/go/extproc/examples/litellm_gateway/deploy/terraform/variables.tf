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
  description = "The container image for the Go ext_proc callout service."
  type        = string
}

variable "litellm_image" {
  description = "The container image for the LiteLLM proxy sidecar."
  type        = string
}

variable "upstream_app_image" {
  description = "The container image for the upstream application (receives non-LLM traffic)."
  type        = string
  default     = "gcr.io/google-samples/hello-app:1.0"
}

variable "gemini_api_key" {
  description = "The Gemini API key for LiteLLM to use when routing to Gemini models."
  type        = string
  sensitive   = true
}

variable "enable_cors" {
  description = "Enable CORS headers and OPTIONS preflight handling for browser-based access."
  type        = bool
  default     = false
}

variable "sec_keywords" {
  description = "Comma-separated keywords to detect in prompts. When found, adds x-sec-keyword response header."
  type        = string
  default     = ""
}
