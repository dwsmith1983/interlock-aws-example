output "kinesis_stream_name" {
  description = "Name of the banking transactions Kinesis stream"
  value       = aws_kinesis_stream.banking_transactions.name
}

output "kinesis_stream_arn" {
  description = "ARN of the banking transactions Kinesis stream"
  value       = aws_kinesis_stream.banking_transactions.arn
}

output "generator_function_name" {
  description = "Name of the banking generator Lambda"
  value       = aws_lambda_function.banking_generator.function_name
}

output "consumer_function_name" {
  description = "Name of the banking consumer Lambda"
  value       = aws_lambda_function.banking_consumer.function_name
}

output "aggregator_function_name" {
  description = "Name of the banking aggregator Lambda"
  value       = aws_lambda_function.banking_aggregator.function_name
}
