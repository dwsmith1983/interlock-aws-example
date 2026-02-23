variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "ap-southeast-1"
}

variable "table_name" {
  description = "DynamoDB table name (also used as resource name prefix)"
  type        = string
  default     = "medallion-interlock"
}

variable "bucket_name" {
  description = "S3 data bucket name. Defaults to {table_name}-data-{account_id} if empty."
  type        = string
  default     = ""
}

# Lambda settings
variable "lambda_memory_size" {
  description = "Memory (MB) for Go Lambda functions"
  type        = number
  default     = 128
}

variable "lambda_timeout" {
  description = "Timeout (seconds) for Go Lambda functions"
  type        = number
  default     = 300
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

# Interlock settings
variable "readiness_ttl" {
  description = "TTL for readiness records"
  type        = string
  default     = "1h"
}

variable "retention_ttl" {
  description = "TTL for retention records"
  type        = string
  default     = "168h"
}

variable "evaluator_base_url" {
  description = "Base URL for the HTTP evaluator. Auto-wired to API Gateway if empty."
  type        = string
  default     = ""
}

# Paths (relative to this module)
variable "lambda_dist_dir" {
  description = "Directory containing built Go Lambda binaries"
  type        = string
  default     = "../dist/lambda"
}

variable "asl_path" {
  description = "Path to Step Function ASL definition"
  type        = string
  default     = "../statemachine.asl.json"
}

variable "python_lambdas_dir" {
  description = "Directory containing Python Lambda source"
  type        = string
  default     = "../../lambdas"
}

variable "glue_scripts_dir" {
  description = "Directory containing Glue PySpark scripts"
  type        = string
  default     = "../../glue"
}

variable "archetypes_dir" {
  description = "Directory containing archetype YAML files"
  type        = string
  default     = "../../archetypes"
}

# Glue settings
variable "glue_worker_type" {
  description = "Glue worker type (G.1X is minimum for batch ETL)"
  type        = string
  default     = "G.1X"
}

variable "glue_number_workers" {
  description = "Number of Glue workers per job (minimum 2 for Spark)"
  type        = number
  default     = 2
}

variable "glue_timeout_minutes" {
  description = "Glue job timeout in minutes"
  type        = number
  default     = 30
}

# EventBridge ingestion rates
variable "gharchive_rate_minutes" {
  description = "GH Archive ingestion interval (minutes)"
  type        = number
  default     = 60
}

variable "openmeteo_rate_minutes" {
  description = "Open-Meteo ingestion interval (minutes)"
  type        = number
  default     = 60
}

# Optional trigger permission flags
variable "enable_glue_trigger" {
  description = "Grant Glue StartJobRun/GetJobRun to trigger Lambda"
  type        = bool
  default     = true
}

variable "destroy_on_delete" {
  description = "Allow Terraform to destroy stateful resources (DynamoDB, S3)"
  type        = bool
  default     = true
}
