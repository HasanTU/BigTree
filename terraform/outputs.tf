output "s3_bucket_name" {
  description = "Name of the provisioned S3 Data Lake bucket"
  value       = aws_s3_bucket.dubaimai_lake.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 Data Lake bucket"
  value       = aws_s3_bucket.dubaimai_lake.arn
}

output "lambda_function_name" {
  description = "Name of the Weather Ingestion Lambda function"
  value       = aws_lambda_function.weather_ingestion.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Weather Ingestion Lambda function"
  value       = aws_lambda_function.weather_ingestion.arn
}

output "test_invocation_command" {
  description = "AWS CLI command to invoke the Lambda function manually"
  value       = "aws lambda invoke --region ${var.aws_region} --function-name ${aws_lambda_function.weather_ingestion.function_name} --payload '{\"start_date\":\"2023-04-01\",\"end_date\":\"2023-04-05\"}' response.json && cat response.json | jq ."
}
