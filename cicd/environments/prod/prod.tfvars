environment            = "prod"
vpc_id                 = "vpc-0bb5090d03b1399b5"
subnet_ids             = ["subnet-032b981f1eb393c1b", "subnet-0543bea34053855f3", "subnet-0f46554659571c7c0"]
sg_inboud_rules_cidrs  = ["10.0.0.0/8", "10.59.225.0/24"]
sg_outboud_rules_cidrs = ["0.0.0.0/0"]
# ECS Service
ecs_service_desired_count = 1
# Auto Scaling settings
autoscaling_settings_min_capacity        = 1
autoscaling_settings_max_capacity        = 2
autoscaling_settings_cpu_target_value    = 2
autoscaling_settings_memory_target_value = 1024
autoscaling_settings_scale_out_cooldown  = 10
autoscaling_settings_scale_in_cooldown   = 10
# ECS Task
ecs_task_memory                       = 1024
ecs_task_cpu                          = 512
ecs_task_log_retention_days           = 7
ecs_task_container_definitions_cpu    = 1
ecs_task_container_definitions_memory = 1024
ecs_task_container_definitions_image  = "934536729814.dkr.ecr.eu-central-1.amazonaws.com/p2p-schedule-api-of-carriers"
# Secret Configuration
api_secret_config = "**TBD**"
# Static Variables
static_variables = {
  HTTP_PROXY  = "http://proxy.eu-central-1.aws.int.kn:80"
  HTTPS_PROXY = "http://proxy.eu-central-1.aws.int.kn:80"
  http_proxy  = "http://proxy.eu-central-1.aws.int.kn:80"
  https_proxy = "http://proxy.eu-central-1.aws.int.kn:80"
  NO_PROXY    = "172.20.0.0/16,localhost,127.0.0.1,10.59.244.0/25,169.254.169.254,.internal,s3.amazonaws.com,.s3.eu-central-1.amazonaws.com,api.ecr.eu-central-1.amazonaws.com,.dkr.ecr.eu-central-1.amazonaws.com,.ec2.eu-central-1.amazonaws.com,169.254.170.2,.int.kn,.eks.amazonaws.com,.cluster.local"
  no_proxy    = "172.20.0.0/16,localhost,127.0.0.1,10.59.244.0/25,169.254.169.254,.internal,s3.amazonaws.com,.s3.eu-central-1.amazonaws.com,api.ecr.eu-central-1.amazonaws.com,.dkr.ecr.eu-central-1.amazonaws.com,.ec2.eu-central-1.amazonaws.com,169.254.170.2,.int.kn,.eks.amazonaws.com,.cluster.local"
}
