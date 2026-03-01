# IAM role for EventBridge Scheduler to start Glue jobs
resource "aws_iam_role" "scheduler_glue" {
  name = "${var.environment}-scheduler-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_glue" {
  name = "glue-start-job"
  role = aws_iam_role.scheduler_glue.id

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

# Hourly schedules — run at :05 past the hour
resource "aws_scheduler_schedule" "cdr_agg_hour" {
  name       = "${var.environment}-cdr-agg-hour"
  group_name = "default"

  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.scheduler_glue.arn

    input = jsonencode({
      JobName   = aws_glue_job.cdr_agg_hour.name
      Arguments = {
        "--s3_bucket" = aws_s3_bucket.telecom_data.id
      }
    })
  }
}

resource "aws_scheduler_schedule" "seq_agg_hour" {
  name       = "${var.environment}-seq-agg-hour"
  group_name = "default"

  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.scheduler_glue.arn

    input = jsonencode({
      JobName   = aws_glue_job.seq_agg_hour.name
      Arguments = {
        "--s3_bucket" = aws_s3_bucket.telecom_data.id
      }
    })
  }
}

# Daily schedules — run at 1:05 AM UTC
resource "aws_scheduler_schedule" "cdr_agg_day" {
  name       = "${var.environment}-cdr-agg-day"
  group_name = "default"

  schedule_expression          = "cron(5 1 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.scheduler_glue.arn

    input = jsonencode({
      JobName   = aws_glue_job.cdr_agg_day.name
      Arguments = {
        "--s3_bucket" = aws_s3_bucket.telecom_data.id
      }
    })
  }
}

resource "aws_scheduler_schedule" "seq_agg_day" {
  name       = "${var.environment}-seq-agg-day"
  group_name = "default"

  schedule_expression          = "cron(5 1 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = aws_iam_role.scheduler_glue.arn

    input = jsonencode({
      JobName   = aws_glue_job.seq_agg_day.name
      Arguments = {
        "--s3_bucket" = aws_s3_bucket.telecom_data.id
      }
    })
  }
}
