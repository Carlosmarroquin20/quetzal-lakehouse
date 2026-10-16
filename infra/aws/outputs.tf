output "buckets" {
  description = "Bucket of each layer, for the S3_BUCKET_* variables of the jobs."
  value       = { for layer, bucket in aws_s3_bucket.layer : layer => bucket.id }
}

output "roles" {
  description = "ARN of the role of each job, for the task definitions that will run them."
  value       = { for name, role in aws_iam_role.job : name => role.arn }
}
