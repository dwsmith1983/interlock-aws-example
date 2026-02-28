terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  # Uncomment after running bootstrap:
  # backend "s3" {
  #   bucket         = "medallion-interlock-terraform-state"
  #   key            = "medallion-pipeline/terraform.tfstate"
  #   region         = "ap-southeast-1"
  #   dynamodb_table = "medallion-interlock-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.table_name}-data-${data.aws_caller_identity.current.account_id}"

  # stream-router is separate to avoid a cycle: it depends on the SFN,
  # which depends on the other 4 Go Lambdas in this set.
  core_lambda_names = toset(["orchestrator", "evaluator", "trigger", "run-checker"])

  go_lambda_common_env = {
    TABLE_NAME                = aws_dynamodb_table.main.name
    SNS_TOPIC_ARN             = aws_sns_topic.alerts.arn
    ARCHETYPE_DIR             = "/opt/archetypes"
    READINESS_TTL             = var.readiness_ttl
    RETENTION_TTL             = var.retention_ttl
    CIRCUIT_BREAKER_THRESHOLD = var.circuit_breaker_threshold
    MAX_RERUNS_PER_DAY        = var.max_reruns_per_day
  }

  python_lambdas = {
    "custom-evaluator"  = { source_dir = "evaluator", timeout = 30 }
    "ingest-earthquake" = { source_dir = "ingest_earthquake", timeout = 60 }
    "ingest-crypto"     = { source_dir = "ingest_crypto", timeout = 60 }
    "pipeline-monitor"  = { source_dir = "pipeline_monitor", timeout = 60 }
    "dashboard-api"     = { source_dir = "dashboard_api", timeout = 30 }
  }

  glue_jobs = {
    "medallion-silver-earthquake"     = "silver_earthquake.py"
    "medallion-silver-crypto"         = "silver_crypto.py"
    "medallion-gold-earthquake"       = "gold_earthquake.py"
    "medallion-gold-crypto"           = "gold_crypto.py"
    "medallion-compact-observability" = "compact_observability.py"
  }

  eventbridge_rules = {
    "ingest-earthquake" = { rate_minutes = var.earthquake_rate_minutes }
    "ingest-crypto"     = { rate_minutes = var.crypto_rate_minutes }
  }

  ingest_lambda_names = toset(["ingest-earthquake", "ingest-crypto"])
}
