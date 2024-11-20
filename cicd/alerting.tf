resource "aws_cloudwatch_metric_alarm" "cpu_alarm" {
  alarm_name          = "${local.project_name}-ecs-cpu-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "5"
  metric_name         = "CPUUtilized"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors ECS CPU utilization"
  dimensions = {
    ClusterName = "${local.project_name}-cluster"
  }
  alarm_actions             = [aws_sns_topic.this.arn]
  insufficient_data_actions = [aws_sns_topic.this.arn]
  ok_actions                = [aws_sns_topic.this.arn]
}

resource "aws_cloudwatch_metric_alarm" "memory_alarm" {
  alarm_name          = "${local.project_name}-ecs-memory-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "5"
  metric_name         = "MemoryUtilized"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors ECS memory utilization"
  dimensions = {
    ClusterName = "${local.project_name}-cluster"
  }
  alarm_actions             = [aws_sns_topic.this.arn]
  insufficient_data_actions = [aws_sns_topic.this.arn]
  ok_actions                = [aws_sns_topic.this.arn]
}

resource "aws_cloudwatch_metric_alarm" "UnHealthyHostCount" {
  alarm_name          = "${local.project_name}-ecs-unhealthy-host-count"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "5"
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "This metric monitors ECS unhealthy host count"
  dimensions = {
    ClusterName = "${local.project_name}-cluster"
  }
  alarm_actions             = [aws_sns_topic.this.arn]
  insufficient_data_actions = [aws_sns_topic.this.arn]
  ok_actions                = [aws_sns_topic.this.arn]
}




resource "aws_sns_topic" "this" {
  name = "${local.project_name}-alerting"
}

resource "aws_sns_topic_subscription" "this" {
  for_each   = { for idx, value in var.alerting_subscriptions : idx => value }
  topic_arn  = aws_sns_topic.this.arn
  protocol   = "email"
  endpoint   = each.value
  depends_on = [aws_sns_topic.this]
}

resource "aws_cloudwatch_metric_alarm" "ProcessingTime" {
  alarm_name          = "${local.project_name}-ProcessingTime"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "5"
  threshold           = "10"
  alarm_description   = "Processing time over 10 seconds above threshold"

  metric_query {
    id          = "m1"
    expression  = "SELECT MAX(ProcessingTime) FROM LoadBalancerMetricsP2P"
    label       = "ProcessingTime"
    return_data = true
    period = 60
  }
  alarm_actions             = [aws_sns_topic.this.arn]
  insufficient_data_actions = [aws_sns_topic.this.arn]
  ok_actions                = [aws_sns_topic.this.arn]

}



resource "aws_cloudwatch_log_metric_filter" "ecs_error_filter" {
  name           = "ecsErrorFilter"
  log_group_name = "/ecs/p2p_schedule_api_of_carriers_service"
  pattern        = "ERROR"

  metric_transformation {
    name      =  "${local.project_name}-ecs-errors"
    namespace = local.project_name
    value     = "1"
  }
}

resource "aws_cloudwatch_group" "ecs_error_filter" {
  name = "/ecs/p2p_schedule_api_of_carriers_service"
}

resource "aws_cloudwatch_metric_alarm" "ecs_error_alarm" {
  alarm_name          = "HighErrorRateECSAlarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = aws_cloudwatch_log_metric_filter.ecs_error_filter.metric_transformation[0].name
  namespace           = aws_cloudwatch_log_metric_filter.ecs_error_filter.metric_transformation[0].namespace
  period              = 300    # in seconds (5 minutes)
  statistic           = "Sum"
  threshold           = 10

  alarm_description   = "Triggers when ECS logs more than 10 errors in 5 minutes"
  actions_enabled     = true

  alarm_actions       = [aws_sns_topic.this.arn]
}
