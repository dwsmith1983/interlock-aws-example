resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.table_name}-pipeline"
  type     = "STANDARD"
  role_arn = aws_iam_role.sfn.arn

  definition = templatefile("${path.module}/${var.asl_path}", {
    OrchestratorFunctionArn = aws_lambda_function.go["orchestrator"].arn
    EvaluatorFunctionArn    = aws_lambda_function.go["evaluator"].arn
    TriggerFunctionArn      = aws_lambda_function.go["trigger"].arn
    RunCheckerFunctionArn   = aws_lambda_function.go["run-checker"].arn
    AlertTopicArn           = aws_sns_topic.alerts.arn
  })
}
