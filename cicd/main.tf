module "tagging" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/tagging?ref=0.0.3"
  classification = {
    confidentiality = "medium"
    availability    = "medium"
    integrity       = "medium"
    authenticity    = "medium"
  }
  datacomplience = "yes"
  responsability = {
    owner              = "sea_schedule_internals@kuehne-nagel.com"
    security-officer   = "unknown"
    operations-officer = "unknown"
    billing-officer    = "unknown"
  }
  costcentreid = "01ASIT"
  description  = "${local.project_name} management with terraform"
  product = {
    name        = "${local.project_name}"
    description = "${local.project_name} management with terraform"
  }
  project = {
    name        = "${local.project_name}"
    description = "${local.project_name} management with terraform"
    code        = "0000"
  }
  asssignment = [{
    name  = "SSM"
    value = "false"
  }]
  environment = var.environment
  team        = "SeaSchedule"
  external = {
    leanix             = "NA"
    cloudbricksID      = "NA"
    cloudbricksVersion = "NA"
  }
}

module "security_group" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/security-group?ref=0.0.3"
  common = {
    vpc_id       = var.vpc_id
    subnet_ids   = var.subnet_ids
    service_name = "${local.project_name}_sg"
  }
  security_group = {
    description = "${local.project_name}_sg"
    rules = [
      {
        description      = "${local.project_name}_sgi_rule"
        from_port        = 8000
        to_port          = 8000
        protocol         = "tcp"
        cidr_blocks      = var.sg_inboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "ingress"
      },
      {
        description      = "${local.project_name}_sgo_rule"
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = var.sg_outboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "egress"
      }
    ]
  }
}

module "security_group_lb" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/security-group?ref=0.0.3"
  common = {
    vpc_id       = var.vpc_id
    subnet_ids   = var.subnet_ids
    service_name = "${local.project_name}_lb_sg"
  }
  security_group = {
    description = "${local.project_name} Security Group for ALB"
    rules = [
      {
        description      = "${local.project_name} Ingress rule for ALB"
        from_port        = 80
        to_port          = 80
        protocol         = "tcp"
        cidr_blocks      = var.sg_inboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "ingress"
      },
      {
        description      = "${local.project_name} Egress rule for ALB"
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = var.sg_outboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "egress"
      }
    ]
  }
}

module "alb" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb?ref=0.0.3"
  lb = {
    name                       = "${local.alb_name}"
    internal                   = true
    load_balancer_type         = "application"
    subnet_ids                 = var.subnet_ids
    security_groups            = [module.security_group_lb.security_group_id]
    enable_deletion_protection = false
    access_logs = {
      bucket = aws_s3_bucket.logsAlb.id
      prefix = "logs"
      enabled = true
    }
  }
}

module "lb_target_group" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb-target-group?ref=0.0.3"
  lb_target_group = {
    name                  = "${local.project_name_abreb}-lbtg"
    protocol              = "HTTP"
    type                  = "ip"
    port                  = 80
    vpc_id                = var.vpc_id
    health_check_path     = "/health"
    health_check_protocol = "HTTP"
  }
}

module "lb_listener" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb-listener?ref=0.0.3"
  lb_listener = {
    load_balancer_arn = module.alb.lb_arn
    target_group_arn  = module.lb_target_group.lb_target_group_arn
  }
  depends_on = [
    module.lb_target_group, module.alb
  ]
}

module "ecs_cluster" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/ecs-cluster?ref=0.0.3"
  ecs_cluster = {
    name               = "${local.project_name}-cluster"
    container_insights = true
  }
}

module "ecs_service_task" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/ecs-service?ref=0.0.3"
  # Required variables
  ecs_service = {
    name                           = "${local.project_name}-service"
    force_new_deployment           = true
    cluster_id                     = module.ecs_cluster.ecs_cluster_id
    repository_name                = "${local.project_name}"
    launch_type                    = "FARGATE"
    desired_count                  = var.ecs_service_desired_count
    subnet_ids                     = var.subnet_ids
    security_groups                = [module.security_group.security_group_id]
    assign_public_ip               = false
    enable_lb                      = true
    load_balancer_container_name   = "${local.project_name}-task-container"
    load_balancer_container_port   = 8000
    load_balancer_target_group_arn = module.lb_target_group.lb_target_group_arn
    autoscaling_settings = {
      min_capacity        = var.autoscaling_settings_min_capacity,
      max_capacity        = var.autoscaling_settings_max_capacity,
      cpu_target_value    = var.autoscaling_settings_cpu_target_value,
      memory_target_value = var.autoscaling_settings_memory_target_value,
      scale_out_cooldown  = var.autoscaling_settings_scale_out_cooldown,
      scale_in_cooldown   = var.autoscaling_settings_scale_in_cooldown
    }
  }
  ecs_task = {
    name                                 = "${local.project_name}-task"
    network_mode                         = "awsvpc"
    memory                               = var.ecs_task_memory
    cpu                                  = var.ecs_task_cpu
    log_retention_days                   = var.ecs_task_log_retention_days
    task_execution_extra_inline_policies = local.task_execution_extra_inline_policies
    task_extra_inline_policies           = local.task_extra_inline_policies
    container_definitions                = local.container_definitions
  }
  depends_on = [
    module.ecs_cluster,
    module.lb_target_group,
    aws_secretsmanager_secret.this
  ]
}


output "alb_arn_suffix" {
  value = data.aws_lb.lb.arn_suffix
}