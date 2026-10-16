terraform {
  required_version = ">= 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
  }

  # State is kept in a local file, ignored by git. A real deployment would
  # keep it in an S3 bucket of its own, with locking, created before this
  # configuration; see docs/aws.md.
}
