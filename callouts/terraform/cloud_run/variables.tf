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
  description = "The container image for the callout service."
  type        = string
  default     = "us-docker.pkg.dev/service-extensions-samples/callouts/python-example-basic:main"
}

variable "main_app_image" {
  description = "The container image for the main application."
  type        = string
  default     = "gcr.io/google-samples/hello-app:1.0"
}

variable "secondary_app_image" {
  description = "The container image for the secondary application."
  type        = string
  default     = "gcr.io/google-samples/hello-app:2.0"
}