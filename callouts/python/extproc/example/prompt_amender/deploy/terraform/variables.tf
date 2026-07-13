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

variable "fail_open" {
  description = "If prompt amendment fails (bad JSON, template error, oversized body), pass the request through unmodified (true) rather than reject it (false)."
  type        = bool
  default     = true
}

variable "config_source" {
  description = "Where the callout sources rules.yaml from: env, gcs, or git."
  type        = string
  default     = "gcs"
  validation {
    condition     = contains(["env", "gcs", "git"], var.config_source)
    error_message = "config_source must be env, gcs, or git."
  }
}

variable "git_repo_url" {
  description = "Git repo URL for rules.yaml. Required when config_source = git."
  type        = string
  default     = ""
}

variable "git_branch" {
  description = "Git branch to poll when config_source = git."
  type        = string
  default     = "main"
}

variable "poll_interval_seconds" {
  description = "How often the callout polls its config source for changes."
  type        = number
  default     = 15
}
