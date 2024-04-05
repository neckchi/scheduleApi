module "tagging" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/tagging?ref=main"
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
  description  = "${var.project_name} management with terraform"
  product = {
    name        = "${var.project_name}"
    description = "${var.project_name} management with terraform"
  }
  project = {
    name        = "${var.project_name}"
    description = "${var.project_name} management with terraform"
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
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/security-group?ref=main"
  common = {
    vpc_id       = var.vpc_id
    subnet_ids   = var.subnet_ids
    service_name = "${var.project_name}_sg"
  }
  security_group = {
    description = "${var.project_name}_sg"
    rules = [
      {
        description      = "${var.project_name}_sgi_rule"
        from_port        = 8000
        to_port          = 8000
        protocol         = "tcp"
        cidr_blocks      = var.sg_inboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "ingress"
      },
      {
        description      = "${var.project_name}_sgo_rule"
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
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/security-group?ref=main"
  common = {
    vpc_id       = var.vpc_id
    subnet_ids   = var.subnet_ids
    service_name = "${var.project_name}_lb_sg"
  }
  security_group = {
    description = "${var.project_name} Security Group for ALB"
    rules = [
      {
        description      = "${var.project_name} Ingress rule for ALB"
        from_port        = 80
        to_port          = 80
        protocol         = "tcp"
        cidr_blocks      = var.sg_inboud_rules_cidrs
        ipv6_cidr_blocks = ["fc00::/7"]
        type             = "ingress"
      },
      {
        description      = "${var.project_name} Egress rule for ALB"
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
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb?ref=main"
  lb = {
    name                       = "${var.project_name_abreb}-alb"
    internal                   = true
    load_balancer_type         = "application"
    subnet_ids                 = var.subnet_ids
    security_groups            = [module.security_group_lb.security_group_id]
    enable_deletion_protection = false
  }
}

module "lb_target_group" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb-target-group?ref=main"
  lb_target_group = {
    name                  = "${var.project_name_abreb}-lbtg"
    protocol              = "HTTP"
    type                  = "ip"
    port                  = 80
    vpc_id                = var.vpc_id
    health_check_path     = "/docs"
    health_check_protocol = "HTTP"
  }
}

module "lb_listener" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb-listener?ref=main"
  lb_listener = {
    load_balancer_arn = module.alb.lb_arn
    target_group_arn  = module.lb_target_group.lb_target_group_arn
  }
  depends_on = [
    module.lb_target_group, module.alb
  ]
}

module "ecs_cluster" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/ecs-cluster?ref=main"
  ecs_cluster = {
    name = "${var.project_name}-cluster"
  }
}

module "ecs_service_task" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/ecs-service?ref=main"
  # Required variables
  ecs_service = {
    name                           = "${var.project_name}-service"
    force_new_deployment           = true
    cluster_id                     = module.ecs_cluster.ecs_cluster_id
    repository_name                = "${var.project_name}"
    launch_type                    = "FARGATE"
    desired_count                  = var.ecs_service_desired_count
    subnet_ids                     = var.subnet_ids
    security_groups                = [module.security_group.security_group_id]
    assign_public_ip               = false
    enable_lb                      = true
    load_balancer_container_name   = "${var.project_name}-task-container"
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
    name               = "${var.project_name}-task"
    network_mode       = "awsvpc"
    memory             = var.ecs_task_memory
    cpu                = var.ecs_task_cpu
    log_retention_days = var.ecs_task_log_retention_days
    task_execution_extra_inline_policies = [
      {
        name = "execution_logs_inline_policy"
        policy = jsonencode({
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "logs:*"
              ],
              "Resource" : [
                "arn:aws:logs:*:*:*"
              ],
              "Effect" : "Allow"
            }
          ]
        })
      },
      {
        name = "execution_secrets_inline_policy"
        policy = jsonencode({
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "secretsmanager:GetSecretValue"
              ],
              "Resource" : [
                "${var.api_secret_config}"
              ],
              "Effect" : "Allow"
            }
          ]
        })
      },
      {
        name = "cloudwatch"
        policy = jsonencode({
          Version = "2012-10-17"
          Statement = [
            {
              Action = [
                "cloudwatch:PutMetricData",
                "cloudwatch:DescribeAlarms",
                "cloudwatch:PutMetricAlarm",
                "cloudwatch:DeleteAlarms",
                "cloudwatch:DescribeAlarmHistory",
                "cloudwatch:DescribeAlarmsForMetric",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "cloudwatch:DisableAlarmActions",
                "cloudwatch:EnableAlarmActions"
              ]
              Effect   = "Allow"
              Resource = "*"
            }
          ]
          }
        )
      },
      {
        name = "autoscaling"
        policy = jsonencode(
          {
            "Version" : "2012-10-17",
            "Statement" : [
              {
                "Action" : [
                  "application-autoscaling:*"
                ],
                "Resource" : [
                  "*"
                ],
                "Effect" : "Allow"
              }
            ]
          }
        )
      }
    ]
    task_extra_inline_policies = [
      {
        name = "ecr_inline_policy"
        policy = jsonencode({
          Version = "2012-10-17"
          Statement = [
            {
              Action = [
                "ecr:GetAuthorizationToken",
                "ecr:DescribeImageScanFindings",
                "ecr:GetLifecyclePolicyPreview",
                "ecr:GetDownloadUrlForLayer",
                "ecr:DescribeImageReplicationStatus",
                "ecr:ListTagsForResource",
                "ecr:ListImages",
                "ecr:BatchGetRepositoryScanningConfiguration",
                "ecr:BatchGetImage",
                "ecr:DescribeImages",
                "ecr:DescribeRepositories",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetRepositoryPolicy",
                "ecr:GetLifecyclePolicy"
              ]
              Effect = "Allow"
              Resource = [
                "arn:aws:ecr:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:repository/*"
              ]
            },
          ]
        })
      },
      {
        name = "ecs_inline_policy"
        policy = jsonencode({
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "ecs:DescribeServices",
                "ecs:UpdateService",
                "ecs:List*"
              ],
              "Resource" : [
                "*"
              ],
              "Effect" : "Allow"
            }
          ]
        })
      },
      {
        name = "logs_inline_policy"
        policy = jsonencode({
          "Version" : "2012-10-17",
          "Statement" : [
            {
              "Action" : [
                "logs:*"
              ],
              "Resource" : [
                "arn:aws:logs:*:*:*"
              ],
              "Effect" : "Allow"
            }
          ]
        })
      },
      {
        name = "cloudwatch"
        policy = jsonencode({
          Version = "2012-10-17"
          Statement = [
            {
              Action = [
                "cloudwatch:PutMetricData",
                "cloudwatch:DescribeAlarms",
                "cloudwatch:PutMetricAlarm",
                "cloudwatch:DeleteAlarms",
                "cloudwatch:DescribeAlarmHistory",
                "cloudwatch:DescribeAlarmsForMetric",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "cloudwatch:DisableAlarmActions",
                "cloudwatch:EnableAlarmActions"
              ]
              Effect   = "Allow"
              Resource = "*"
            }
          ]
          }
        )
      },
      {
        name = "autoscaling"
        policy = jsonencode(
          {
            "Version" : "2012-10-17",
            "Statement" : [
              {
                "Action" : [
                  "application-autoscaling:*"
                ],
                "Resource" : [
                  "*"
                ],
                "Effect" : "Allow"
              }
            ]
          }
        )
      }
    ]
    container_definitions = [
      {
        "name" : "${var.project_name}-task-container",
        "image" : "${var.ecs_task_container_definitions_image}:${var.image_tag}",
        "cpu" : "${var.ecs_task_container_definitions_cpu}",
        "memory" : "${var.ecs_task_container_definitions_memory}",
        "networkMode" : "awsvpc",
        "logConfiguration" : {
          "logDriver" : "awslogs",
          "options" : {
            "awslogs-group" : "/ecs/p2p_schedule_api_of_carriers_service",
            "awslogs-region" : "${var.AWS_REGION}",
            "awslogs-stream-prefix" : "ecs"
          }
        },
        "portMappings" : [
          {
            "containerPort" : 8000,
            "hostPort" : 8000
          }
        ],
        environment = [for k, v in var.static_variables : { name : k, value : v }],
        secrets : [
          {
            "name" : "MONGO_URL",
            "valueFrom" : "${var.api_secret_config}:MONGO_URL::"
          },
          {
            "name" : "CMA_URL",
            "valueFrom" : "${var.api_secret_config}:CMA_URL::"
          },
          {
            "name" : "CMA_TOKEN",
            "valueFrom" : "${var.api_secret_config}:CMA_TOKEN::"
          },
          {
            "name" : "SUDU_URL",
            "valueFrom" : "${var.api_secret_config}:SUDU_URL::"
          },
          {
            "name" : "SUDU_TOKEN",
            "valueFrom" : "${var.api_secret_config}:SUDU_TOKEN::"
          },
          {
            "name" : "HMM_URL",
            "valueFrom" : "${var.api_secret_config}:HMM_URL::"
          },
          {
            "name" : "HMM_TOKEN",
            "valueFrom" : "${var.api_secret_config}:HMM_TOKEN::"
          },
          {
            "name" : "IQAX_URL",
            "valueFrom" : "${var.api_secret_config}:IQAX_URL::"
          },
          {
            "name" : "IQAX_TOKEN",
            "valueFrom" : "${var.api_secret_config}:IQAX_TOKEN::"
          },
          {
            "name" : "MAEU_P2P",
            "valueFrom" : "${var.api_secret_config}:MAEU_P2P::"
          },
          {
            "name" : "MAEU_LOCATION",
            "valueFrom" : "${var.api_secret_config}:MAEU_LOCATION::"
          },
          {
            "name" : "MAEU_CUTOFF",
            "valueFrom" : "${var.api_secret_config}:MAEU_CUTOFF::"
          },
          {
            "name" : "MAEU_TOKEN",
            "valueFrom" : "${var.api_secret_config}:MAEU_TOKEN::"
          },
          {
            "name" : "MAEU_TOKEN2",
            "valueFrom" : "${var.api_secret_config}:MAEU_TOKEN2::"
          },
          {
            "name" : "ONEY_URL",
            "valueFrom" : "${var.api_secret_config}:ONEY_URL::"
          },
          {
            "name" : "ONEY_TURL",
            "valueFrom" : "${var.api_secret_config}:ONEY_TURL::"
          },
          {
            "name" : "ONEY_TOKEN",
            "valueFrom" : "${var.api_secret_config}:ONEY_TOKEN::"
          },
          {
            "name" : "ONEY_AUTH",
            "valueFrom" : "${var.api_secret_config}:ONEY_AUTH::"
          },
          {
            "name" : "ZIM_URL",
            "valueFrom" : "${var.api_secret_config}:ZIM_URL::"
          },
          {
            "name" : "ZIM_TURL",
            "valueFrom" : "${var.api_secret_config}:ZIM_TURL::"
          },
          {
            "name" : "ZIM_TOKEN",
            "valueFrom" : "${var.api_secret_config}:ZIM_TOKEN::"
          },
          {
            "name" : "ZIM_CLIENT",
            "valueFrom" : "${var.api_secret_config}:ZIM_CLIENT::"
          },
          {
            "name" : "ZIM_SECRET",
            "valueFrom" : "${var.api_secret_config}:ZIM_SECRET::"
          },
          {
            "name" : "MSCU_URL",
            "valueFrom" : "${var.api_secret_config}:MSCU_URL::"
          },
          {
            "name" : "MSCU_AUD",
            "valueFrom" : "${var.api_secret_config}:MSCU_AUD::"
          },
          {
            "name" : "MSCU_OAUTH",
            "valueFrom" : "${var.api_secret_config}:MSCU_OAUTH::"
          },
          {
            "name" : "MSCU_CLIENT",
            "valueFrom" : "${var.api_secret_config}:MSCU_CLIENT::"
          },
          {
            "name" : "MSCU_THUMBPRINT",
            "valueFrom" : "${var.api_secret_config}:MSCU_THUMBPRINT::"
          },
          {
            "name" : "MSCU_SCOPE",
            "valueFrom" : "${var.api_secret_config}:MSCU_SCOPE::"
          },
          {
            "name" : "MSCU_RSA_KEY",
            "valueFrom" : "${var.api_secret_config}:MSCU_RSA_KEY::"
          },
          {
            "name" : "HLCU_TOKEN_URL",
            "valueFrom" : "${var.api_secret_config}:HLCU_TOKEN_URL::"
          },
          {
            "name" : "HLCU_URL",
            "valueFrom" : "${var.api_secret_config}:HLCU_URL::"
          },
          {
            "name" : "HLCU_CLIENT_ID",
            "valueFrom" : "${var.api_secret_config}:HLCU_CLIENT_ID::"
          },
          {
            "name" : "HLCU_CLIENT_SECRET",
            "valueFrom" : "${var.api_secret_config}:HLCU_CLIENT_SECRET::"
          },
          {
            "name" : "HLCU_USER_ID",
            "valueFrom" : "${var.api_secret_config}:HLCU_USER_ID::"
          },
          {
            "name" : "HLCU_PASSWORD",
            "valueFrom" : "${var.api_secret_config}:HLCU_PASSWORD::"
          },
          {
            "name" : "BASIC_USER",
            "valueFrom" : "${var.api_secret_config}:BASIC_USER::"
          },
          {
            "name" : "BASIC_PW",
            "valueFrom" : "${var.api_secret_config}:BASIC_PW::"
          },
          {
            "name" : "REDIS_HOST",
            "valueFrom" : "${var.api_secret_config}:REDIS_HOST::"
          },
          {
            "name" : "REDIS_PORT",
            "valueFrom" : "${var.api_secret_config}:REDIS_PORT::"
          },
          {
            "name" : "REDIS_DB",
            "valueFrom" : "${var.api_secret_config}:REDIS_DB::"
          },
          {
            "name" : "REDIS_USER",
            "valueFrom" : "${var.api_secret_config}:REDIS_USER::"
          },
          {
            "name" : "REDIS_PW",
            "valueFrom" : "${var.api_secret_config}:REDIS_PW::"
          }
        ]
      }
    ]
  }
  depends_on = [
    module.ecs_cluster,
    module.lb_target_group
  ]
}
