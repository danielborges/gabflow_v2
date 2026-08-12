terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      managed-by  = "terraform"
      owner       = var.owner
      cost-center = var.cost_center
      service     = "organization"
    }
  }
}
