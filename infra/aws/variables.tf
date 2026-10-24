variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix of every bucket and role name. Bucket names are global across AWS accounts, so it must be unique to this deployment."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "Use 3 to 41 lowercase letters, digits and hyphens."
  }
}

variable "noncurrent_version_days" {
  description = "Days that bronze keeps the previous version of an object after it is overwritten."
  type        = number
  default     = 90
}

variable "backup_keep_days" {
  description = "Days the catalog dumps are kept. Below the days of table versions the catalogs keep (30), or old dumps point at deleted files."
  type        = number
  default     = 14

  validation {
    condition     = var.backup_keep_days >= 1 && var.backup_keep_days < 30
    error_message = "Keep between 1 and 29 days of dumps."
  }
}

variable "require_tls" {
  description = "Refuse requests to the buckets made without TLS. Only the emulator, which serves plain HTTP, turns it off."
  type        = bool
  default     = true
}

variable "s3_use_path_style" {
  description = "Address buckets as endpoint/bucket. Only the emulator needs it."
  type        = bool
  default     = false
}
