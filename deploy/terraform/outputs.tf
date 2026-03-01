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

output "kinesis_stream_name" {
  description = "Name of the Kinesis stream for raw S3 events"
  value       = aws_kinesis_stream.raw_events.name
}

output "bronze_function_name" {
  description = "Name of the bronze consumer Lambda function"
  value       = aws_lambda_function.bronze_consumer.function_name
}

output "phone_hash_table_name" {
  description = "Name of the phone hash DynamoDB table"
  value       = aws_dynamodb_table.phone_hash.name
}

output "glue_job_names" {
  description = "Names of the Glue aggregation jobs"
  value = {
    cdr_agg_hour = aws_glue_job.cdr_agg_hour.name
    cdr_agg_day  = aws_glue_job.cdr_agg_day.name
    seq_agg_hour = aws_glue_job.seq_agg_hour.name
    seq_agg_day  = aws_glue_job.seq_agg_day.name
  }
}

output "interlock_control_table" {
  description = "Name of the Interlock control DynamoDB table"
  value       = module.interlock.control_table_name
}

output "interlock_event_bus" {
  description = "Name of the Interlock EventBridge event bus"
  value       = module.interlock.event_bus_name
}

output "interlock_sfn_arn" {
  description = "ARN of the Interlock Step Functions state machine"
  value       = module.interlock.sfn_arn
}

output "audit_function_url" {
  description = "Function URL for the bronze audit Lambda"
  value       = aws_lambda_function_url.bronze_audit.function_url
}
