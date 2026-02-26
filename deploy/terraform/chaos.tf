# =============================================================================
# Chaos Controller Lambda + EventBridge + IAM
# Conditionally deployed when var.chaos_enabled = true
# =============================================================================

# --- Package chaos controller ---
data "archive_file" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  type        = "zip"
  source_dir  = "${path.module}/${var.python_lambdas_dir}/chaos_controller"
  output_path = "${path.module}/.build/py-chaos-controller.zip"
}

# --- Lambda function ---
resource "aws_lambda_function" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  function_name = "${var.table_name}-chaos-controller"
  role          = aws_iam_role.chaos_controller[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 300

  filename         = data.archive_file.chaos_controller[0].output_path
  source_code_hash = data.archive_file.chaos_controller[0].output_base64sha256

  environment {
    variables = {
      TABLE_NAME        = aws_dynamodb_table.main.name
      BUCKET_NAME       = aws_s3_bucket.data.id
      STATE_MACHINE_ARN = aws_sfn_state_machine.pipeline.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.chaos_controller]
}

# --- CloudWatch log group ---
resource "aws_cloudwatch_log_group" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  name              = "/aws/lambda/${var.table_name}-chaos-controller"
  retention_in_days = var.log_retention_days
}

# --- EventBridge rule (every N minutes) ---
resource "aws_cloudwatch_event_rule" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  name                = "${var.table_name}-chaos-controller"
  schedule_expression = "rate(${var.chaos_rate_minutes} ${var.chaos_rate_minutes == 1 ? "minute" : "minutes"})"
}

resource "aws_cloudwatch_event_target" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  rule = aws_cloudwatch_event_rule.chaos_controller[0].name
  arn  = aws_lambda_function.chaos_controller[0].arn
}

resource "aws_lambda_permission" "chaos_controller_eventbridge" {
  count = var.chaos_enabled ? 1 : 0

  statement_id  = "AllowEventBridge-chaos-controller"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chaos_controller[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.chaos_controller[0].arn
}

# =============================================================================
# Chaos Controller IAM Role
# Needs: DynamoDB RW, S3 RW, SFN ListExecutions/StopExecution,
#         Lambda PutFunctionConcurrency/DeleteFunctionConcurrency/ListFunctions,
#         Glue GetJobRuns/BatchStopJobRun
# =============================================================================

resource "aws_iam_role" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  name               = "${var.table_name}-chaos-controller"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "chaos_controller_basic" {
  count = var.chaos_enabled ? 1 : 0

  role       = aws_iam_role.chaos_controller[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "chaos_controller" {
  count = var.chaos_enabled ? 1 : 0

  name = "chaos-controller-policy"
  role = aws_iam_role.chaos_controller[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
          "s3:GetBucketLocation", "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*",
        ]
      },
      {
        Sid    = "StepFunctionsChaos"
        Effect = "Allow"
        Action = [
          "states:ListExecutions",
          "states:StopExecution",
        ]
        Resource = [aws_sfn_state_machine.pipeline.arn]
      },
      {
        Sid    = "LambdaThrottle"
        Effect = "Allow"
        Action = [
          "lambda:PutFunctionConcurrency",
          "lambda:DeleteFunctionConcurrency",
          "lambda:ListFunctions",
        ]
        Resource = ["*"]
      },
      {
        Sid    = "GlueKill"
        Effect = "Allow"
        Action = [
          "glue:GetJobRuns",
          "glue:BatchStopJobRun",
        ]
        Resource = [for name, _ in local.glue_jobs : aws_glue_job.etl[name].arn]
      },
    ]
  })
}
