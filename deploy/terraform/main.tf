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
    TABLE_NAME    = aws_dynamodb_table.main.name
    SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
    ARCHETYPE_DIR = "/opt/archetypes"
    READINESS_TTL = var.readiness_ttl
    RETENTION_TTL = var.retention_ttl
  }

  python_lambdas = {
    "custom-evaluator" = { source_dir = "evaluator", timeout = 30 }
    "ingest-gharchive" = { source_dir = "ingest_gharchive", timeout = 300 }
    "ingest-openmeteo" = { source_dir = "ingest_openmeteo", timeout = 60 }
  }

  glue_jobs = {
    "medallion-silver-gharchive" = "silver_gharchive.py"
    "medallion-silver-openmeteo" = "silver_openmeteo.py"
    "medallion-gold-gharchive"   = "gold_gharchive.py"
    "medallion-gold-openmeteo"   = "gold_openmeteo.py"
  }

  eventbridge_rules = {
    "ingest-gharchive" = { rate_minutes = var.gharchive_rate_minutes }
    "ingest-openmeteo" = { rate_minutes = var.openmeteo_rate_minutes }
  }

  ingest_lambda_names = toset(["ingest-gharchive", "ingest-openmeteo"])
}
