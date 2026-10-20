variable "aws_account_id" {
  description = "12-digit AWS account ID. Set it in terraform.tfvars (git-ignored), never in code."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 digits."
  }
}

variable "aws_region" {
  description = "Region the data lake bucket lives in."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "Named profile in ~/.aws/credentials that Terraform uses (an admin user, not the pipeline user)."
  type        = string
  default     = "terraform-admin"
}

variable "bucket_name" {
  description = "S3 bucket holding the raw Parquet lake."
  type        = string
  default     = "texas-grid-pipeline-ram"
}

variable "pipeline_user_name" {
  description = "IAM user the pipeline (laptop + GitHub Actions) authenticates as."
  type        = string
  default     = "texas-grid-pipeline"
}

variable "pipeline_policy_name" {
  description = "Name of the pipeline's least-privilege IAM policy."
  type        = string
  default     = "texas-grid-s3-access"
}

variable "noncurrent_version_days" {
  description = "How long to keep overwritten (noncurrent) object versions before deleting them."
  type        = number
  default     = 30
}
