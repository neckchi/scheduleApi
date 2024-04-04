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

module "lb_listener_rule" {
  source = "git::ssh://git@gitlab.tools.apim.eu-central-1.aws.int.kn/sea-schedule/terraform-modules//aws/lb-listener-rule?ref=main"
  lb_listener_rule = {
    lb_listener_arn  = var.lb_listener_arn
    target_group_arn = module.lb_target_group.lb_target_group_arn
    base_path        = "/p2p-api-carriers"
  }
  depends_on = [
    module.lb_target_group
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
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MONGO_URL::"
          },
          {
            "name" : "CMA_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:CMA_URL::"
          },
          {
            "name" : "CMA_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:CMA_TOKEN::"
          },
          {
            "name" : "SUDU_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:SUDU_URL::"
          },
          {
            "name" : "SUDU_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:SUDU_TOKEN::"
          },
          {
            "name" : "HMM_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HMM_URL::"
          },
          {
            "name" : "HMM_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HMM_TOKEN::"
          },
          {
            "name" : "IQAX_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:IQAX_URL::"
          },
          {
            "name" : "IQAX_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:IQAX_TOKEN::"
          },
          {
            "name" : "MAEU_P2P",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MAEU_P2P::"
          },
          {
            "name" : "MAEU_LOCATION",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MAEU_LOCATION::"
          },
          {
            "name" : "MAEU_CUTOFF",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MAEU_CUTOFF::"
          },
          {
            "name" : "MAEU_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MAEU_TOKEN::"
          },
          {
            "name" : "MAEU_TOKEN2",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MAEU_TOKEN2::"
          },
          {
            "name" : "ONEY_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ONEY_URL::"
          },
          {
            "name" : "ONEY_TURL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ONEY_TURL::"
          },
          {
            "name" : "ONEY_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ONEY_TOKEN::"
          },
          {
            "name" : "ONEY_AUTH",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ONEY_AUTH::"
          },
          {
            "name" : "ZIM_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ZIM_URL::"
          },
          {
            "name" : "ZIM_TURL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ZIM_TURL::"
          },
          {
            "name" : "ZIM_TOKEN",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ZIM_TOKEN::"
          },
          {
            "name" : "ZIM_CLIENT",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ZIM_CLIENT::"
          },
          {
            "name" : "ZIM_SECRET",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:ZIM_SECRET::"
          },
          {
            "name" : "MSCU_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_URL::"
          },
          {
            "name" : "MSCU_AUD",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_AUD::"
          },
          {
            "name" : "MSCU_OAUTH",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_OAUTH::"
          },
          {
            "name" : "MSCU_CLIENT",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_CLIENT::"
          },
          {
            "name" : "MSCU_THUMBPRINT",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_THUMBPRINT::"
          },
          {
            "name" : "MSCU_SCOPE",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_SCOPE::"
          },
          {
            "name" : "MSCU_RSA_KEY",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:MSCU_RSA_KEY::"
          },
          {
            "name" : "HLCU_TOKEN_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_TOKEN_URL::"
          },
          {
            "name" : "HLCU_URL",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_URL::"
          },
          {
            "name" : "HLCU_CLIENT_ID",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_CLIENT_ID::"
          },
          {
            "name" : "HLCU_CLIENT_SECRET",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_CLIENT_SECRET::"
          },
          {
            "name" : "HLCU_USER_ID",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_USER_ID::"
          },
          {
            "name" : "HLCU_PASSWORD",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:HLCU_PASSWORD::"
          },
          {
            "name" : "BASIC_USER",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:BASIC_USER::"
          },
          {
            "name" : "BASIC_PW",
            "valueFrom" : "arn:aws:secretsmanager:${var.AWS_REGION}:${var.AWS_PROFILE_ID}:secret:${var.environment}/p2p-schedule-api-of-carriers-IDIdKr:BASIC_PW::"
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
