provider "aws" {
  region = local.AWS_REGION
  # default_tags {
  #   tags = module.tagging.resource_tags
  # }
}
