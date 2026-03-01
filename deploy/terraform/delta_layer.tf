# Upload layer zip to S3 (exceeds 70MB direct upload limit)
resource "aws_s3_object" "delta_lake_layer" {
  bucket = aws_s3_bucket.telecom_data.id
  key    = "layers/delta-lake-layer.zip"
  source = "${path.module}/../../build/delta-lake-layer.zip"
  etag   = filemd5("${path.module}/../../build/delta-lake-layer.zip")
}

# Lambda layer for pyarrow + deltalake (arm64)
resource "aws_lambda_layer_version" "delta_lake" {
  layer_name               = "${var.environment}-delta-lake"
  s3_bucket                = aws_s3_object.delta_lake_layer.bucket
  s3_key                   = aws_s3_object.delta_lake_layer.key
  s3_object_version        = aws_s3_object.delta_lake_layer.version_id
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["arm64"]
  description              = "pyarrow + deltalake for Delta Lake writes"

  depends_on = [aws_s3_object.delta_lake_layer]
}
