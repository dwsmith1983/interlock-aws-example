resource "aws_glue_job" "etl" {
  for_each = local.glue_jobs

  name     = each.key
  role_arn = aws_iam_role.glue.arn

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data.id}/glue-scripts/${each.value}"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_workers
  timeout           = var.glue_timeout_minutes

  default_arguments = {
    "--datalake-formats" = "delta"
    "--bucket"           = aws_s3_bucket.data.id
    "--table_name"       = aws_dynamodb_table.main.name
    "--source"           = element(split("-", each.key), 2)
    "--tier"             = element(split("-", each.key), 1)
  }
}
