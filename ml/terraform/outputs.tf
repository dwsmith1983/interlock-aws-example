output "generator_function_name" {
  description = "Name of the ML generator Lambda"
  value       = aws_lambda_function.ml_generator.function_name
}

output "data_prep_function_name" {
  description = "Name of the ML data prep Lambda"
  value       = aws_lambda_function.ml_data_prep.function_name
}

output "training_function_name" {
  description = "Name of the ML training Lambda"
  value       = aws_lambda_function.ml_training.function_name
}

output "evaluation_function_name" {
  description = "Name of the ML evaluation Lambda"
  value       = aws_lambda_function.ml_evaluation.function_name
}

output "deployment_function_name" {
  description = "Name of the ML deployment Lambda"
  value       = aws_lambda_function.ml_deployment.function_name
}
