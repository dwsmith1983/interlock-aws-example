# ---------- Dry Run Demo: EventBridge -> Lambda ----------
# Simulates weather station data arriving every 10 minutes.
# Updates interlock sensors for dry run observation (never triggers SFN).
#
# Gated by var.deploy_pipelines containing "dryrun".

locals {
  deploy_dryrun = contains(var.deploy_pipelines, "dryrun")
}

# ---- S3 bucket ----

resource "aws_s3_bucket" "dryrun_data" {
  count  = local.deploy_dryrun ? 1 : 0
  bucket = "${var.environment}-dryrun-data-${random_id.suffix.hex}"

  tags = var.tags
}

resource "aws_s3_bucket_lifecycle_configuration" "dryrun_data" {
  count  = local.deploy_dryrun ? 1 : 0
  bucket = aws_s3_bucket.dryrun_data[0].id

  rule {
    id     = "expire-old-data"
    status = "Enabled"

    filter {}

    expiration {
      days = var.data_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "dryrun_data" {
  count  = local.deploy_dryrun ? 1 : 0
  bucket = aws_s3_bucket.dryrun_data[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---- Lambda function ----

resource "aws_lambda_function" "dryrun_demo" {
  count            = local.deploy_dryrun ? 1 : 0
  function_name    = "${var.environment}-dryrun-demo"
  role             = aws_iam_role.dryrun_demo[0].arn
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
      S3_BUCKET               = aws_s3_bucket.dryrun_data[0].id
    }
  }

  tags = var.tags
}

# ---- EventBridge rule: every 10 minutes ----
# Runs on the default event bus (schedule-based), not the interlock custom bus.

resource "aws_cloudwatch_event_rule" "dryrun_demo" {
  count               = local.deploy_dryrun ? 1 : 0
  name                = "${var.environment}-dryrun-demo-schedule"
  schedule_expression = "rate(10 minutes)"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "dryrun_demo" {
  count = local.deploy_dryrun ? 1 : 0
  rule  = aws_cloudwatch_event_rule.dryrun_demo[0].name
  arn   = aws_lambda_function.dryrun_demo[0].arn
}

resource "aws_lambda_permission" "dryrun_demo_eventbridge" {
  count         = local.deploy_dryrun ? 1 : 0
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dryrun_demo[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dryrun_demo[0].arn
}

# ---- IAM role ----

resource "aws_iam_role" "dryrun_demo" {
  count = local.deploy_dryrun ? 1 : 0
  name  = "${var.environment}-interlock-dryrun-demo"

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
  count      = local.deploy_dryrun ? 1 : 0
  role       = aws_iam_role.dryrun_demo[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dryrun_demo_dynamodb" {
  count = local.deploy_dryrun ? 1 : 0
  name  = "control-table-readwrite"
  role  = aws_iam_role.dryrun_demo[0].id

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

resource "aws_iam_role_policy" "dryrun_demo_s3" {
  count = local.deploy_dryrun ? 1 : 0
  name  = "s3-write"
  role  = aws_iam_role.dryrun_demo[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${aws_s3_bucket.dryrun_data[0].arn}/*"
    }]
  })
}

# ---- CloudWatch log group ----

resource "aws_cloudwatch_log_group" "dryrun_demo" {
  count             = local.deploy_dryrun ? 1 : 0
  name              = "/aws/lambda/${var.environment}-dryrun-demo"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
