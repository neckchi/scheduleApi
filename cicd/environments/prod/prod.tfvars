AWS_PROFILE_ID         = "217604659377"
AWS_REGION             = "eu-central-1"
vpc_id                 = "vpc-0d30ee809b50ad14b"
subnet_ids             = ["subnet-06e78569a6c0b1762", "subnet-0cd5d566cfd5bc499", "subnet-0119e1034e4fce205"]
project_name           = "p2p-schedule-api-of-carriers"
project_name_abreb     = "p2papicarriers"
sg_inboud_rules_cidrs  = ["10.0.0.0/8", "10.59.226.0/24"]
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
ecs_task_container_definitions_image  = "217604659377.dkr.ecr.eu-central-1.amazonaws.com/p2p-schedule-api-of-carriers"
# LB listner rule
lb_listener_arn = "**TBD**"
# Secret Configuration
api_secret_config = "**TBD**"
# Static Variables
static_variables = {
  ENV_TEST = "VALUE_ENV_TEST"
}
