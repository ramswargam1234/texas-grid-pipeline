output "bucket_arn" {
  value = aws_s3_bucket.lake.arn
}

output "pipeline_user_arn" {
  value = aws_iam_user.pipeline.arn
}

output "pipeline_policy_arn" {
  value = aws_iam_policy.pipeline_s3.arn
}
