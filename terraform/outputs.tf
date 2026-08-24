output "bucket_name" {
  description = "S3 bucket to upload CSV files into (under raw/)"
  value       = aws_s3_bucket.data_bucket.id
}

output "dynamodb_table" {
  description = "DynamoDB table where clean records land"
  value       = aws_dynamodb_table.orders_table.name
}

output "lambda_function_name" {
  value = aws_lambda_function.etl_handler.function_name
}

output "dlq_url" {
  description = "SQS dead-letter queue for failed records"
  value       = aws_sqs_queue.dlq.url
}
