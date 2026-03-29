output "chaos_controller_function_name" {
  description = "Name of the chaos controller Lambda function"
  value       = aws_lambda_function.chaos_controller.function_name
}

output "chaos_controller_function_arn" {
  description = "ARN of the chaos controller Lambda function"
  value       = aws_lambda_function.chaos_controller.arn
}

output "chaos_schedule_rule_name" {
  description = "Name of the EventBridge chaos schedule rule"
  value       = aws_cloudwatch_event_rule.chaos_schedule.name
}

output "chaos_schedule_rule_arn" {
  description = "ARN of the EventBridge chaos schedule rule"
  value       = aws_cloudwatch_event_rule.chaos_schedule.arn
}
