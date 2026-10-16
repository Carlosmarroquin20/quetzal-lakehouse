# One role per job, each allowed only what the job needs, like the
# identities storage-init creates in the local stack. The jobs would run as
# ECS tasks and receive temporary credentials from their role, so there is
# no long-lived key to store or rotate.
locals {
  roles = {
    ingestion = {
      description = "Ingestion jobs: write bronze."
      read        = []
      read_write  = ["bronze"]
    }
    transform-prod = {
      description = "dbt in prod: read bronze, write prod silver and gold."
      read        = ["bronze"]
      read_write  = ["silver", "gold"]
    }
    transform-dev = {
      description = "dbt in dev: read bronze, write dev silver and gold."
      read        = ["bronze"]
      read_write  = ["silver-dev", "gold-dev"]
    }
    dashboard = {
      description = "Dashboard: read prod gold."
      read        = ["gold"]
      read_write  = []
    }
  }
}

data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "job" {
  for_each = local.roles

  name               = "${var.name_prefix}-${each.key}"
  description        = each.value.description
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

data "aws_iam_policy_document" "job" {
  for_each = local.roles

  # Listing every bucket the role uses, and finding its region.
  statement {
    sid     = "List"
    actions = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [
      for layer in concat(each.value.read, each.value.read_write) :
      aws_s3_bucket.layer[layer].arn
    ]
  }

  statement {
    sid     = "Read"
    actions = ["s3:GetObject"]
    resources = [
      for layer in concat(each.value.read, each.value.read_write) :
      "${aws_s3_bucket.layer[layer].arn}/*"
    ]
  }

  # Writing includes replacing and deleting objects, and the multipart
  # uploads DuckDB uses for large files.
  dynamic "statement" {
    for_each = length(each.value.read_write) > 0 ? [1] : []
    content {
      sid = "Write"
      actions = [
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts",
      ]
      resources = [
        for layer in each.value.read_write : "${aws_s3_bucket.layer[layer].arn}/*"
      ]
    }
  }
}

resource "aws_iam_role_policy" "job" {
  for_each = local.roles

  name   = "lakehouse-storage"
  role   = aws_iam_role.job[each.key].id
  policy = data.aws_iam_policy_document.job[each.key].json
}
