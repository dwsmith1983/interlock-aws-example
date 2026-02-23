# Zip each Python Lambda
data "archive_file" "python_lambda" {
  for_each = local.python_lambdas

  type        = "zip"
  source_dir  = "${path.module}/${var.python_lambdas_dir}/${each.value.source_dir}"
  output_path = "${path.module}/.build/py-${each.key}.zip"
}

# Python Lambda functions
resource "aws_lambda_function" "python" {
  for_each = local.python_lambdas

  function_name = "${var.table_name}-${each.key}"
  role          = local.python_lambda_roles[each.key]
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = each.value.timeout

  filename         = data.archive_file.python_lambda[each.key].output_path
  source_code_hash = data.archive_file.python_lambda[each.key].output_base64sha256

  layers = [aws_lambda_layer_version.python_shared.arn]

  environment {
    variables = {
      TABLE_NAME  = aws_dynamodb_table.main.name
      BUCKET_NAME = aws_s3_bucket.data.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.python_lambda]
}

# CloudWatch log groups with retention
resource "aws_cloudwatch_log_group" "python_lambda" {
  for_each = local.python_lambdas

  name              = "/aws/lambda/${var.table_name}-${each.key}"
  retention_in_days = var.log_retention_days
}
