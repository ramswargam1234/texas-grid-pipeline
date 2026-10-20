# These resources were first created by hand in the AWS console. Import blocks adopt them into
# Terraform state on the first `terraform apply`, without recreating anything. After that first
# apply they are no-ops and can be left in place as documentation.

import {
  to = aws_s3_bucket.lake
  id = var.bucket_name
}

import {
  to = aws_s3_bucket_public_access_block.lake
  id = var.bucket_name
}

import {
  to = aws_s3_bucket_server_side_encryption_configuration.lake
  id = var.bucket_name
}

import {
  to = aws_s3_bucket_ownership_controls.lake
  id = var.bucket_name
}

import {
  to = aws_iam_user.pipeline
  id = var.pipeline_user_name
}

import {
  to = aws_iam_policy.pipeline_s3
  id = "arn:aws:iam::${var.aws_account_id}:policy/${var.pipeline_policy_name}"
}

import {
  to = aws_iam_user_policy_attachment.pipeline_s3
  id = "${var.pipeline_user_name}/arn:aws:iam::${var.aws_account_id}:policy/${var.pipeline_policy_name}"
}
