output "table_name" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.main.name
}

output "bucket_name" {
  description = "S3 data bucket name"
  value       = aws_s3_bucket.data.id
}

output "topic_arn" {
  description = "SNS alert topic ARN"
  value       = aws_sns_topic.alerts.arn
}

output "state_machine_arn" {
  description = "Step Function state machine ARN"
  value       = aws_sfn_state_machine.pipeline.arn
}

output "evaluator_api_url" {
  description = "API Gateway URL for the custom evaluator"
  value       = "https://${aws_apigatewayv2_api.evaluator.id}.execute-api.${data.aws_region.current.name}.amazonaws.com"
}

output "chaos_enabled" {
  description = "Whether chaos testing is enabled"
  value       = var.chaos_enabled
}
