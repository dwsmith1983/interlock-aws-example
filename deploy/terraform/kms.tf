# Customer-managed KMS key for encrypting all stack resources.
# Only created when var.enable_cmk_encryption is true.

resource "aws_kms_key" "main" {
  count = var.enable_cmk_encryption ? 1 : 0

  description             = "${var.environment}-interlock encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RootAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${data.aws_region.current.name}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:*"
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_kms_alias" "main" {
  count = var.enable_cmk_encryption ? 1 : 0

  name          = "alias/${var.environment}-interlock"
  target_key_id = aws_kms_key.main[0].key_id
}

# Data sources for account ID and region (used in KMS policy).
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Convenience local for use in other .tf files.
locals {
  kms_key_arn = var.enable_cmk_encryption ? aws_kms_key.main[0].arn : null
}
