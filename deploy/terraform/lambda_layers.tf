# Archetype layer — YAML definitions at /opt/archetypes
data "archive_file" "archetype_layer" {
  type        = "zip"
  output_path = "${path.module}/.build/archetype-layer.zip"
  source_dir  = "${path.module}/../dist/layer"
}

resource "aws_lambda_layer_version" "archetypes" {
  layer_name               = "${var.table_name}-archetypes"
  filename                 = data.archive_file.archetype_layer.output_path
  source_code_hash         = data.archive_file.archetype_layer.output_base64sha256
  compatible_runtimes      = ["provided.al2023"]
  compatible_architectures = ["arm64"]
  description              = "Interlock archetype definitions"
}

# Python shared layer — helpers + requests at /opt/python
data "archive_file" "python_layer" {
  type        = "zip"
  output_path = "${path.module}/.build/python-layer.zip"
  source_dir  = "${path.module}/../dist/python-layer"
}

resource "aws_lambda_layer_version" "python_shared" {
  layer_name          = "${var.table_name}-python-shared"
  filename            = data.archive_file.python_layer.output_path
  source_code_hash    = data.archive_file.python_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
  description         = "Shared Python helpers for medallion ingestion"
}
