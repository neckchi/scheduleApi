terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.30"
    }
    sops = {
      source  = "carlpett/sops"
      version = "~> 1.0.0"
    }
  }
}
