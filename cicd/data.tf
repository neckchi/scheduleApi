data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "sops_file" "sops-secret" {
  source_file = "./environments/${var.environment}/secrets.yaml"
}
