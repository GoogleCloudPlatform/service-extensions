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

variable "outbound_client_secret" {
  type    = string
  default = ""
}
