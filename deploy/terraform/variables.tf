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

# Pipeline start date (YYYYMMDD) — first kick backfills from this date hour 00
variable "pipeline_start_date" {
  description = "Start date for pipeline schedules (YYYYMMDD). First ingestion backfills from this date."
  type        = string
  default     = "20260225"
}

# EventBridge ingestion rates
variable "earthquake_rate_minutes" {
  description = "USGS Earthquake ingestion interval (minutes)"
  type        = number
  default     = 20
}

variable "crypto_rate_minutes" {
  description = "CoinLore Crypto ingestion interval (minutes)"
  type        = number
  default     = 20
}

# Chaos testing
variable "chaos_enabled" {
  description = "Enable chaos testing Lambda and EventBridge rule"
  type        = bool
  default     = false
}

variable "chaos_rate_minutes" {
  description = "Chaos controller invocation interval (minutes)"
  type        = number
  default     = 20
}

# Optional trigger permission flags
variable "enable_glue_trigger" {
  description = "Grant Glue StartJobRun/GetJobRun to trigger Lambda"
  type        = bool
  default     = true
}

variable "watchdog_interval" {
  description = "EventBridge schedule expression for the watchdog Lambda"
  type        = string
  default     = "rate(5 minutes)"
}

variable "destroy_on_delete" {
  description = "Allow Terraform to destroy stateful resources (DynamoDB, S3)"
  type        = bool
  default     = true
}
