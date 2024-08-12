resource "aws_cloudwatch_dashboard" "this" {
    dashboard_name = local.project_name
    dashboard_body = jsonencode(
      {
        widgets = [
            {
                type = "metric",
                properties = {
                    metrics = [[ "AWS/ApplicationELB", "RequestCount", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
                    sparkline = true,
                    view = "singleValue",
                    region = "eu-central-1",
                    period = 300,
                    stat = "Sum",
                    title = "Total number of requests"
                }
            },
            {
                type = "metric",
                properties = {
                    metrics = [[ "AWS/ApplicationELB", "RequestCount", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
                    view = "timeSeries",
                    region = "eu-central-1",
                    period = 1,
                    stat = "Sum",
                    title = "Total requests per seconds"
                }
            },
            {
                type  = "metric"
                properties = {
                    metrics = [[ "AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
                    view = "timeSeries",
                    stacked = false,
                    region = "eu-central-1",
                    title = "Target Response Time",
                }
            },
            {
                type  = "metric"
                properties = {
                    metrics = [
                        [ "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}" ],
                    ],
                    view = "timeSeries",
                    stacked = false,
                    region = "eu-central-1",
                    title = "Total number of 5XX errors in ELB",
                }
            },
            {
                type  = "metric"
                properties = {
                    metrics = [[ "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]],
                    view = "timeSeries",
                    stacked = false,
                    region = "eu-central-1",
                    title = "Total number of 5XX errors in Target",
                }
            },
            {
                type = "metric",
                properties = {
                    metrics = [[ "AWS/ApplicationELB", "HTTPCode_Target_2XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]]
                    stacked = false,
                    view = "timeSeries",
                    region = "eu-central-1",
                    period = 60,
                    stat = "Sum",
                    title = "Success requests per seconds in Target (2XXs)"
                }
            },
             {
                type = "metric",
                properties = {
                    metrics = [
                        [ "AWS/ApplicationELB", "AWS/ApplicationELB/HTTPCode_ELB_4XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"],
                        [ "AWS/ApplicationELB", "AWS/ApplicationELB/HTTPCode_ELB_2XX_Count", "LoadBalancer", "${data.aws_lb.lb.arn_suffix}"]
                    ]
                    sparkline = true,
                    view = "timeSeries",
                    region = "eu-central-1",
                    period = 60,
                    stat = "Sum",
                    title = "Success requests per seconds LB (2XXs and 4XXs)"
                }
            },
             {
                type = "metric",
                properties = {
                    metrics = [
                        [ { "id": "expr1m0", "label": "p2p_schedule_api_of_carriers_cluster", "expression": "mm1m0 * 100 / mm0m0", "stat": "Average", "region": "eu-central-1" } ],
                        [ "ECS/ContainerInsights", "CpuReserved", "ClusterName", "p2p_schedule_api_of_carriers_cluster", { "id": "mm0m0", "visible": false, "stat": "Sum", "region": "eu-central-1" } ],
                        [ ".", "CpuUtilized", ".", ".", { "id": "mm1m0", "visible": false, "stat": "Sum", "region": "eu-central-1" } ]
                    ]
                    sparkline = true,
                    view = "timeSeries",
                    region = "eu-central-1",
                    period = 60,
                    title = "CPU utilization"
                    yAxis = {
                    "left": {
                        "min": 0,
                        "showUnits": false,
                        "label": "Percent"
                    }
                },
                }
            },
             {
                type = "metric",
                properties = {
                    metrics = [
                        [ { "id": "expr1m0", "label": "p2p_schedule_api_of_carriers_cluster", "expression": "mm1m0 * 100 / mm0m0", "stat": "Average", "region": "eu-central-1" } ],
                        [ "ECS/ContainerInsights", "MemoryReserved", "ClusterName", "p2p_schedule_api_of_carriers_cluster", { "id": "mm0m0", "visible": false, "stat": "Sum", "region": "eu-central-1" } ],
                        [ ".", "MemoryUtilized", ".", ".", { "id": "mm1m0", "visible": false, "stat": "Sum", "region": "eu-central-1" } ]
                    ]
                    sparkline = true,
                    view = "timeSeries",
                    region = "eu-central-1",
                    period = 60,
                    title = "Memory Utilization"
                    yAxis = {
                    "left": {
                        "min": 0,
                        "showUnits": false,
                        "label": "Percent"
                    }
                },
                }
            },
        ]
      }
    )
}