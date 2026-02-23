# Scheduled rules for ingestion Lambdas
resource "aws_cloudwatch_event_rule" "ingest" {
  for_each = local.eventbridge_rules

  name                = "${var.table_name}-${each.key}"
  schedule_expression = "rate(${each.value.rate_minutes} ${each.value.rate_minutes == 1 ? "minute" : "minutes"})"
}

resource "aws_cloudwatch_event_target" "ingest" {
  for_each = local.eventbridge_rules

  rule = aws_cloudwatch_event_rule.ingest[each.key].name
  arn  = aws_lambda_function.python[each.key].arn
}

resource "aws_lambda_permission" "eventbridge" {
  for_each = local.eventbridge_rules

  statement_id  = "AllowEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.python[each.key].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest[each.key].arn
}
