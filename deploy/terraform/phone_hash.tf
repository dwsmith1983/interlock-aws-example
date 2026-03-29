# DynamoDB table for phone number → SHA-256 hash mapping
resource "aws_dynamodb_table" "phone_hash" {
  name         = "${var.environment}-phone-hash"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "phone"

  attribute {
    name = "phone"
    type = "S"
  }

  dynamic "server_side_encryption" {
    for_each = var.enable_cmk_encryption ? [1] : []
    content {
      enabled     = true
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = {
    Component = "bronze-pipeline"
  }
}
