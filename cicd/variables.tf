variable "environment" {
  type    = string
  default = "dev"
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
variable "sg_inboud_rules_cidrs" {
  type = list(string)
}
variable "sg_outboud_rules_cidrs" {
  type = list(string)
}
# ECS Service
variable "ecs_service_desired_count" {
  type        = number
  description = "ECS autosacling desired capacity"
}
# Auto Scaling settings
variable "autoscaling_settings_min_capacity" {
  type        = number
  description = "ECS autosacling min capacity"
}
variable "autoscaling_settings_max_capacity" {
  type        = number
  description = "ECS autosacling max capacity"
}
variable "autoscaling_settings_cpu_target_value" {
  type        = number
  description = "ECS autosacling cpu target"
}
variable "autoscaling_settings_memory_target_value" {
  type        = number
  description = "ECS autosacling memory target"
}
variable "autoscaling_settings_scale_out_cooldown" {
  type        = number
  description = "ECS autosacling ou cooldown"
}
variable "autoscaling_settings_scale_in_cooldown" {
  type        = number
  description = "ECS autosacling in cooldown"
}
# ECS Task
variable "ecs_task_memory" {
  type        = number
  description = "ECS service memory"
}
variable "ecs_task_cpu" {
  type        = number
  description = "ECS service cpu"
}
variable "ecs_task_log_retention_days" {
  type        = number
  description = "ECS task log retention in days"
}
variable "ecs_task_container_definitions_cpu" {
  type        = number
  description = "ECS task cpu"
}
variable "ecs_task_container_definitions_memory" {
  type        = number
  description = "ECS task container memory"
}
variable "ecs_task_container_definitions_image" {
  type        = string
  description = "ECS task image name"
}
# Secret Configuration
variable "api_secret_config" {
  type        = string
  description = "Secret for app environment variables configuration"
}
variable "static_variables" {
  type        = map(string)
  description = "Map of variables and static values to add to the task definition"
  default     = {}
}
