terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# --- Kinesis Stream ---

resource "aws_kinesis_stream" "banking_transactions" {
  name             = "${var.environment}-banking-transactions"
  shard_count      = 1
  retention_period = 24

  tags = var.tags
}

# --- Generator Lambda ---

resource "aws_lambda_function" "banking_generator" {
  function_name    = "${var.environment}-banking-generator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "banking/generator/handler.lambda_handler"
  memory_size      = 256
  timeout          = 60
  filename         = "${path.module}/../../build/banking-generator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/banking-generator.zip")
  role             = aws_iam_role.banking_generator.arn

  environment {
    variables = {
      KINESIS_STREAM_NAME = aws_kinesis_stream.banking_transactions.name
      BATCH_SIZE          = "100"
      COB_HOUR            = "17"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "banking_generator" {
  name = "${var.environment}-banking-generator-role"
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

resource "aws_iam_role_policy" "banking_generator_kinesis" {
  name = "kinesis-put"
  role = aws_iam_role.banking_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["kinesis:PutRecord", "kinesis:PutRecords"]
      Effect   = "Allow"
      Resource = aws_kinesis_stream.banking_transactions.arn
    }]
  })
}

resource "aws_iam_role_policy" "banking_generator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.banking_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.banking_generator.arn,
        "${aws_cloudwatch_log_group.banking_generator.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "banking_generator" {
  name              = "/aws/lambda/${var.environment}-banking-generator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Generator schedule: every 5 minutes during business hours.
resource "aws_cloudwatch_event_rule" "banking_generator" {
  name                = "${var.environment}-banking-generator-schedule"
  schedule_expression = "rate(5 minutes)"
  state               = var.enable_banking ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "banking_generator" {
  rule = aws_cloudwatch_event_rule.banking_generator.name
  arn  = aws_lambda_function.banking_generator.arn
}

resource "aws_lambda_permission" "banking_generator_eventbridge" {
  statement_id  = "AllowEventBridgeBankingGen"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.banking_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.banking_generator.arn
}

# --- Consumer Lambda ---

resource "aws_lambda_function" "banking_consumer" {
  function_name    = "${var.environment}-banking-consumer"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "banking/consumer/handler.lambda_handler"
  memory_size      = 512
  timeout          = 120
  filename         = "${path.module}/../../build/banking-consumer.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/banking-consumer.zip")
  role             = aws_iam_role.banking_consumer.arn

  environment {
    variables = {
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      OUTPUT_BUCKET           = var.s3_bucket_name
      COB_HOUR                = "17"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "banking_consumer" {
  name = "${var.environment}-banking-consumer-role"
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

resource "aws_iam_role_policy" "banking_consumer_kinesis" {
  name = "kinesis-read"
  role = aws_iam_role.banking_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "kinesis:GetRecords",
        "kinesis:GetShardIterator",
        "kinesis:DescribeStream",
        "kinesis:DescribeStreamSummary",
        "kinesis:ListShards"
      ]
      Effect   = "Allow"
      Resource = aws_kinesis_stream.banking_transactions.arn
    }]
  })
}

resource "aws_iam_role_policy" "banking_consumer_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.banking_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "banking_consumer_s3" {
  name = "s3-write"
  role = aws_iam_role.banking_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "s3:PutObject"
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "banking_consumer_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.banking_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.banking_consumer.arn,
        "${aws_cloudwatch_log_group.banking_consumer.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "banking_consumer" {
  name              = "/aws/lambda/${var.environment}-banking-consumer"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Kinesis event source mapping for consumer.
resource "aws_lambda_event_source_mapping" "banking_consumer" {
  event_source_arn  = aws_kinesis_stream.banking_transactions.arn
  function_name     = aws_lambda_function.banking_consumer.arn
  starting_position = "LATEST"
  batch_size        = 100

  enabled = var.enable_banking
}

# --- Aggregator Lambda ---

resource "aws_lambda_function" "banking_aggregator" {
  function_name    = "${var.environment}-banking-aggregator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "banking/aggregator/handler.lambda_handler"
  memory_size      = 256
  timeout          = 120
  filename         = "${path.module}/../../build/banking-aggregator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/banking-aggregator.zip")
  role             = aws_iam_role.banking_aggregator.arn

  environment {
    variables = {
      OUTPUT_BUCKET = var.s3_bucket_name
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "banking_aggregator" {
  name = "${var.environment}-banking-aggregator-role"
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

resource "aws_iam_role_policy" "banking_aggregator_s3" {
  name = "s3-read-write"
  role = aws_iam_role.banking_aggregator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy" "banking_aggregator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.banking_aggregator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.banking_aggregator.arn,
        "${aws_cloudwatch_log_group.banking_aggregator.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "banking_aggregator" {
  name              = "/aws/lambda/${var.environment}-banking-aggregator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
