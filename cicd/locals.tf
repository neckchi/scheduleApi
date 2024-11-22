# AWS Config Parametres
locals {
  AWS_REGION = "eu-central-1"
  sops_environment = var.environment == "prod" ? "production" : var.environment
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
              "secretsmanager:*"
            ],
            "Resource" : [
              "${aws_secretsmanager_secret.this.arn}"
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
              "arn:aws:ecr:${local.AWS_REGION}:${data.aws_caller_identity.current.account_id}:repository/*"
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
      "name" : "${local.project_name}-task-container",
      "image" : "${var.ecs_task_container_definitions_image}:${var.image_tag}",
      "cpu" : "${var.ecs_task_container_definitions_cpu}",
      "memory" : "${var.ecs_task_container_definitions_memory}",
      "networkMode" : "awsvpc",
      "logConfiguration" : {
        "logDriver" : "awslogs",
        "options" : {
          "awslogs-group" : "/ecs/p2p_schedule_api_of_carriers_service",
          "awslogs-region" : "${local.AWS_REGION}",
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
          "name" : "CMA_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:CMA_URL::"
        },
        {
          "name" : "CMA_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:CMA_TOKEN::"
        },
        {
          "name" : "SUDU_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:SUDU_URL::"
        },
        {
          "name" : "SUDU_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:SUDU_TOKEN::"
        },
        {
          "name" : "HMM_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:HMM_URL::"
        },
        {
          "name" : "HMM_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:HMM_TOKEN::"
        },
        {
          "name" : "IQAX_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:IQAX_URL::"
        },
        {
          "name" : "IQAX_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:IQAX_TOKEN::"
        },
        {
          "name" : "MAEU_P2P",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MAEU_P2P::"
        },
        {
          "name" : "MAEU_LOCATION",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MAEU_LOCATION::"
        },
        {
          "name" : "MAEU_CUTOFF",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MAEU_CUTOFF::"
        },
        {
          "name" : "MAEU_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MAEU_TOKEN::"
        },
        {
          "name" : "MAEU_TOKEN2",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MAEU_TOKEN2::"
        },
        {
          "name" : "ONEY_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ONEY_URL::"
        },
        {
          "name" : "ONEY_TURL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ONEY_TURL::"
        },
        {
          "name" : "ONEY_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ONEY_TOKEN::"
        },
        {
          "name" : "ONEY_AUTH",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ONEY_AUTH::"
        },
        {
          "name" : "ZIM_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ZIM_URL::"
        },
        {
          "name" : "ZIM_TURL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ZIM_TURL::"
        },
        {
          "name" : "ZIM_TOKEN",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ZIM_TOKEN::"
        },
        {
          "name" : "ZIM_CLIENT",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ZIM_CLIENT::"
        },
        {
          "name" : "ZIM_SECRET",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:ZIM_SECRET::"
        },
        {
          "name" : "MSCU_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_URL::"
        },
        {
          "name" : "MSCU_AUD",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_AUD::"
        },
        {
          "name" : "MSCU_OAUTH",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_OAUTH::"
        },
        {
          "name" : "MSCU_CLIENT",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_CLIENT::"
        },
        {
          "name" : "MSCU_THUMBPRINT",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_THUMBPRINT::"
        },
        {
          "name" : "MSCU_SCOPE",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_SCOPE::"
        },
        {
          "name" : "MSCU_RSA_KEY",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:MSCU_RSA_KEY::"
        },
        {
          "name" : "HLCU_URL",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:HLCU_URL::"
        },
        {
          "name" : "HLCU_CLIENT_ID",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:HLCU_CLIENT_ID::"
        },
        {
          "name" : "HLCU_CLIENT_SECRET",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:HLCU_CLIENT_SECRET::"
        },
        {
          "name" : "BASIC_USER",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:BASIC_USER::"
        },
        {
          "name" : "BASIC_PW",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:BASIC_PW::"
        },
        {
          "name" : "REDIS_HOST",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:REDIS_HOST::"
        },
        {
          "name" : "REDIS_PORT",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:REDIS_PORT::"
        },
        {
          "name" : "REDIS_DB",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:REDIS_DB::"
        },
        {
          "name" : "REDIS_USER",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:REDIS_USER::"
        },
        {
          "name" : "REDIS_PW",
          "valueFrom" : "${aws_secretsmanager_secret.this.arn}:REDIS_PW::"
        }
      ]
    }
  ]
  project_name       = "p2p-schedule-api-of-carriers"
  project_name_abreb = "p2papicarriers"
  alb_name    = "p2papicarriers-alb"
}
