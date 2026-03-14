module "interlock" {
  source = "../../../interlock/deploy/terraform"

  environment    = var.environment
  dist_path      = "${path.module}/../../build/interlock"
  pipelines_path = ""
  tags           = var.tags

  lambda_memory_size   = 256
  log_retention_days   = var.log_retention_days
  enable_glue_trigger  = true
  glue_job_arns = [
    aws_glue_job.cdr_agg_hour.arn,
    aws_glue_job.cdr_agg_day.arn,
    aws_glue_job.seq_agg_hour.arn,
    aws_glue_job.seq_agg_day.arn,
  ]
  sfn_timeout_seconds  = 18000
  slack_bot_token      = var.slack_bot_token
  slack_channel_id     = var.slack_channel_id

  lambda_concurrency = {
    stream_router    = -1
    orchestrator     = -1
    sla_monitor      = -1
    watchdog         = -1
    event_sink       = -1
    alert_dispatcher = -1
  }
}

# Orchestrator needs permission to invoke audit Lambda directly
resource "aws_iam_role_policy" "interlock_audit_invoke" {
  name = "audit-lambda-invoke"
  role = "${var.environment}-interlock-orchestrator"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "lambda:InvokeFunction"
      Effect   = "Allow"
      Resource = aws_lambda_function.bronze_audit.arn
    }]
  })

  depends_on = [module.interlock]
}
