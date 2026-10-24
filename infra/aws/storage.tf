# One bucket per layer, as in the local stack. Bronze is shared by both
# environments; silver and gold have one bucket per environment.
locals {
  buckets = {
    bronze     = "${var.name_prefix}-bronze"
    silver     = "${var.name_prefix}-silver"
    gold       = "${var.name_prefix}-gold"
    silver-dev = "${var.name_prefix}-silver-dev"
    gold-dev   = "${var.name_prefix}-gold-dev"
    backups    = "${var.name_prefix}-backups"
  }
}

resource "aws_s3_bucket" "layer" {
  for_each = local.buckets

  bucket = each.value
}

# No bucket is ever public, whatever a later policy or object ACL says.
resource "aws_s3_bucket_public_access_block" "layer" {
  for_each = aws_s3_bucket.layer

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Access is decided by IAM policies alone; object ACLs are disabled.
resource "aws_s3_bucket_ownership_controls" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Encryption with keys managed by S3. A customer managed KMS key would add a
# monthly cost and a charge per request, for public data.
resource "aws_s3_bucket_server_side_encryption_configuration" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Requests without TLS are refused.
data "aws_iam_policy_document" "tls_only" {
  for_each = var.require_tls ? aws_s3_bucket.layer : {}

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "layer" {
  for_each = var.require_tls ? aws_s3_bucket.layer : {}

  bucket = each.value.id
  policy = data.aws_iam_policy_document.tls_only[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.layer]
}

# Bronze is the only layer that cannot be rebuilt, because the sources do
# not keep their history. Versioning keeps what a run overwrites for a
# while, so a bad load can be undone. Silver and gold are rebuilt from bronze
# on every run.
resource "aws_s3_bucket_versioning" "bronze" {
  bucket = aws_s3_bucket.layer["bronze"].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "layer" {
  for_each = aws_s3_bucket.layer

  bucket = each.value.id

  # DuckDB writes large files in parts; a run that dies leaves parts that
  # are billed until they are removed.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # The catalog dumps expire after the days the backup job keeps them, as a
  # second line in case the job stops pruning.
  dynamic "rule" {
    for_each = each.key == "backups" ? [1] : []
    content {
      id     = "expire-catalog-dumps"
      status = "Enabled"
      filter {
        prefix = "catalog/"
      }
      expiration {
        days = var.backup_keep_days
      }
    }
  }

  dynamic "rule" {
    for_each = each.key == "bronze" ? [1] : []
    content {
      id     = "expire-previous-versions"
      status = "Enabled"
      filter {}
      noncurrent_version_expiration {
        noncurrent_days = var.noncurrent_version_days
      }
    }
  }

  depends_on = [aws_s3_bucket_versioning.bronze]
}
