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

# Bronze consumer
variable "phone_hash_salt" {
  description = "Salt for SHA-256 phone number hashing"
  type        = string
  sensitive   = true
}

variable "bronze_memory_mb" {
  description = "Memory allocation for the bronze consumer Lambda in MB"
  type        = number
  default     = 2048
}

variable "bronze_timeout_s" {
  description = "Timeout for the bronze consumer Lambda in seconds"
  type        = number
  default     = 300
}

# Glue
variable "glue_worker_type" {
  description = "Glue worker type for aggregation jobs"
  type        = string
  default     = "G.1X"
}

variable "glue_hourly_workers" {
  description = "Number of Glue workers for hourly aggregation jobs"
  type        = number
  default     = 2
}

variable "glue_daily_workers" {
  description = "Number of Glue workers for daily aggregation jobs"
  type        = number
  default     = 5
}

# Alerting
variable "slack_bot_token" {
  description = "Slack Bot API token for pipeline alerts (empty = logging only)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_channel_id" {
  description = "Slack channel ID for pipeline alerts"
  type        = string
  default     = ""
}
