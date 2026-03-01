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
resource "aws_s3_object" "glue_components" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "glue_scripts/glue_jobs/components.py"
  source = "${path.module}/../../glue_jobs/components.py"
  etag   = filemd5("${path.module}/../../glue_jobs/components.py")
}

resource "aws_s3_object" "glue_init" {
  bucket  = aws_s3_bucket.telecom_data.id
  key     = "glue_scripts/glue_jobs/__init__.py"
  content = ""
  etag    = md5("")
}

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

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/cdr_agg_hour.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs/components.py"
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
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_daily_workers

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/cdr_agg_day.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs/components.py"
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

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/seq_agg_hour.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs/components.py"
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
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_daily_workers

  command {
    script_location = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/seq_agg_day.py"
    python_version  = "3"
  }

  default_arguments = {
    "--datalake-formats"              = "delta"
    "--extra-py-files"                = "s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/ppf.whl,s3://${aws_s3_bucket.telecom_data.id}/glue_scripts/glue_jobs/components.py"
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                   = "python"
  }

  tags = {
    Component = "silver-pipeline"
  }
}
