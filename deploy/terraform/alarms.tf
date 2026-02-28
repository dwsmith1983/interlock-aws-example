# =============================================================================
# CloudWatch Alarms — Lambda errors + DLQ depth + Glue failure detection
# =============================================================================

locals {
  # Critical Lambda functions to alarm on errors.
  # stream-router and watchdog are defined outside the core set.
  alarm_lambda_functions = {
    "orchestrator"  = aws_lambda_function.go["orchestrator"].function_name
    "evaluator"     = aws_lambda_function.go["evaluator"].function_name
    "trigger"       = aws_lambda_function.go["trigger"].function_name
    "run-checker"   = aws_lambda_function.go["run-checker"].function_name
    "stream-router" = aws_lambda_function.stream_router.function_name
    "watchdog"      = aws_lambda_function.watchdog.function_name
  }

  alarm_dlq_queues = {
    "stream-router-dlq"    = aws_sqs_queue.stream_router_dlq.name
    "pipeline-monitor-dlq" = aws_sqs_queue.pipeline_monitor_dlq.name
  }

  # Glue job names to monitor for failures.
  alarm_glue_jobs = [for name, _ in local.glue_jobs : name]
}

# --- Lambda error alarms ---
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.alarm_lambda_functions

  alarm_name          = "${var.table_name}-${each.key}-errors"
  alarm_description   = "Errors detected in ${each.key} Lambda"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# --- DLQ depth alarms ---
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = local.alarm_dlq_queues

  alarm_name          = "${var.table_name}-${each.key}-depth"
  alarm_description   = "Messages visible in ${each.key}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# =============================================================================
# Glue Job Failure Detection — EventBridge rule for Glue state changes
# =============================================================================

resource "aws_cloudwatch_event_rule" "glue_failure" {
  name        = "${var.table_name}-glue-failure"
  description = "Detect Glue job failures for monitored ETL jobs"

  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      jobName = local.alarm_glue_jobs
      state   = ["FAILED"]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_failure_sns" {
  rule      = aws_cloudwatch_event_rule.glue_failure.name
  target_id = "glue-failure-to-sns"
  arn       = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      jobName = "$.detail.jobName"
      state   = "$.detail.state"
      message = "$.detail.message"
    }
    input_template = "\"Glue job <jobName> entered state <state>: <message>\""
  }
}

resource "aws_sns_topic_policy" "alerts_eventbridge" {
  arn = aws_sns_topic.alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowEventBridgePublish"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
      },
      {
        Sid       = "AllowCloudWatchAlarmsPublish"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
      },
    ]
  })
}
