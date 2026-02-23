# HTTP API for custom evaluator
resource "aws_apigatewayv2_api" "evaluator" {
  name          = "${var.table_name}-evaluator-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.evaluator.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "evaluator" {
  api_id                 = aws_apigatewayv2_api.evaluator.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.python["custom-evaluator"].arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "evaluator" {
  api_id    = aws_apigatewayv2_api.evaluator.id
  route_key = "POST /evaluate/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.evaluator.id}"
}

# Grant API Gateway permission to invoke the evaluator Lambda
resource "aws_lambda_permission" "api_gw_evaluator" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.python["custom-evaluator"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.evaluator.execution_arn}/*/*"
}
