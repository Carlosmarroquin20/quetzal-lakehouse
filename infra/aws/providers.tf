# Credentials come from the standard AWS environment variables. Against the
# emulator, AWS_ENDPOINT_URL points every service at it, so this file is the
# same for the emulator and for AWS.
provider "aws" {
  region = var.region

  # The emulator is reached through a plain hostname, which cannot resolve
  # the bucket.hostname addresses S3 uses by default.
  s3_use_path_style = var.s3_use_path_style

  default_tags {
    tags = {
      Project   = "quetzal-lakehouse"
      ManagedBy = "terraform"
    }
  }
}
