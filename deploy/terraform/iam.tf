# =============================================================================
# Trust policies
# =============================================================================

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# =============================================================================
# Go Lambda roles
# =============================================================================

# --- orchestrator: DynamoDB RW + SNS Publish ---
resource "aws_iam_role" "orchestrator" {
  name               = "${var.table_name}-orchestrator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "orchestrator_basic" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "orchestrator" {
  name = "orchestrator-policy"
  role = aws_iam_role.orchestrator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
      {
        Sid      = "SNSPublish"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      },
    ]
  })
}

# --- evaluator: DynamoDB RW ---
resource "aws_iam_role" "evaluator_role" {
  name               = "${var.table_name}-evaluator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "evaluator_basic" {
  role       = aws_iam_role.evaluator_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "evaluator" {
  name = "evaluator-policy"
  role = aws_iam_role.evaluator_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
    ]
  })
}

# --- trigger: DynamoDB RW + SNS Publish + Glue (conditional) ---
resource "aws_iam_role" "trigger" {
  name               = "${var.table_name}-trigger"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "trigger_basic" {
  role       = aws_iam_role.trigger.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "trigger" {
  name = "trigger-policy"
  role = aws_iam_role.trigger.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
      {
        Sid      = "SNSPublish"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      },
    ]
  })
}

resource "aws_iam_role_policy" "trigger_glue" {
  count = var.enable_glue_trigger ? 1 : 0

  name = "trigger-glue"
  role = aws_iam_role.trigger.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "GlueAccess"
      Effect   = "Allow"
      Action   = ["glue:StartJobRun", "glue:GetJobRun"]
      Resource = ["*"]
    }]
  })
}

# --- run-checker: DynamoDB Read + Glue Get (conditional) ---
resource "aws_iam_role" "run_checker" {
  name               = "${var.table_name}-run-checker"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "run_checker_basic" {
  role       = aws_iam_role.run_checker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "run_checker" {
  name = "run-checker-policy"
  role = aws_iam_role.run_checker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DynamoDBRead"
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan",
        "dynamodb:BatchGetItem", "dynamodb:ConditionCheckItem",
        "dynamodb:DescribeTable",
      ]
      Resource = [
        aws_dynamodb_table.main.arn,
        "${aws_dynamodb_table.main.arn}/index/*",
      ]
    }]
  })
}

resource "aws_iam_role_policy" "run_checker_glue" {
  count = var.enable_glue_trigger ? 1 : 0

  name = "run-checker-glue"
  role = aws_iam_role.run_checker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "GlueGet"
      Effect   = "Allow"
      Action   = ["glue:GetJobRun"]
      Resource = ["*"]
    }]
  })
}

# --- stream-router: DynamoDB Stream + SFN Start ---
resource "aws_iam_role" "stream_router" {
  name               = "${var.table_name}-stream-router"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "stream_router_basic" {
  role       = aws_iam_role.stream_router.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "stream_router" {
  name = "stream-router-policy"
  role = aws_iam_role.stream_router.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBStream"
        Effect = "Allow"
        Action = [
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:DescribeStream",
          "dynamodb:ListStreams",
        ]
        Resource = ["${aws_dynamodb_table.main.arn}/stream/*"]
      },
      {
        Sid      = "SFNStart"
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [aws_sfn_state_machine.pipeline.arn]
      },
      {
        Sid      = "SNSPublishLifecycle"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.lifecycle.arn]
      },
    ]
  })
}

# =============================================================================
# Alert logger role: DynamoDB Write (ALERT# records)
# =============================================================================

resource "aws_iam_role" "alert_logger" {
  name               = "${var.table_name}-alert-logger"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "alert_logger_basic" {
  role       = aws_iam_role.alert_logger.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "alert_logger" {
  name = "alert-logger-policy"
  role = aws_iam_role.alert_logger.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DynamoDBWrite"
      Effect = "Allow"
      Action = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
      Resource = [
        aws_dynamodb_table.main.arn,
        "${aws_dynamodb_table.main.arn}/index/*",
      ]
    }]
  })
}

# =============================================================================
# Python Lambda roles
# =============================================================================

# --- custom-evaluator: DynamoDB RW + S3 Read ---
resource "aws_iam_role" "custom_evaluator" {
  name               = "${var.table_name}-custom-evaluator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "custom_evaluator_basic" {
  role       = aws_iam_role.custom_evaluator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "custom_evaluator" {
  name = "custom-evaluator-policy"
  role = aws_iam_role.custom_evaluator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
      {
        Sid    = "S3Read"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetBucketLocation",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*",
        ]
      },
    ]
  })
}

# --- ingest-* (x3): DynamoDB RW + S3 RW ---
resource "aws_iam_role" "ingest" {
  for_each = local.ingest_lambda_names

  name               = "${var.table_name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "ingest_basic" {
  for_each = local.ingest_lambda_names

  role       = aws_iam_role.ingest[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ingest" {
  for_each = local.ingest_lambda_names

  name = "${each.key}-policy"
  role = aws_iam_role.ingest[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem",
          "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable",
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
          "s3:GetBucketLocation", "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*",
        ]
      },
    ]
  })
}

# =============================================================================
# Step Function role
# =============================================================================

resource "aws_iam_role" "sfn" {
  name               = "${var.table_name}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  name = "invoke-lambdas"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.go["orchestrator"].arn,
          aws_lambda_function.go["evaluator"].arn,
          aws_lambda_function.go["trigger"].arn,
          aws_lambda_function.go["run-checker"].arn,
        ]
      },
      {
        Sid      = "SNSPublishAlerts"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = [aws_sns_topic.alerts.arn]
      },
    ]
  })
}

# =============================================================================
# Glue role
# =============================================================================

resource "aws_iam_role" "glue" {
  name               = "${var.table_name}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue" {
  name = "glue-data-access"
  role = aws_iam_role.glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
          "s3:GetBucketLocation", "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*",
        ]
      },
      {
        Sid      = "DynamoDBPutItem"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = [aws_dynamodb_table.main.arn]
      },
    ]
  })
}

# --- pipeline-monitor: DynamoDB Stream Read + DynamoDB Write (CONTROL#/JOBLOG#) ---
resource "aws_iam_role" "pipeline_monitor" {
  name               = "${var.table_name}-pipeline-monitor"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "pipeline_monitor_basic" {
  role       = aws_iam_role.pipeline_monitor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "pipeline_monitor" {
  name = "pipeline-monitor-policy"
  role = aws_iam_role.pipeline_monitor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBStream"
        Effect = "Allow"
        Action = [
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:DescribeStream",
          "dynamodb:ListStreams",
        ]
        Resource = ["${aws_dynamodb_table.main.arn}/stream/*"]
      },
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
        ]
      },
    ]
  })
}

# --- dashboard-api: DynamoDB Read-Only ---
resource "aws_iam_role" "dashboard_api" {
  name               = "${var.table_name}-dashboard-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "dashboard_api_basic" {
  role       = aws_iam_role.dashboard_api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dashboard_api" {
  name = "dashboard-api-policy"
  role = aws_iam_role.dashboard_api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "DynamoDBReadOnly"
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan",
        "dynamodb:BatchGetItem", "dynamodb:ConditionCheckItem",
        "dynamodb:DescribeTable",
      ]
      Resource = [
        aws_dynamodb_table.main.arn,
        "${aws_dynamodb_table.main.arn}/index/*",
      ]
    }]
  })
}

# =============================================================================
# Role ARN maps (referenced by lambda_go.tf and lambda_python.tf)
# =============================================================================

locals {
  go_lambda_roles = {
    "orchestrator" = aws_iam_role.orchestrator.arn
    "evaluator"    = aws_iam_role.evaluator_role.arn
    "trigger"      = aws_iam_role.trigger.arn
    "run-checker"  = aws_iam_role.run_checker.arn
  }

  python_lambda_roles = {
    "custom-evaluator"  = aws_iam_role.custom_evaluator.arn
    "ingest-earthquake" = aws_iam_role.ingest["ingest-earthquake"].arn
    "ingest-crypto"     = aws_iam_role.ingest["ingest-crypto"].arn
    "pipeline-monitor"  = aws_iam_role.pipeline_monitor.arn
    "dashboard-api"     = aws_iam_role.dashboard_api.arn
  }
}
