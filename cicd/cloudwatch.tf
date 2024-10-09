resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = local.project_name
  dashboard_body = jsonencode(
    {
      widgets = [
        {
          type = "metric",
          properties = {
            metrics   = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
            sparkline = true,
            view      = "singleValue",
            region    = "eu-central-1",
            period    = 300,
            stat      = "Sum",
            title     = "Total number of requests"
          }
        },
        {
          type = "metric"
          properties = {
            metrics = [["AWS/ApplicationELB", "HealthyHostCount", "TargetGroup", "${data.aws_lb_target_group.tg.arn_suffix}", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}",]]
            view    = "timeSeries",
            region  = "eu-central-1",
            period  = 300,
            stat    = "Average",
            title   = "Healthy hosts count (Average)"
            stacked = false
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Percent"
              }
            },
          }
        },
        {
          type = "metric"
          properties = {
            metrics = [["AWS/ApplicationELB", "UnHealthyHostCount", "TargetGroup", "${data.aws_lb_target_group.tg.arn_suffix}", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
            view    = "timeSeries",
            region  = "eu-central-1",
            period  = 300,
            stat    = "Average",
            title   = "UnHealthy hosts count (Average)"
            stacked = false
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Percent"
              }
            },
          }
        },
        {
          type = "metric",
          properties = {
            metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
            view    = "timeSeries",
            region  = "eu-central-1",
            period  = 1,
            stat    = "Sum",
            title   = "Total requests per seconds"
          }
        },
        {
          type = "metric"
          properties = {
            metrics = [["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
            view    = "timeSeries",
            stacked = false,
            region  = "eu-central-1",
            title   = "Target Response Time",
          }
        },
        {
          type = "metric"
          properties = {
            metrics = [
              ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"],
            ],
            view    = "timeSeries",
            stacked = false,
            region  = "eu-central-1",
            title   = "Total number of 5XX errors in ELB",
            stat    = "Sum",
            yAxis = {
              "left" : {
                "min" : 0,
              }
            }
          }
        },
        {
          type = "metric"
          properties = {
            metrics = [["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]],
            view    = "timeSeries",
            stacked = false,
            region  = "eu-central-1",
            title   = "Total number of 5XX errors in Target",
            stat    = "Sum",
            yAxis = {
              "left" : {
                "min" : 0,
              }
            }
          }
        },
        {
          type = "metric",
          properties = {
            metrics = [["AWS/ApplicationELB", "HTTPCode_Target_2XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
            stacked = false,
            view    = "timeSeries",
            region  = "eu-central-1",
            period  = 60,
            stat    = "Sum",
            title   = "Success requests per seconds in Target (2XXs)"
            yAxis = {
              "left" : {
                "min" : 0,
              }
            }
          }
        },
        {
          type = "metric",
          properties = {
            metrics = [
              ["AWS/ApplicationELB", "HTTPCode_ELB_4XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"],
              ["AWS/ApplicationELB", "HTTPCode_ELB_2XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]
            ]
            sparkline = true,
            view      = "timeSeries",
            region    = "eu-central-1",
            period    = 60,
            stat      = "Sum",
            title     = "Success requests per seconds LB (2XXs and 4XXs)"
            yAxis = {
              "left" : {
                "min" : 0,
              }
            }
          }
        },
        {
          type = "metric",
          properties = {
            metrics = [
              [{ "id" : "expr1m0", "label" : "p2p_schedule_api_of_carriers_cluster", "expression" : "mm1m0 * 100 / mm0m0", "stat" : "Average", "region" : "eu-central-1" }],
              ["ECS/ContainerInsights", "CpuReserved", "ClusterName", "p2p_schedule_api_of_carriers_cluster", { "id" : "mm0m0", "visible" : false, "stat" : "Sum", "region" : "eu-central-1" }],
              [".", "CpuUtilized", ".", ".", { "id" : "mm1m0", "visible" : false, "stat" : "Sum", "region" : "eu-central-1" }]
            ]
            sparkline = true,
            view      = "timeSeries",
            region    = "eu-central-1",
            period    = 60,
            title     = "CPU utilization"
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Percent"
              }
            },
          }
        },
        {
          type = "metric",
          properties = {
            metrics = [
              [{ "id" : "expr1m0", "label" : "p2p_schedule_api_of_carriers_cluster", "expression" : "mm1m0 * 100 / mm0m0", "stat" : "Average", "region" : "eu-central-1" }],
              ["ECS/ContainerInsights", "MemoryReserved", "ClusterName", "p2p_schedule_api_of_carriers_cluster", { "id" : "mm0m0", "visible" : false, "stat" : "Sum", "region" : "eu-central-1" }],
              [".", "MemoryUtilized", ".", ".", { "id" : "mm1m0", "visible" : false, "stat" : "Sum", "region" : "eu-central-1" }]
            ]
            sparkline = true,
            view      = "timeSeries",
            region    = "eu-central-1",
            period    = 60,
            title     = "Memory Utilization"
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : true,
                "label" : "Percent"
              }
              "right" : {
                "showUnits" : true
              }
            },
          }
        },
        {
          type = "metric",
          stacked = true,
          sparkline = false,
          view = "timeSeries",
          properties = {
            metrics = [
              [ { "expression": "SELECT COUNT(RequestByIP) FROM LoadBalancerMetricsP2P GROUP BY ClientIP", "id": "q1" } ]
            ],
            period  = 300,
            title   = "Load Balancer Requests by Client IP",
            stat    = "Sum",
            region  = "eu-central-1"
            dimensions = {
              "LoadBalancerName" = "${data.aws_lb.lb.arn_suffix}"
              "ClientIP" = "*"
            }
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Number"
              }
            },
          }
        },
        {
          type = "metric",
          stacked = false,
          sparkline = true,
          view = "timeSeries",
          properties = {
            metrics = [
              [ { "expression": "SELECT AVG(ProcessingTime) FROM LoadBalancerMetricsP2P", "id": "q1" } ]
            ],
            period  = 300,
            title   = "Average Processing time",
            stat    = "Average",
            region  = "eu-central-1"
            dimensions = {
              "LoadBalancerName" = "${data.aws_lb.lb.arn_suffix}"
              "ClientIP" = "*"
            }
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Seconds"
              }
            },
          }
        },
        {
          type = "metric",
          stacked = false,
          sparkline = true,
          view = "timeSeries",
          properties = {
            metrics = [
              [ { "expression": "SELECT AVG(ProcessingTime) FROM LoadBalancerMetricsP2P GROUP BY ClientIP", "id": "q1" } ]
            ],
            period  = 300,
            title   = "Processing time by Client IP",
            stat    = "Average",
            region  = "eu-central-1"
            dimensions = {
              "LoadBalancerName" = "${data.aws_lb.lb.arn_suffix}"
              "ClientIP" = "*"
            }
            yAxis = {
              "left" : {
                "min" : 0,
                "showUnits" : false,
                "label" : "Seconds"
              }
            },
          }
        }
      ]
    }
  )
}


resource "aws_s3_bucket" "logsAlb" {
  bucket = "${local.project_name}-${data.aws_caller_identity.current.account_id}-alb-logs"

}

/**
054676820928 is the id of aws loadbalance service account
https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html#access-log-create-bucket

*/

resource "aws_s3_bucket_policy" "logsAlb" {
  bucket = aws_s3_bucket.logsAlb.id
  policy = <<POLICY
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                 "AWS": "arn:aws:iam::054676820928:root" 
            },
            "Action": "s3:*",
            "Resource": "arn:aws:s3:::${aws_s3_bucket.logsAlb.id}/*"
        },
        {
            "Effect": "Allow",
            "Principal": {
                 "Service": "lambda.amazonaws.com"
            },
            "Action": [
              "s3:putObject",
              "s3:getObject"
            ],
            "Resource": "arn:aws:s3:::${aws_s3_bucket.logsAlb.id}/*"
        }
    ]
}
POLICY
}


resource "aws_glue_catalog_database" "this" {
  name = "${local.project_name}-lb-logs"
}


resource "aws_glue_catalog_table" "this" {
  database_name = aws_glue_catalog_database.this.name
  name          = "access_logs_alb"

  table_type = "EXTERNAL_TABLE"

  parameters = {
        "projection.enabled" = "true",
        "projection.day.type" = "date",
        "projection.day.range" = "2022/01/01,NOW",
        "projection.day.format" = "yyyy/MM/dd",
        "projection.day.interval" = "1",
        "projection.day.interval.unit" = "DAYS",
        "storage.location.template" = "s3://${aws_s3_bucket.logsAlb.id}/logs/AWSLogs/${data.aws_caller_identity.current.account_id}/elasticloadbalancing/eu-central-1/$${day}"
  }

  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.logsAlb.id}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    columns {
      name = "type"
      type = "string"
    }

    columns {
      name = "time"
      type = "string"
    }
    columns {
      name = "elb"
      type = "string"
    }
    columns {
      name = "client_ip"
      type = "string"
    }
    columns {
      name = "client_port"
      type = "string"
    }

    columns {
      name = "target_ip"
      type = "string"
    }
    columns {
      name = "target_port"
      type = "int"
    }
    columns {
      name = "request_processing_time"
      type = "double"
    }

    columns {
      name = "target_processing_time"
      type = "double"
    }
    columns {
      name = "response_processing_time"
      type = "double"
    }
    columns {
      name = "elb_status_code"
      type = "int"
    }
    columns {
      name = "target_status_code"
      type = "string"
    }
    columns {
      name = "received_bytes"
      type = "bigint"
    }
    columns {
      name = "sent_bytes"
      type = "bigint"
    }
    columns {
      name = "request_verb"
      type = "string"
    }
    columns {
      name = "request_url"
      type = "string"
    }
    columns {
      name = "request_proto"
      type = "string"
    }
    columns {
      name = "user_agent"
      type = "string"
    }
    columns {
      name = "ssl_cipher"
      type = "string"
    }
    columns {
      name = "ssl_protocol"
      type = "string"
    }
    columns {
      name = "target_group_arn"
      type = "string"
    }
    columns {
      name = "trace_id"
      type = "string"
    }
    columns {
      name = "domain_name"
      type = "string"
    }
    columns {
      name = "chosen_cert_arn"
      type = "string"
    }
    columns {
      name = "matched_rule_priority"
      type = "string"
    }
    columns {
      name = "request_creation_time"
      type = "string"
    }
    columns {
      name = "actions_executed"
      type = "string"
    }
    columns {
      name = "redirect_url"
      type = "string"
    }
    columns {
      name = "lambda_error_reason"
      type = "string"
    }
    columns {
      name = "target_port_list"
      type = "string"
    }
    columns {
      name = "target_status_code_list"
      type = "string"
    }
    columns {
      name = "classification"
      type = "string"
    }
    columns {
      name = "classification_reason"
      type = "string"
    }
    columns {
      name = "conn_trace_id"
      type = "string"
    }

    ser_de_info {
      name = "mySerDe"
        parameters = {
            "serialization.format" = "1",
            "input.regex" = "([^ ]*) ([^ ]*) ([^ ]*) ([^ ]*):([0-9]*) ([^ ]*)[:-]([0-9]*) ([-.0-9]*) ([-.0-9]*) ([-.0-9]*) (|[-0-9]*) (-|[-0-9]*) ([-0-9]*) ([-0-9]*) \"([^ ]*) (.*) (- |[^ ]*)\" \"([^\"]*)\" ([A-Z0-9-_]+) ([A-Za-z0-9.-]*) ([^ ]*) \"([^\"]*)\" \"([^\"]*)\" \"([^\"]*)\" ([-.0-9]*) ([^ ]*) \"([^\"]*)\" \"([^\"]*)\" \"([^ ]*)\" \"([^\\s]+?)\" \"([^\\s]+)\" \"([^ ]*)\" \"([^ ]*)\" ?([^ ]*)?"
        }
        serialization_library = "org.apache.hadoop.hive.serde2.RegexSerDe"

    }
  }
  depends_on = [aws_glue_catalog_database.this]

}

resource "aws_iam_role" "lambda_athena_role" {
  name = "lambda-athena-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_athena_policy" {
  name        = "lambda-athena-policy"
  description = "Lambda Athena and CloudWatch permissions"
  
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryResults",
          "athena:GetQueryExecution",
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_s3_policy" {
  name        = "lambda-s3-policy"
  description = "Lambda S3 permissions"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ],
        Resource = [
          "arn:aws:s3:::${aws_s3_bucket.logsAlb.bucket}"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ],
        Resource = [
          "arn:aws:s3:::${aws_s3_bucket.logsAlb.bucket}",
          "arn:aws:s3:::${aws_s3_bucket.logsAlb.bucket}/*"
        ]
      }
    ]
  })

}

resource "aws_iam_role_policy_attachment" "lambda_attach_policy" {
  role       = aws_iam_role.lambda_athena_role.name
  policy_arn = aws_iam_policy.lambda_athena_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_attach_s3_policy" {
  role       = aws_iam_role.lambda_athena_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

resource "aws_lambda_function" "athena_to_cloudwatch" {
  function_name = "athena-query-cloudwatch"
  role          = aws_iam_role.lambda_athena_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.9"
  filename      = data.archive_file.code.output_path
  description = "Lambda function to execute Athena queries and send results to CloudWatch"
  timeout = 300

  source_code_hash = data.archive_file.code.output_base64sha256

    environment {
        variables = {
            ATHENA_DATABASE       = aws_glue_catalog_database.this.name
            ATHENA_TABLE          = aws_glue_catalog_table.this.name
            ATHENA_OUTPUT_LOCATION = "s3://${aws_s3_bucket.logsAlb.bucket}/Unsaved//"
            ALB_NAME = local.alb_name
        }
    }


}


data "archive_file" "code" {
  type        = "zip"
  source_file = "./lambda/lambda_function.py"
  output_path = "./lambda/lambda_function.zip"
}


resource "aws_cloudwatch_event_rule" "schedule_rule" {
  name        = "athena-to-cloudwatch-schedule"
  description = "Run Athena query every hour and send results to CloudWatch"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule_rule.name
  target_id = "lambda-athena-cloudwatch"
  arn       = aws_lambda_function.athena_to_cloudwatch.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.athena_to_cloudwatch.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule_rule.arn
}
