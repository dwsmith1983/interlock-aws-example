# ---------- Daily Sensor: EventBridge -> Lambda ----------
# Fires on JOB_COMPLETED from silver hourly pipelines to gate daily SFN.

# ---- Lambda function ----

resource "aws_lambda_function" "daily_sensor" {
  function_name    = "${var.environment}-daily-sensor"
  role             = aws_iam_role.daily_sensor.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = 128
  timeout          = 30
  filename         = "${path.module}/../../build/daily-sensor.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/daily-sensor.zip")

  environment {
    variables = {
      INTERLOCK_CONTROL_TABLE = module.interlock.control_table_name
    }
  }

  tags = var.tags
}

# ---- EventBridge rule: JOB_COMPLETED from silver hourly pipelines ----

resource "aws_cloudwatch_event_rule" "daily_sensor" {
  name           = "${var.environment}-daily-sensor-trigger"
  event_bus_name = module.interlock.event_bus_name

  event_pattern = jsonencode({
    source      = ["interlock"]
    detail-type = ["JOB_COMPLETED"]
    detail = {
      pipelineId = [{ prefix = "silver-" }]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "daily_sensor" {
  rule           = aws_cloudwatch_event_rule.daily_sensor.name
  event_bus_name = module.interlock.event_bus_name
  arn            = aws_lambda_function.daily_sensor.arn
}

resource "aws_lambda_permission" "daily_sensor_eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_sensor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_sensor.arn
}

# ---- IAM role ----

resource "aws_iam_role" "daily_sensor" {
  name = "${var.environment}-interlock-daily-sensor"

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

resource "aws_iam_role_policy_attachment" "daily_sensor_basic" {
  role       = aws_iam_role.daily_sensor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "daily_sensor_dynamodb" {
  name = "control-table-write"
  role = aws_iam_role.daily_sensor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
      ]
      Resource = module.interlock.control_table_arn
    }]
  })
}

# ---- CloudWatch log group ----

resource "aws_cloudwatch_log_group" "daily_sensor" {
  name              = "/aws/lambda/${var.environment}-daily-sensor"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
