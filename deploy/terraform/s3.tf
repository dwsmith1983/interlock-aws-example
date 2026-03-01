resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "telecom_data" {
  bucket = "${var.environment}-telecom-data-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_lifecycle_configuration" "telecom_data" {
  bucket = aws_s3_bucket.telecom_data.id

  rule {
    id     = "expire-old-data"
    status = "Enabled"

    filter {}

    expiration {
      days = var.data_retention_days
    }
  }
}

resource "aws_s3_bucket_public_access_block" "telecom_data" {
  bucket = aws_s3_bucket.telecom_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
