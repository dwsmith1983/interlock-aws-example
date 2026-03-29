terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# --- Generator Lambda ---

resource "aws_lambda_function" "iot_generator" {
  function_name    = "${var.environment}-iot-generator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 256
  timeout          = 60
  filename         = "${path.module}/../../build/iot-generator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/iot-generator.zip")
  role             = aws_iam_role.iot_generator.arn

  environment {
    variables = {
      S3_BUCKET   = var.s3_bucket_name
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "iot_generator" {
  name = "${var.environment}-iot-generator-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "iot_generator_s3" {
  name = "s3-write"
  role = aws_iam_role.iot_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "s3:PutObject"
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "iot_generator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.iot_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.iot_generator.arn,
        "${aws_cloudwatch_log_group.iot_generator.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "iot_generator" {
  name              = "/aws/lambda/${var.environment}-iot-generator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Generator schedule: every 5 minutes.
resource "aws_cloudwatch_event_rule" "iot_generator" {
  name                = "${var.environment}-iot-generator-schedule"
  schedule_expression = "rate(5 minutes)"
  state               = var.enable_iot ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "iot_generator" {
  rule = aws_cloudwatch_event_rule.iot_generator.name
  arn  = aws_lambda_function.iot_generator.arn
}

resource "aws_lambda_permission" "iot_generator_eventbridge" {
  statement_id  = "AllowEventBridgeIoTGen"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.iot_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.iot_generator.arn
}

# --- Consumer Lambda ---

resource "aws_lambda_function" "iot_consumer" {
  function_name    = "${var.environment}-iot-consumer"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 512
  timeout          = 120
  filename         = "${path.module}/../../build/iot-consumer.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/iot-consumer.zip")
  role             = aws_iam_role.iot_consumer.arn

  environment {
    variables = {
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      S3_BUCKET               = var.s3_bucket_name
      PIPELINE_ID             = "iot-factory"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "iot_consumer" {
  name = "${var.environment}-iot-consumer-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "iot_consumer_s3" {
  name = "s3-read"
  role = aws_iam_role.iot_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy" "iot_consumer_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.iot_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "iot_consumer_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.iot_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.iot_consumer.arn,
        "${aws_cloudwatch_log_group.iot_consumer.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "iot_consumer" {
  name              = "/aws/lambda/${var.environment}-iot-consumer"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# S3 notification triggers consumer via Lambda permission.
resource "aws_s3_bucket_notification" "iot_readings" {
  count  = var.enable_iot ? 1 : 0
  bucket = var.s3_bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.iot_consumer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "iot/readings/"
    filter_suffix       = ".jsonl"
  }
}

resource "aws_lambda_permission" "iot_consumer_s3" {
  statement_id  = "AllowS3InvokeIoTConsumer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.iot_consumer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.s3_bucket_arn
}

# --- Aggregator Lambda ---

resource "aws_lambda_function" "iot_aggregator" {
  function_name    = "${var.environment}-iot-aggregator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 256
  timeout          = 120
  filename         = "${path.module}/../../build/iot-aggregator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/iot-aggregator.zip")
  role             = aws_iam_role.iot_aggregator.arn

  environment {
    variables = {
      S3_BUCKET   = var.s3_bucket_name
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "iot_aggregator" {
  name = "${var.environment}-iot-aggregator-role"
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "iot_aggregator_s3" {
  name = "s3-read-write"
  role = aws_iam_role.iot_aggregator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy" "iot_aggregator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.iot_aggregator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.iot_aggregator.arn,
        "${aws_cloudwatch_log_group.iot_aggregator.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "iot_aggregator" {
  name              = "/aws/lambda/${var.environment}-iot-aggregator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
