# Bronze audit Lambda — reconciles Delta table records against sensor counts
resource "aws_lambda_function" "bronze_audit" {
  function_name    = "${var.environment}-bronze-audit"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "audit.handler.lambda_handler"
  memory_size      = 2048
  timeout          = 120
  filename         = "${path.module}/../../build/bronze-audit.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/bronze-audit.zip")
  role             = aws_iam_role.bronze_audit.arn

  layers = [aws_lambda_layer_version.delta_lake.arn]

  environment {
    variables = {
      INTERLOCK_CONTROL_TABLE = module.interlock.control_table_name
      S3_BUCKET               = aws_s3_bucket.telecom_data.id
    }
  }
}

resource "aws_cloudwatch_log_group" "bronze_audit" {
  name              = "/aws/lambda/${var.environment}-bronze-audit"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function_url" "bronze_audit" {
  function_name      = aws_lambda_function.bronze_audit.function_name
  authorization_type = "AWS_IAM"
}

# IAM role for audit Lambda
resource "aws_iam_role" "bronze_audit" {
  name = "${var.environment}-bronze-audit-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "bronze_audit_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.bronze_audit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Effect   = "Allow"
      Resource = [
        aws_cloudwatch_log_group.bronze_audit.arn,
        "${aws_cloudwatch_log_group.bronze_audit.arn}:*"
      ]
    }]
  })
}

resource "aws_iam_role_policy" "bronze_audit_s3" {
  name = "s3-read"
  role = aws_iam_role.bronze_audit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [aws_s3_bucket.telecom_data.arn, "${aws_s3_bucket.telecom_data.arn}/bronze/*"]
    }]
  })
}

resource "aws_iam_role_policy" "bronze_audit_dynamodb" {
  name = "dynamodb-rw"
  role = aws_iam_role.bronze_audit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
      Effect   = "Allow"
      Resource = module.interlock.control_table_arn
    }]
  })
}
