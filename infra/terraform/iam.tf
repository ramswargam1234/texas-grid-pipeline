# The pipeline's identity. Used by the laptop and by GitHub Actions, each with its own access key.
# Access keys are deliberately NOT managed here: Terraform would store the secret in its state file.
# Create and rotate them in the console (IAM > Users > Security credentials).

resource "aws_iam_user" "pipeline" {
  name = var.pipeline_user_name
}

# Least privilege: list, read and write objects under raw/ (the lake) and state/ (the dbt warehouse
# file that carries snapshot history between cloud runs) in this one bucket. No delete.
data "aws_iam_policy_document" "pipeline_s3" {
  statement {
    sid       = "ListLakePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/", "raw/*", "state/", "state/*"]
    }
  }

  statement {
    sid       = "BucketLocation"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.lake.arn]
  }

  statement {
    sid       = "ReadWriteLakeObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.lake.arn}/raw/*",
      "${aws_s3_bucket.lake.arn}/state/*",
    ]
  }
}

resource "aws_iam_policy" "pipeline_s3" {
  name   = var.pipeline_policy_name
  policy = data.aws_iam_policy_document.pipeline_s3.json
  # No `description`: changing it forces AWS to replace the policy.
}

resource "aws_iam_user_policy_attachment" "pipeline_s3" {
  user       = aws_iam_user.pipeline.name
  policy_arn = aws_iam_policy.pipeline_s3.arn
}
