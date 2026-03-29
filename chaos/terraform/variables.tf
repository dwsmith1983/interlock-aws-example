variable "environment" {
  description = "Deployment environment name"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 data bucket (for scenario files and data mutations)"
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

variable "interlock_events_table_name" {
  description = "Name of the Interlock events DynamoDB table"
  type        = string
}

variable "interlock_events_table_arn" {
  description = "ARN of the Interlock events DynamoDB table"
  type        = string
}

variable "chaos_schedule_rate" {
  description = "EventBridge schedule rate for probabilistic chaos runs"
  type        = string
  default     = "rate(20 minutes)"
}

variable "chaos_max_severity" {
  description = "Maximum chaos severity level (low, moderate, severe, critical)"
  type        = string
  default     = "moderate"
}

variable "enable_chaos" {
  description = "Whether the chaos schedule is enabled"
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
    Module    = "chaos"
    ManagedBy = "terraform"
  }
}
