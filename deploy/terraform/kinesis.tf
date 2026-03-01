# Kinesis Data Stream — ordered queue for raw S3 file events
resource "aws_kinesis_stream" "raw_events" {
  name = "${var.environment}-telecom-raw-events"

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }

  retention_period = 24

  tags = {
    Component = "bronze-pipeline"
  }
}

# EventBridge rule — capture S3 PutObject events for cdr/ and seq/ prefixes
resource "aws_cloudwatch_event_rule" "raw_s3_put" {
  name        = "${var.environment}-telecom-raw-s3-put"
  description = "Capture S3 PutObject events for raw CDR and SEQ data"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.telecom_data.id]
      }
      object = {
        key = [
          { prefix = "cdr/" },
          { prefix = "seq/" }
        ]
      }
    }
  })
}

# EventBridge target — route matching events to Kinesis
resource "aws_cloudwatch_event_target" "raw_s3_to_kinesis" {
  rule = aws_cloudwatch_event_rule.raw_s3_put.name
  arn  = aws_kinesis_stream.raw_events.arn

  kinesis_target {
    partition_key_path = "$.detail.object.key"
  }

  role_arn = aws_iam_role.eventbridge_kinesis.arn
}

# IAM role for EventBridge to put records into Kinesis
resource "aws_iam_role" "eventbridge_kinesis" {
  name = "${var.environment}-eventbridge-kinesis-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_kinesis" {
  name = "kinesis-put"
  role = aws_iam_role.eventbridge_kinesis.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "kinesis:PutRecord",
          "kinesis:PutRecords"
        ]
        Effect   = "Allow"
        Resource = aws_kinesis_stream.raw_events.arn
      }
    ]
  })
}
