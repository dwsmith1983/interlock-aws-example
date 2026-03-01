variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Default tags applied to all resources"
  type        = map(string)
  default = {
    Project   = "interlock-aws-example"
    ManagedBy = "terraform"
  }
}

variable "generator_memory_mb" {
  description = "Memory allocation for the generator Lambda in MB"
  type        = number
  default     = 3008
}

variable "generator_timeout_s" {
  description = "Timeout for the generator Lambda in seconds"
  type        = number
  default     = 900
}

variable "cdr_daily_target" {
  description = "Daily target record count for the CDR stream"
  type        = number
  default     = 100000000
}

variable "seq_daily_target" {
  description = "Daily target record count for the SEQ stream"
  type        = number
  default     = 500000000
}

variable "data_retention_days" {
  description = "Number of days to retain generated data in S3"
  type        = number
  default     = 7
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 7
}
