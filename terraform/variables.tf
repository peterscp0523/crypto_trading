variable "region" {
  description = "Oracle Cloud region"
  type        = string
  default     = "ap-seoul-1"
}

variable "compartment_id" {
  description = "Compartment OCID (루트 compartment 사용)"
  type        = string
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "cryptodb"
}

variable "db_display_name" {
  description = "Database display name"
  type        = string
  default     = "crypto-trading-db"
}

variable "db_admin_password" {
  description = "Database admin password (최소 12자, 대소문자+숫자+특수문자 포함)"
  type        = string
  sensitive   = true
}

variable "db_wallet_password" {
  description = "Database wallet password"
  type        = string
  sensitive   = true
}

variable "is_free_tier" {
  description = "Always Free Tier 사용 여부"
  type        = bool
  default     = true
}

variable "cpu_core_count" {
  description = "OCPU count (Always Free는 1)"
  type        = number
  default     = 1
}

variable "data_storage_size_in_tbs" {
  description = "Storage size in TB (Always Free는 0.02 = 20GB)"
  type        = number
  default     = 0.02
}
