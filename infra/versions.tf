terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  # State in the S3 bucket from infra/bootstrap (S3-native locking, no DynamoDB).
  # The bucket name includes the account ID, so it is passed at init:
  #   terraform init -backend-config="bucket=asap-chem-hub-tfstate-<account-id>"
  backend "s3" {
    key          = "asap-chem-hub/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project }
  }
}

# us-east-1 is needed only for global-service resources that AWS keeps there: an ACM certificate
# for CloudFront (custom domain, domain.tf). The account's managed SCP allows acm:*, route53:* and
# cloudfront:* in us-east-1 while denying most regional services there.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = { Project = var.project }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  name       = var.project
}
