resource "aws_lambda_function" "telecom_generator" {
  function_name    = "${var.environment}-telecom-generator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "generator.handler.lambda_handler"
  memory_size      = var.generator_memory_mb
  timeout          = var.generator_timeout_s
  filename         = "${path.module}/../../build/telecom-generator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/telecom-generator.zip")
  role             = aws_iam_role.telecom_generator.arn

  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.telecom_data.id
    }
  }
}

resource "aws_iam_role" "telecom_generator" {
  name = "${var.environment}-telecom-generator-role"

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

resource "aws_iam_role_policy" "telecom_generator_s3" {
  name = "s3-put"
  role = aws_iam_role.telecom_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "s3:PutObject"
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.telecom_data.arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "telecom_generator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.telecom_generator.id

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
          aws_cloudwatch_log_group.telecom_generator.arn,
          "${aws_cloudwatch_log_group.telecom_generator.arn}:*"
        ]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "telecom_generator" {
  name              = "/aws/lambda/${var.environment}-telecom-generator"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_event_rule" "cdr" {
  name                = "${var.environment}-telecom-cdr-schedule"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_rule" "seq" {
  name                = "${var.environment}-telecom-seq-schedule"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_target" "cdr" {
  rule = aws_cloudwatch_event_rule.cdr.name
  arn  = aws_lambda_function.telecom_generator.arn

  input = jsonencode({
    stream       = "cdr"
    daily_target = var.cdr_daily_target
  })
}

resource "aws_cloudwatch_event_target" "seq" {
  rule = aws_cloudwatch_event_rule.seq.name
  arn  = aws_lambda_function.telecom_generator.arn

  input = jsonencode({
    stream       = "seq"
    daily_target = var.seq_daily_target
  })
}

resource "aws_lambda_permission" "cdr" {
  statement_id  = "AllowEventBridgeCDR"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.telecom_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cdr.arn
}

resource "aws_lambda_permission" "seq" {
  statement_id  = "AllowEventBridgeSEQ"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.telecom_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.seq.arn
}
