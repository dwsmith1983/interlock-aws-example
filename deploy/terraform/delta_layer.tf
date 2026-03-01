# Lambda layer for pyarrow + deltalake (arm64)
resource "aws_lambda_layer_version" "delta_lake" {
  layer_name          = "${var.environment}-delta-lake"
  filename            = "${path.module}/../../build/delta-lake-layer.zip"
  source_code_hash    = filebase64sha256("${path.module}/../../build/delta-lake-layer.zip")
  compatible_runtimes = ["python3.12"]
  compatible_architectures = ["arm64"]
  description         = "pyarrow + deltalake for Delta Lake writes"
}
