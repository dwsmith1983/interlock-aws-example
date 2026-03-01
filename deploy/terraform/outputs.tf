output "telecom_data_bucket" {
  description = "Name of the S3 bucket for generated telecom data"
  value       = aws_s3_bucket.telecom_data.id
}

output "telecom_data_bucket_arn" {
  description = "ARN of the S3 bucket for generated telecom data"
  value       = aws_s3_bucket.telecom_data.arn
}

output "generator_function_name" {
  description = "Name of the telecom generator Lambda function"
  value       = aws_lambda_function.telecom_generator.function_name
}

output "generator_function_arn" {
  description = "ARN of the telecom generator Lambda function"
  value       = aws_lambda_function.telecom_generator.arn
}
