resource "aws_s3_bucket" "data" {
  bucket        = local.bucket_name
  force_destroy = var.destroy_on_delete
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-bronze"
    status = "Enabled"

    filter {
      prefix = "bronze/"
    }

    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Upload Glue PySpark scripts
resource "aws_s3_object" "glue_script" {
  for_each = local.glue_jobs

  bucket = aws_s3_bucket.data.id
  key    = "glue-scripts/${each.value}"
  source = "${path.module}/${var.glue_scripts_dir}/${each.value}"
  etag   = filemd5("${path.module}/${var.glue_scripts_dir}/${each.value}")
}
