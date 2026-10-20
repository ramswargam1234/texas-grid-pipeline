terraform {
  # 1.7+ supports import blocks whose IDs use variables.
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # Every taggable resource gets these, so it's obvious in the console what Terraform owns.
  default_tags {
    tags = {
      Project   = "texas-grid-pipeline"
      ManagedBy = "terraform"
    }
  }
}
