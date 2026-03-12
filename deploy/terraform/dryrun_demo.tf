# ---------- Dry Run Demo: EventBridge -> Lambda ----------
# Simulates weather station data arriving every 10 minutes.
# Updates interlock sensors for dry run observation (never triggers SFN).

# ---- Lambda function ----

resource "aws_lambda_function" "dryrun_demo" {
  function_name    = "${var.environment}-dryrun-demo"
  role             = aws_iam_role.dryrun_demo.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 128
  timeout          = 30
  filename         = "${path.module}/../../build/dryrun-demo.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/dryrun-demo.zip")

  environment {
    variables = {
      INTERLOCK_CONTROL_TABLE = module.interlock.control_table_name
      S3_BUCKET               = aws_s3_bucket.telecom_data.id
    }
  }

  tags = var.tags
}

# ---- EventBridge rule: every 10 minutes ----
# Runs on the default event bus (schedule-based), not the interlock custom bus.

resource "aws_cloudwatch_event_rule" "dryrun_demo" {
  name                = "${var.environment}-dryrun-demo-schedule"
  schedule_expression = "rate(10 minutes)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "dryrun_demo" {
  rule = aws_cloudwatch_event_rule.dryrun_demo.name
  arn  = aws_lambda_function.dryrun_demo.arn
}

resource "aws_lambda_permission" "dryrun_demo_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dryrun_demo.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dryrun_demo.arn
}

# ---- IAM role ----

resource "aws_iam_role" "dryrun_demo" {
  name = "${var.environment}-interlock-dryrun-demo"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "dryrun_demo_basic" {
  role       = aws_iam_role.dryrun_demo.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dryrun_demo_dynamodb" {
  name = "control-table-readwrite"
  role = aws_iam_role.dryrun_demo.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
      ]
      Resource = module.interlock.control_table_arn
    }]
  })
}

# Demo data writes to the dryrun-demo/* prefix in the shared telecom_data bucket.
# Existing triggers pattern-match on cdr/ and seq/ prefixes only, so no fan-out interference.
resource "aws_iam_role_policy" "dryrun_demo_s3" {
  name = "s3-write"
  role = aws_iam_role.dryrun_demo.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${aws_s3_bucket.telecom_data.arn}/dryrun-demo/*"
    }]
  })
}

# ---- CloudWatch log group ----

resource "aws_cloudwatch_log_group" "dryrun_demo" {
  name              = "/aws/lambda/${var.environment}-dryrun-demo"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
