terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# --- Lambda Function ---

resource "aws_lambda_function" "chaos_controller" {
  function_name    = "${var.environment}-chaos-controller"
  runtime          = "provided.al2023"
  architectures    = ["arm64"]
  handler          = "bootstrap"
  memory_size      = 512
  timeout          = 300
  filename         = "${path.module}/../../build/chaos/chaos-controller.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/chaos/chaos-controller.zip")
  role             = aws_iam_role.chaos_controller.arn

  environment {
    variables = {
      S3_BUCKET               = var.s3_bucket_name
      SCENARIO_PREFIX         = "chaos/scenarios/"
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      INTERLOCK_EVENTS_TABLE  = var.interlock_events_table_name
      MAX_SEVERITY            = var.chaos_max_severity
    }
  }

  tags = var.tags
}

# --- CloudWatch Logs ---

resource "aws_cloudwatch_log_group" "chaos_controller" {
  name              = "/aws/lambda/${var.environment}-chaos-controller"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# --- IAM Role ---

resource "aws_iam_role" "chaos_controller" {
  name = "${var.environment}-chaos-controller-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# --- IAM Policies ---

resource "aws_iam_role_policy" "chaos_controller_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.chaos_controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect = "Allow"
        Resource = [
          aws_cloudwatch_log_group.chaos_controller.arn,
          "${aws_cloudwatch_log_group.chaos_controller.arn}:*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "chaos_controller_s3" {
  name = "s3-read-write"
  role = aws_iam_role.chaos_controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Effect = "Allow"
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "chaos_controller_dynamodb" {
  name = "dynamodb-read-write"
  role = aws_iam_role.chaos_controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchWriteItem"
        ]
        Effect = "Allow"
        Resource = [
          var.interlock_control_table_arn,
          var.interlock_events_table_arn
        ]
      }
    ]
  })
}

# --- EventBridge Schedule ---

resource "aws_cloudwatch_event_rule" "chaos_schedule" {
  name                = "${var.environment}-chaos-schedule"
  schedule_expression = var.chaos_schedule_rate
  state               = var.enable_chaos ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "chaos_schedule" {
  rule = aws_cloudwatch_event_rule.chaos_schedule.name
  arn  = aws_lambda_function.chaos_controller.arn

  input = jsonencode({})
}

resource "aws_lambda_permission" "chaos_eventbridge" {
  statement_id  = "AllowEventBridgeChaos"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chaos_controller.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.chaos_schedule.arn
}
