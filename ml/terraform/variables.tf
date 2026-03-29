variable "environment" {
  description = "Deployment environment name"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 data bucket"
  type        = string
}

variable "s3_bucket_arn" {
  description = "ARN of the S3 data bucket"
  type        = string
}

variable "interlock_control_table_name" {
  description = "Name of the Interlock control DynamoDB table"
  type        = string
}

variable "interlock_control_table_arn" {
  description = "ARN of the Interlock control DynamoDB table"
  type        = string
}

variable "enable_ml" {
  description = "Whether the ML pipeline is enabled"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Default tags applied to all resources"
  type        = map(string)
  default = {
    Project   = "interlock-aws-example"
    Module    = "ml"
    ManagedBy = "terraform"
  }
}
