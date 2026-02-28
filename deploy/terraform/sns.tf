resource "aws_sns_topic" "alerts" {
  name = "${var.table_name}-alerts"
}

resource "aws_sns_topic" "lifecycle" {
  name = "${var.table_name}-lifecycle"
}

resource "aws_sns_topic" "observability" {
  name = "${var.table_name}-observability"
}

# =============================================================================
# Lifecycle topic — pipeline-monitor subscribes for active chaos recovery
# =============================================================================

resource "aws_sns_topic_subscription" "pipeline_monitor_lifecycle" {
  topic_arn = aws_sns_topic.lifecycle.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.python["pipeline-monitor"].arn
}

resource "aws_lambda_permission" "sns_lifecycle_monitor" {
  statement_id  = "AllowLifecycleSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.python["pipeline-monitor"].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.lifecycle.arn
}

# =============================================================================
# Alert logger — SNS subscriber that logs + persists alerts to DynamoDB
# =============================================================================

data "archive_file" "alert_logger" {
  type        = "zip"
  source_dir  = "${path.module}/${var.python_lambdas_dir}/alert_logger"
  output_path = "${path.module}/.build/py-alert-logger.zip"
}

resource "aws_cloudwatch_log_group" "alert_logger" {
  name              = "/aws/lambda/${var.table_name}-alert-logger"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "alert_logger" {
  function_name = "${var.table_name}-alert-logger"
  role          = aws_iam_role.alert_logger.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 30

  filename         = data.archive_file.alert_logger.output_path
  source_code_hash = data.archive_file.alert_logger.output_base64sha256

  environment {
    variables = {
      TABLE_NAME        = aws_dynamodb_table.main.name
      SLACK_WEBHOOK_URL = var.slack_webhook_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.alert_logger]
}

resource "aws_sns_topic_subscription" "alert_logger" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.alert_logger.arn
}

resource "aws_lambda_permission" "sns_alert_logger" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alert_logger.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alerts.arn
}

# =============================================================================
# Event exporter — SNS subscriber that writes observability events to S3
# =============================================================================

data "archive_file" "event_exporter" {
  type        = "zip"
  source_dir  = "${path.module}/${var.python_lambdas_dir}/event_exporter"
  output_path = "${path.module}/.build/py-event-exporter.zip"
}

resource "aws_cloudwatch_log_group" "event_exporter" {
  name              = "/aws/lambda/${var.table_name}-event-exporter"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "event_exporter" {
  function_name = "${var.table_name}-event-exporter"
  role          = aws_iam_role.event_exporter.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 30

  filename         = data.archive_file.event_exporter.output_path
  source_code_hash = data.archive_file.event_exporter.output_base64sha256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.data.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.event_exporter]
}

resource "aws_sns_topic_subscription" "event_exporter" {
  topic_arn = aws_sns_topic.observability.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.event_exporter.arn
}

resource "aws_lambda_permission" "sns_event_exporter" {
  statement_id  = "AllowObservabilitySNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_exporter.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.observability.arn
}
