# Templated pipeline config loader — resolves ${environment}, ${s3_bucket}
# placeholders before writing to Interlock control table.
# This replaces the module's built-in config_loader.tf (disabled via pipelines_path = "").
#
# Filtered by var.deploy_pipelines: "dryrun", "cdr", "seq".

locals {
  all_pipeline_files = fileset("${path.module}/../../pipelines", "*.yaml")

  # Derive group from filename: dryrun-* → "dryrun", *cdr* → "cdr", *seq* → "seq"
  active_pipeline_files = toset([
    for f in local.all_pipeline_files : f
    if (
      (startswith(f, "dryrun-") && contains(var.deploy_pipelines, "dryrun")) ||
      (!startswith(f, "dryrun-") && length(regexall("cdr", f)) > 0 && contains(var.deploy_pipelines, "cdr")) ||
      (!startswith(f, "dryrun-") && length(regexall("seq", f)) > 0 && contains(var.deploy_pipelines, "seq"))
    )
  ])

  pipeline_template_vars = {
    environment = var.environment
    s3_bucket   = aws_s3_bucket.telecom_data.id
  }
}

resource "aws_dynamodb_table_item" "pipeline_config" {
  for_each   = local.active_pipeline_files
  table_name = module.interlock.control_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK     = { S = "PIPELINE#${trimsuffix(each.value, ".yaml")}" }
    SK     = { S = "CONFIG" }
    config = { S = jsonencode(yamldecode(templatefile("${path.module}/../../pipelines/${each.value}", local.pipeline_template_vars))) }
  })
}
