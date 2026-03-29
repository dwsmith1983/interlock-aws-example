# Pipeline dependency graph for cross-pipeline blast radius computation.
# Each item maps a pipeline to one downstream pipeline. The chaos controller's
# DependencyResolver walks these records transitively via BFS.

locals {
  pipeline_dependencies = [
    # Bronze → Silver
    { pipeline = "bronze-cdr", downstream = "silver-cdr-hour" },
    { pipeline = "bronze-cdr", downstream = "silver-cdr-day" },
    { pipeline = "bronze-seq", downstream = "silver-seq-hour" },
    { pipeline = "bronze-seq", downstream = "silver-seq-day" },

    # ML chain
    { pipeline = "ml-data-prep", downstream = "ml-training" },
    { pipeline = "ml-training",  downstream = "ml-evaluation" },
    { pipeline = "ml-evaluation", downstream = "ml-deployment" },
  ]
}

resource "aws_dynamodb_table_item" "pipeline_deps" {
  for_each = {
    for dep in local.pipeline_dependencies :
    "${dep.pipeline}::${dep.downstream}" => dep
  }

  table_name = var.interlock_control_table_name
  hash_key   = "PK"
  range_key  = "SK"

  item = jsonencode({
    PK = { S = "DEPS#${each.value.pipeline}" }
    SK = { S = "DOWNSTREAM#${each.value.downstream}" }
  })
}
