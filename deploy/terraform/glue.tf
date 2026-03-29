# IAM role for Glue jobs
resource "aws_iam_role" "glue" {
  name = "${var.environment}-telecom-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3" {
  name = "s3-read-write"
  role = aws_iam_role.glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.telecom_data.arn,
          "${aws_s3_bucket.telecom_data.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "glue_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:/aws-glue/*"
      }
    ]
  })
}

# Upload Glue scripts to S3
# Entry point scripts (referenced by script_location)
resource "aws_s3_object" "glue_cdr_agg_hour" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/cdr_agg_hour.py"
  source = "${path.module}/../../glue_jobs/cdr_agg_hour.py"
  etag   = filemd5("${path.module}/../../glue_jobs/cdr_agg_hour.py")
}

resource "aws_s3_object" "glue_cdr_agg_day" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/cdr_agg_day.py"
  source = "${path.module}/../../glue_jobs/cdr_agg_day.py"
  etag   = filemd5("${path.module}/../../glue_jobs/cdr_agg_day.py")
}

resource "aws_s3_object" "glue_seq_agg_hour" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/seq_agg_hour.py"
  source = "${path.module}/../../glue_jobs/seq_agg_hour.py"
  etag   = filemd5("${path.module}/../../glue_jobs/seq_agg_hour.py")
}

resource "aws_s3_object" "glue_seq_agg_day" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/seq_agg_day.py"
  source = "${path.module}/../../glue_jobs/seq_agg_day.py"
  etag   = filemd5("${path.module}/../../glue_jobs/seq_agg_day.py")
}

# glue_jobs package zip (components + args as --extra-py-files)
resource "aws_s3_object" "glue_jobs_zip" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/glue_jobs.zip"
  source = "${path.module}/../../build/glue_jobs.zip"
  etag   = filemd5("${path.module}/../../build/glue_jobs.zip")
}

# Upload pyspark-pipeline-framework wheel
resource "aws_s3_object" "ppf_wheel" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/ppf.whl"
  source = "${path.module}/../../build/ppf.whl"
  etag   = filemd5("${path.module}/../../build/ppf.whl")
}

# Glue jobs
resource "aws_glue_job" "cdr_agg_hour" {
  name     = "${var.environment}-cdr-agg-hour"
  role_arn = aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_hourly_workers

  execution_property {
    max_concurrent_runs = 24
  }

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/cdr_agg_hour.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs.zip"
    "--additional-python-modules"     = "dataconf>=3.4,structlog>=23.0"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                   = "python"
  }

  tags = {
    Component = "silver-pipeline"
  }
}

resource "aws_glue_job" "cdr_agg_day" {
  name     = "${var.environment}-cdr-agg-day"
  role_arn = aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = var.glue_daily_worker_type
  number_of_workers = var.glue_daily_workers

  execution_property {
    max_concurrent_runs = 24
  }

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/cdr_agg_day.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs.zip"
    "--additional-python-modules"     = "dataconf>=3.4,structlog>=23.0"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                   = "python"
  }

  tags = {
    Component = "silver-pipeline"
  }
}

resource "aws_glue_job" "seq_agg_hour" {
  name     = "${var.environment}-seq-agg-hour"
  role_arn = aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_hourly_workers

  execution_property {
    max_concurrent_runs = 24
  }

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/seq_agg_hour.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs.zip"
    "--additional-python-modules"     = "dataconf>=3.4,structlog>=23.0"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                   = "python"
  }

  tags = {
    Component = "silver-pipeline"
  }
}

resource "aws_glue_job" "seq_agg_day" {
  name     = "${var.environment}-seq-agg-day"
  role_arn = aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = var.glue_daily_worker_type
  number_of_workers = var.glue_daily_workers

  execution_property {
    max_concurrent_runs = 24
  }

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/seq_agg_day.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs.zip"
    "--additional-python-modules"     = "dataconf>=3.4,structlog>=23.0"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                   = "python"
  }

  tags = {
    Component = "silver-pipeline"
  }
}

resource "aws_iam_role_policy" "glue_kms" {
  count = var.enable_cmk_encryption ? 1 : 0
  name  = "kms-access"
  role  = aws_iam_role.glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Effect   = "Allow"
        Resource = [local.kms_key_arn]
      }
    ]
  })
}
