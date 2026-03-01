# IAM role for EventBridge to start Glue jobs
resource "aws_iam_role" "eventbridge_glue" {
  name = "${var.environment}-eventbridge-glue-role"

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

resource "aws_iam_role_policy" "eventbridge_glue" {
  name = "glue-start-job"
  role = aws_iam_role.eventbridge_glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "glue:StartJobRun"
        Effect   = "Allow"
        Resource = [
          aws_glue_job.cdr_agg_hour.arn,
          aws_glue_job.cdr_agg_day.arn,
          aws_glue_job.seq_agg_hour.arn,
          aws_glue_job.seq_agg_day.arn,
        ]
      }
    ]
  })
}

# Hourly schedules — run at :05 past the hour to allow bronze writes to settle
resource "aws_cloudwatch_event_rule" "cdr_agg_hour" {
  name                = "${var.environment}-cdr-agg-hour"
  schedule_expression = "cron(5 * * * ? *)"
  description         = "Trigger CDR hourly aggregation"
}

resource "aws_cloudwatch_event_rule" "seq_agg_hour" {
  name                = "${var.environment}-seq-agg-hour"
  schedule_expression = "cron(5 * * * ? *)"
  description         = "Trigger SEQ hourly aggregation"
}

# Daily schedules — run at 1:05 AM UTC
resource "aws_cloudwatch_event_rule" "cdr_agg_day" {
  name                = "${var.environment}-cdr-agg-day"
  schedule_expression = "cron(5 1 * * ? *)"
  description         = "Trigger CDR daily aggregation"
}

resource "aws_cloudwatch_event_rule" "seq_agg_day" {
  name                = "${var.environment}-seq-agg-day"
  schedule_expression = "cron(5 1 * * ? *)"
  description         = "Trigger SEQ daily aggregation"
}

# Targets — EventBridge → Glue StartJobRun
# Glue jobs compute par_day/par_hour from current time when not provided
resource "aws_cloudwatch_event_target" "cdr_agg_hour" {
  rule     = aws_cloudwatch_event_rule.cdr_agg_hour.name
  arn      = aws_glue_job.cdr_agg_hour.arn
  role_arn = aws_iam_role.eventbridge_glue.arn

  input = jsonencode({
    "--s3_bucket" = aws_s3_bucket.telecom_data.id
  })
}

resource "aws_cloudwatch_event_target" "seq_agg_hour" {
  rule     = aws_cloudwatch_event_rule.seq_agg_hour.name
  arn      = aws_glue_job.seq_agg_hour.arn
  role_arn = aws_iam_role.eventbridge_glue.arn

  input = jsonencode({
    "--s3_bucket" = aws_s3_bucket.telecom_data.id
  })
}

resource "aws_cloudwatch_event_target" "cdr_agg_day" {
  rule     = aws_cloudwatch_event_rule.cdr_agg_day.name
  arn      = aws_glue_job.cdr_agg_day.arn
  role_arn = aws_iam_role.eventbridge_glue.arn

  input = jsonencode({
    "--s3_bucket" = aws_s3_bucket.telecom_data.id
  })
}

resource "aws_cloudwatch_event_target" "seq_agg_day" {
  rule     = aws_cloudwatch_event_rule.seq_agg_day.name
  arn      = aws_glue_job.seq_agg_day.arn
  role_arn = aws_iam_role.eventbridge_glue.arn

  input = jsonencode({
    "--s3_bucket" = aws_s3_bucket.telecom_data.id
  })
}
