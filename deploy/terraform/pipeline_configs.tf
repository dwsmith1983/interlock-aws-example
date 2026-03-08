# Templated pipeline config loader — resolves ${environment}, ${s3_bucket}
# placeholders before writing to Interlock control table.
# This replaces the module's built-in config_loader.tf (disabled via pipelines_path = "").

locals {
  pipeline_files = fileset("${path.module}/../../pipelines", "*.yaml")
  pipeline_template_vars = {
    environment = var.environment
    s3_bucket   = aws_s3_bucket.telecom_data.id
  }
}

resource "aws_dynamodb_table_item" "pipeline_config" {
  for_each   = local.pipeline_files
  table_name = module.interlock.control_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK     = { S = "PIPELINE#${trimsuffix(each.value, ".yaml")}" }
    SK     = { S = "CONFIG" }
    config = { S = jsonencode(yamldecode(templatefile("${path.module}/../../pipelines/${each.value}", local.pipeline_template_vars))) }
  })
}
