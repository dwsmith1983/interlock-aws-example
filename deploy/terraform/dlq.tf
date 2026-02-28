# =============================================================================
# Dead Letter Queues — capture failed DynamoDB Stream processing records
# =============================================================================

# --- Stream-router DLQ ---
resource "aws_sqs_queue" "stream_router_dlq" {
  name                      = "${var.table_name}-stream-router-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_iam_role_policy" "stream_router_dlq" {
  name = "stream-router-dlq"
  role = aws_iam_role.stream_router.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SQSSendMessage"
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = [aws_sqs_queue.stream_router_dlq.arn]
    }]
  })
}

# --- Pipeline-monitor DLQ ---
resource "aws_sqs_queue" "pipeline_monitor_dlq" {
  name                      = "${var.table_name}-pipeline-monitor-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_iam_role_policy" "pipeline_monitor_dlq" {
  name = "pipeline-monitor-dlq"
  role = aws_iam_role.pipeline_monitor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SQSSendMessage"
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = [aws_sqs_queue.pipeline_monitor_dlq.arn]
    }]
  })
}
