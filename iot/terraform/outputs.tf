output "generator_function_name" {
  description = "Name of the IoT generator Lambda"
  value       = aws_lambda_function.iot_generator.function_name
}

output "consumer_function_name" {
  description = "Name of the IoT consumer Lambda"
  value       = aws_lambda_function.iot_consumer.function_name
}

output "aggregator_function_name" {
  description = "Name of the IoT aggregator Lambda"
  value       = aws_lambda_function.iot_aggregator.function_name
}
