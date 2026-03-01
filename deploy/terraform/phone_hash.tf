# DynamoDB table for phone number → SHA-256 hash mapping
resource "aws_dynamodb_table" "phone_hash" {
  name         = "${var.environment}-phone-hash"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "phone"

  attribute {
    name = "phone"
    type = "S"
  }

  tags = {
    Component = "bronze-pipeline"
  }
}
