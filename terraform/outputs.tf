output "s3_bucket_name" {
  description = "Name of the provisioned S3 Data Lake bucket"
  value       = aws_s3_bucket.dubaimai_lake.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 Data Lake bucket"
  value       = aws_s3_bucket.dubaimai_lake.arn
}

output "step_functions_state_machine_name" {
  description = "Name of the Step Functions Pipeline Orchestrator"
  value       = aws_sfn_state_machine.pipeline.name
}

output "step_functions_state_machine_arn" {
  description = "ARN of the Step Functions Pipeline Orchestrator"
  value       = aws_sfn_state_machine.pipeline.arn
}

output "lambda_weather_ingestion" {
  description = "Weather Ingestion Lambda Function (Person 1)"
  value       = aws_lambda_function.weather_ingestion.function_name
}

output "lambda_data_transformation" {
  description = "Data Transformation Lambda Function (Person 3)"
  value       = aws_lambda_function.data_transformation.function_name
}

output "lambda_research_analysis" {
  description = "Research Analysis Lambda Function (Person 4)"
  value       = aws_lambda_function.research_analysis.function_name
}

output "start_pipeline_command" {
  description = "AWS CLI command to run the entire pipeline end-to-end via Step Functions"
  value       = "aws stepfunctions start-execution --region ${var.aws_region} --state-machine-arn ${aws_sfn_state_machine.pipeline.arn} --input '{\"bucket_name\":\"${aws_s3_bucket.dubaimai_lake.id}\"}'"
}
