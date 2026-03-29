terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# --- Feature Generator Lambda ---

resource "aws_lambda_function" "ml_generator" {
  function_name    = "${var.environment}-ml-generator"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 256
  timeout          = 60
  filename         = "${path.module}/../../build/ml-generator.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/ml-generator.zip")
  role             = aws_iam_role.ml_generator.arn

  environment {
    variables = {
      S3_BUCKET   = var.s3_bucket_name
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "ml_generator" {
  name = "${var.environment}-ml-generator-role"
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

resource "aws_iam_role_policy" "ml_generator_s3" {
  name = "s3-write"
  role = aws_iam_role.ml_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "s3:PutObject"
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "ml_generator_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ml_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.ml_generator.arn,
        "${aws_cloudwatch_log_group.ml_generator.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "ml_generator" {
  name              = "/aws/lambda/${var.environment}-ml-generator"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# Generator schedule: hourly.
resource "aws_cloudwatch_event_rule" "ml_generator" {
  name                = "${var.environment}-ml-generator-schedule"
  schedule_expression = "rate(1 hour)"
  state               = var.enable_ml ? "ENABLED" : "DISABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "ml_generator" {
  rule = aws_cloudwatch_event_rule.ml_generator.name
  arn  = aws_lambda_function.ml_generator.arn
}

resource "aws_lambda_permission" "ml_generator_eventbridge" {
  statement_id  = "AllowEventBridgeMLGen"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ml_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ml_generator.arn
}

# --- Data Prep Lambda ---

resource "aws_lambda_function" "ml_data_prep" {
  function_name    = "${var.environment}-ml-data-prep"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 512
  timeout          = 120
  filename         = "${path.module}/../../build/ml-data-prep.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/ml-data-prep.zip")
  role             = aws_iam_role.ml_data_prep.arn

  environment {
    variables = {
      S3_BUCKET               = var.s3_bucket_name
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      PIPELINE_ID             = "ml-data-prep"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "ml_data_prep" {
  name = "${var.environment}-ml-data-prep-role"
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

resource "aws_iam_role_policy" "ml_data_prep_s3" {
  name = "s3-read-write"
  role = aws_iam_role.ml_data_prep.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy" "ml_data_prep_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.ml_data_prep.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "ml_data_prep_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ml_data_prep.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.ml_data_prep.arn,
        "${aws_cloudwatch_log_group.ml_data_prep.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "ml_data_prep" {
  name              = "/aws/lambda/${var.environment}-ml-data-prep"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# --- Training Lambda ---

resource "aws_lambda_function" "ml_training" {
  function_name    = "${var.environment}-ml-training"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 512
  timeout          = 300
  filename         = "${path.module}/../../build/ml-training.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/ml-training.zip")
  role             = aws_iam_role.ml_training.arn

  environment {
    variables = {
      S3_BUCKET               = var.s3_bucket_name
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      PIPELINE_ID             = "ml-training"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "ml_training" {
  name = "${var.environment}-ml-training-role"
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

resource "aws_iam_role_policy" "ml_training_s3" {
  name = "s3-read-write"
  role = aws_iam_role.ml_training.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject"]
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "ml_training_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.ml_training.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "ml_training_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ml_training.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.ml_training.arn,
        "${aws_cloudwatch_log_group.ml_training.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "ml_training" {
  name              = "/aws/lambda/${var.environment}-ml-training"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# --- Evaluation Lambda ---

resource "aws_lambda_function" "ml_evaluation" {
  function_name    = "${var.environment}-ml-evaluation"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 256
  timeout          = 120
  filename         = "${path.module}/../../build/ml-evaluation.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/ml-evaluation.zip")
  role             = aws_iam_role.ml_evaluation.arn

  environment {
    variables = {
      S3_BUCKET               = var.s3_bucket_name
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      PIPELINE_ID             = "ml-evaluation"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "ml_evaluation" {
  name = "${var.environment}-ml-evaluation-role"
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

resource "aws_iam_role_policy" "ml_evaluation_s3" {
  name = "s3-read"
  role = aws_iam_role.ml_evaluation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = "s3:GetObject"
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "ml_evaluation_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.ml_evaluation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "ml_evaluation_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ml_evaluation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.ml_evaluation.arn,
        "${aws_cloudwatch_log_group.ml_evaluation.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "ml_evaluation" {
  name              = "/aws/lambda/${var.environment}-ml-evaluation"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# --- Deployment Lambda ---

resource "aws_lambda_function" "ml_deployment" {
  function_name    = "${var.environment}-ml-deployment"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handler.lambda_handler"
  memory_size      = 256
  timeout          = 60
  filename         = "${path.module}/../../build/ml-deployment.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/ml-deployment.zip")
  role             = aws_iam_role.ml_deployment.arn

  environment {
    variables = {
      S3_BUCKET               = var.s3_bucket_name
      INTERLOCK_CONTROL_TABLE = var.interlock_control_table_name
      PIPELINE_ID             = "ml-deployment"
    }
  }

  tags = var.tags
}

resource "aws_iam_role" "ml_deployment" {
  name = "${var.environment}-ml-deployment-role"
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

resource "aws_iam_role_policy" "ml_deployment_s3" {
  name = "s3-read-write"
  role = aws_iam_role.ml_deployment.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject"]
      Effect   = "Allow"
      Resource = "${var.s3_bucket_arn}/*"
    }]
  })
}

resource "aws_iam_role_policy" "ml_deployment_dynamodb" {
  name = "dynamodb-write"
  role = aws_iam_role.ml_deployment.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
      Effect   = "Allow"
      Resource = var.interlock_control_table_arn
    }]
  })
}

resource "aws_iam_role_policy" "ml_deployment_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.ml_deployment.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.ml_deployment.arn,
        "${aws_cloudwatch_log_group.ml_deployment.arn}:*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "ml_deployment" {
  name              = "/aws/lambda/${var.environment}-ml-deployment"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
