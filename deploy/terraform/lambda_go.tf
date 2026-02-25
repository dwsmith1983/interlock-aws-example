# =============================================================================
# Core Go Lambdas (orchestrator, evaluator, trigger, run-checker)
# =============================================================================

data "archive_file" "go_lambda" {
  for_each = local.core_lambda_names

  type        = "zip"
  source_file = "${path.module}/${var.lambda_dist_dir}/${each.key}/bootstrap"
  output_path = "${path.module}/.build/${each.key}.zip"
}

resource "aws_lambda_function" "go" {
  for_each = local.core_lambda_names

  function_name = "${var.table_name}-${each.key}"
  role          = local.go_lambda_roles[each.key]
  handler       = "bootstrap"
  runtime       = "provided.al2023"
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  filename         = data.archive_file.go_lambda[each.key].output_path
  source_code_hash = data.archive_file.go_lambda[each.key].output_base64sha256

  layers = [aws_lambda_layer_version.archetypes.arn]

  environment {
    variables = merge(
      local.go_lambda_common_env,
      {
        EVALUATOR_BASE_URL = var.evaluator_base_url != "" ? var.evaluator_base_url : "https://${aws_apigatewayv2_api.evaluator.id}.execute-api.${data.aws_region.current.name}.amazonaws.com"
      }
    )
  }

  depends_on = [aws_cloudwatch_log_group.go_lambda]
}

resource "aws_cloudwatch_log_group" "go_lambda" {
  for_each = local.core_lambda_names

  name              = "/aws/lambda/${var.table_name}-${each.key}"
  retention_in_days = var.log_retention_days
}

# =============================================================================
# Stream-router (separate to break dependency cycle with SFN)
# =============================================================================

data "archive_file" "stream_router" {
  type        = "zip"
  source_file = "${path.module}/${var.lambda_dist_dir}/stream-router/bootstrap"
  output_path = "${path.module}/.build/stream-router.zip"
}

resource "aws_lambda_function" "stream_router" {
  function_name = "${var.table_name}-stream-router"
  role          = aws_iam_role.stream_router.arn
  handler       = "bootstrap"
  runtime       = "provided.al2023"
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  filename         = data.archive_file.stream_router.output_path
  source_code_hash = data.archive_file.stream_router.output_base64sha256

  environment {
    variables = merge(
      local.go_lambda_common_env,
      {
        STATE_MACHINE_ARN = aws_sfn_state_machine.pipeline.arn
      }
    )
  }

  depends_on = [aws_cloudwatch_log_group.stream_router]
}

resource "aws_cloudwatch_log_group" "stream_router" {
  name              = "/aws/lambda/${var.table_name}-stream-router"
  retention_in_days = var.log_retention_days
}

# DynamoDB Stream -> stream-router
resource "aws_lambda_event_source_mapping" "stream_router" {
  event_source_arn  = aws_dynamodb_table.main.stream_arn
  function_name     = aws_lambda_function.stream_router.arn
  starting_position = "TRIM_HORIZON"
  batch_size        = 10
}
