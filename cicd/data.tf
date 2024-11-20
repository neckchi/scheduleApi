data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "sops_file" "sops-secret" {
  source_file = "./environments/${var.environment}/secrets.yaml"
}


data "aws_lb" "lb" {
  name = "${local.project_name_abreb}-alb"
  arn  = module.alb.lb_arn
}
