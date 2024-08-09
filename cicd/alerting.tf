resource "aws_cloudwatch_metric_alarm" "cpu_alarm" {
  alarm_name                = "ecs-cpu-utilization"
  comparison_operator       = "GreaterThanThreshold"
  evaluation_periods        = "5"
  metric_name               = "CPUUtilized"
  namespace                 = "AWS/ECS"
  period                    = "60"
  statistic                 = "Average"
  threshold                 = "80"
  alarm_description         = "This metric monitors ECS CPU utilization"
  dimensions = {
    ClusterName = "${local.project_name}-cluster"
  }
  alarm_actions             = [aws_sns_topic.this.arn]
  insufficient_data_actions = [aws_sns_topic.this.arn]
  ok_actions                = [aws_sns_topic.this.arn]
}

resource "aws_cloudwatch_metric_alarm" "memory_alarm" {
  alarm_name                = "ecs-memory-utilization"
  comparison_operator       = "GreaterThanThreshold"
  evaluation_periods        = "5"
  metric_name               = "MemoryUtilized"
  namespace                 = "AWS/ECS"
  period                    = "60"
  statistic                 = "Average"
  threshold                 = "80"
  alarm_description         = "This metric monitors ECS memory utilization"
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
  for_each                        = { for idx, value in var.alerting_subscriptions : idx => value }
  topic_arn                       = aws_sns_topic.this.arn
  protocol                        = "email"
  endpoint                        = each.value
  depends_on                      = [aws_sns_topic.this]
}