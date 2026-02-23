variable "project_name" {
  description = "Project name used as prefix for state resources"
  type        = string
  default     = "medallion-interlock"
}

variable "aws_region" {
  description = "AWS region for the state bucket and lock table"
  type        = string
  default     = "ap-southeast-1"
}
