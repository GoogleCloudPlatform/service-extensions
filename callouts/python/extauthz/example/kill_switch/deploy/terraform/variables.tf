# Copyright 2026 Google LLC.
# Licensed under the Apache License, Version 2.0

variable "project_id" {
  description = "The Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "The Google Cloud region."
  type        = string
  default     = "us-central1"
}

variable "kill_switch_image" {
  description = "The container image for the Kill Switch service."
  type        = string
}

variable "kill_switch_service_account" {
  description = "Service account email for the Kill Switch Cloud Run services, Pub/Sub push, and Scheduler. Defaults to the project's default compute SA."
  type        = string
  default     = null
}

variable "agent_gateway_service_account" {
  description = "Service account email of the Agent Gateway, granted roles/run.invoker on the ext_authz service. If empty, no IAM binding is created."
  type        = string
  default     = ""
}

# -------------------------------------------------------------------
# KILL SWITCH POLICY VARIABLES
# -------------------------------------------------------------------

variable "dry_run" {
  description = "If true, the kill switch logs the block intent but does not isolate the agent."
  type        = string
  default     = "false"
}

variable "exempt_agents" {
  description = "Comma-separated list of SPIFFE IDs that should never be blocked."
  type        = string
  default     = ""
}

variable "scc_threshold" {
  description = "Minimum severity for SCC alerts to trigger a block."
  type        = string
  default     = "HIGH"
}

variable "wiz_threshold" {
  description = "Minimum severity for Wiz alerts to trigger a block."
  type        = string
  default     = "CRITICAL"
}

variable "vertex_threshold" {
  description = "Minimum severity for Vertex AI alerts to trigger a block."
  type        = string
  default     = "MEDIUM"
}

# -------------------------------------------------------------------
# VERTEX AI VARIABLES
# -------------------------------------------------------------------

variable "enable_vertex_polling" {
  description = "Feature flag to enable Cloud Scheduler polling of the Vertex AI model."
  type        = string
  default     = "true"
}

variable "vertex_endpoint_id" {
  description = "The Endpoint ID of the deployed Vertex AI Anomaly Detection model."
  type        = string
  default     = ""
}
