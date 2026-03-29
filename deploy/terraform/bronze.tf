# Bronze consumer Lambda — reads raw S3 files from Kinesis, writes Delta Lake
resource "aws_lambda_function" "bronze_consumer" {
  function_name    = "${var.environment}-bronze-consumer"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "bronze_consumer.handler.lambda_handler"
  memory_size      = var.bronze_memory_mb
  timeout          = var.bronze_timeout_s
  filename         = "${path.module}/../../build/bronze-consumer.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/bronze-consumer.zip")
  role             = aws_iam_role.bronze_consumer.arn

  layers = [aws_lambda_layer_version.delta_lake.arn]

  environment {
    variables = {
      S3_BUCKET               = aws_s3_bucket.telecom_data.id
      PHONE_HASH_TABLE        = aws_dynamodb_table.phone_hash.name
      PHONE_HASH_SALT         = var.phone_hash_salt
      INTERLOCK_CONTROL_TABLE = module.interlock.control_table_name
      CDR_DAILY_TARGET        = tostring(var.cdr_daily_target)
      SEQ_DAILY_TARGET        = tostring(var.seq_daily_target)
    }
  }
}

resource "aws_cloudwatch_log_group" "bronze_consumer" {
  name              = "/aws/lambda/${var.environment}-bronze-consumer"
  retention_in_days = var.log_retention_days
}

# IAM role
resource "aws_iam_role" "bronze_consumer" {
  name = "${var.environment}-bronze-consumer-role"

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

resource "aws_iam_role_policy" "bronze_consumer_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.bronze_consumer.id

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
          aws_cloudwatch_log_group.bronze_consumer.arn,
          "${aws_cloudwatch_log_group.bronze_consumer.arn}:*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "bronze_consumer_s3" {
  name = "s3-read-write"
  role = aws_iam_role.bronze_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "s3:GetObject"
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.telecom_data.arn}/cdr/*"
      },
      {
        Action   = "s3:GetObject"
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.telecom_data.arn}/seq/*"
      },
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = [
          "${aws_s3_bucket.telecom_data.arn}/bronze/*",
          aws_s3_bucket.telecom_data.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "bronze_consumer_kinesis" {
  name = "kinesis-read"
  role = aws_iam_role.bronze_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "kinesis:GetRecords",
          "kinesis:GetShardIterator",
          "kinesis:DescribeStream",
          "kinesis:DescribeStreamSummary",
          "kinesis:ListShards",
          "kinesis:ListStreams",
          "kinesis:SubscribeToShard"
        ]
        Effect   = "Allow"
        Resource = aws_kinesis_stream.raw_events.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "bronze_consumer_dynamodb" {
  name = "dynamodb-read-write"
  role = aws_iam_role.bronze_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem"
        ]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.phone_hash.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "bronze_consumer_sqs" {
  name = "sqs-dlq"
  role = aws_iam_role.bronze_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:SendMessage"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.bronze_dlq.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "bronze_consumer_interlock" {
  name = "interlock-control-table"
  role = aws_iam_role.bronze_consumer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:UpdateItem", "dynamodb:PutItem"]
      Effect   = "Allow"
      Resource = module.interlock.control_table_arn
    }]
  })
}

# Kinesis event source mapping
resource "aws_lambda_event_source_mapping" "bronze_kinesis" {
  event_source_arn  = aws_kinesis_stream.raw_events.arn
  function_name     = aws_lambda_function.bronze_consumer.arn
  starting_position = "LATEST"
  batch_size        = 5

  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 3

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.bronze_dlq.arn
    }
  }
}

# SQS dead-letter queue for failed Kinesis records
resource "aws_sqs_queue" "bronze_dlq" {
  name                      = "${var.environment}-bronze-consumer-dlq"
  message_retention_seconds = 1209600 # 14 days

  kms_master_key_id                 = local.kms_key_arn
  kms_data_key_reuse_period_seconds = var.enable_cmk_encryption ? 300 : null

  tags = {
    Component = "bronze-pipeline"
  }
}
