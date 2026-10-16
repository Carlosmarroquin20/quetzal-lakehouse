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
