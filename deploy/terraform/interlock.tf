module "interlock" {
  source = "../../../interlock/deploy/terraform"

  environment    = var.environment
  dist_path      = "${path.module}/../../build/interlock"
  pipelines_path = ""
  tags           = var.tags

  lambda_memory_size   = 256
  log_retention_days   = var.log_retention_days
  enable_glue_trigger  = true
  sfn_timeout_seconds  = 18000
  slack_bot_token      = var.slack_bot_token
  slack_channel_id     = var.slack_channel_id
}

# Orchestrator needs permission to invoke audit Lambda via function URL
resource "aws_iam_role_policy" "interlock_audit_invoke" {
  name = "audit-lambda-invoke"
  role = "${var.environment}-interlock-orchestrator"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "lambda:InvokeFunctionUrl"
      Effect   = "Allow"
      Resource = aws_lambda_function.bronze_audit.arn
    }]
  })

  depends_on = [module.interlock]
}
