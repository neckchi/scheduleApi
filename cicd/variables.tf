variable "environment" {
  type    = string
  default = "dev"
}
variable "AWS_PROFILE_ID" {
  type = string
}
variable "AWS_REGION" {
  type = string
}
variable "vpc_id" {
  type = string
}
variable "subnet_ids" {
  type = list(string)
}
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "image" {
  type    = string
  default = "p2p-schedule-api-of-carriers"
}
variable "project_name" {
  type = string
}
variable "project_name_abreb" {
  type = string
}
variable "sg_inboud_rules_cidrs" {
  type = list(string)
}
variable "sg_outboud_rules_cidrs" {
  type = list(string)
}
# ECS Service
variable "ecs_service_desired_count" {
  type = number
}
# Auto Scaling settings
variable "autoscaling_settings_min_capacity" {
  type = number
}
variable "autoscaling_settings_max_capacity" {
  type = number
}
variable "autoscaling_settings_cpu_target_value" {
  type = number
}
variable "autoscaling_settings_memory_target_value" {
  type = number
}
variable "autoscaling_settings_scale_out_cooldown" {
  type = number
}
variable "autoscaling_settings_scale_in_cooldown" {
  type = number
}
# ECS Task
variable "ecs_task_memory" {
  type = number
}
variable "ecs_task_cpu" {
  type = number
}
variable "ecs_task_log_retention_days" {
  type = number
}
variable "ecs_task_container_definitions_cpu" {
  type = number
}
variable "ecs_task_container_definitions_memory" {
  type = number
}
variable "ecs_task_container_definitions_image" {
  type = string
}
# LB Listner rule
variable "lb_listener_arn" {
  type = string
}
# Secret Configuration
variable "api_secret_config" {
  type = string
}
variable "static_variables" {
  type        = map(string)
  description = "Map of variables and static values to add to the task definition"
  default     = {}
}
