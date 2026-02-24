# =============================================================================
# Watchdog Lambda — detects missed pipeline schedules
# Invoked by EventBridge on a regular interval (not part of the Step Function)
# =============================================================================

# --- IAM ---

resource "aws_iam_role" "watchdog" {
  name               = "${var.table_name}-watchdog"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "watchdog_basic" {
  role       = aws_iam_role.watchdog.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "watchdog" {
  name = "watchdog-policy"
  role = aws_iam_role.watchdog.id

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
        Sid      = "SNSPublish"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      },
    ]
  })
}

# --- Lambda ---

data "archive_file" "watchdog" {
  type        = "zip"
  source_file = "${path.module}/${var.lambda_dist_dir}/watchdog/bootstrap"
  output_path = "${path.module}/.build/watchdog.zip"
}

resource "aws_cloudwatch_log_group" "watchdog" {
  name              = "/aws/lambda/${var.table_name}-watchdog"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "watchdog" {
  function_name = "${var.table_name}-watchdog"
  role          = aws_iam_role.watchdog.arn
  handler       = "bootstrap"
  runtime       = "provided.al2023"
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  filename         = data.archive_file.watchdog.output_path
  source_code_hash = data.archive_file.watchdog.output_base64sha256

  layers = [aws_lambda_layer_version.archetypes.arn]

  environment {
    variables = local.go_lambda_common_env
  }

  depends_on = [aws_cloudwatch_log_group.watchdog]
}

# --- EventBridge ---

resource "aws_cloudwatch_event_rule" "watchdog" {
  name                = "${var.table_name}-watchdog"
  description         = "Invoke watchdog Lambda to detect missed pipeline schedules"
  schedule_expression = var.watchdog_interval
}

resource "aws_cloudwatch_event_target" "watchdog" {
  rule = aws_cloudwatch_event_rule.watchdog.name
  arn  = aws_lambda_function.watchdog.arn
}

resource "aws_lambda_permission" "watchdog_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watchdog.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.watchdog.arn
}
