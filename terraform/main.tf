provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "Dubaimai"
      Course    = "CS341"
      ManagedBy = "Terraform"
      Role      = "Person1-Ingestion"
    }
  }
}

# Unique suffix for S3 bucket globally unique namespace
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# -----------------------------------------------------------------------------
# 1. S3 Data Lake Storage
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "dubaimai_lake" {
  bucket        = "${var.project_name}-data-${var.environment}-${random_id.bucket_suffix.hex}"
  force_destroy = true # Useful for student/dev teardown
}

resource "aws_s3_bucket_versioning" "lake_versioning" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake_encryption" {
  bucket = aws_s3_bucket.dubaimai_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake_public_block" {
  bucket = aws_s3_bucket.dubaimai_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Folder Prefixes matching team specification
resource "aws_s3_object" "folder_raw_weather" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "raw/weather/"
}

resource "aws_s3_object" "folder_spatial" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "spatial/"
}

resource "aws_s3_object" "folder_curated" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "curated/"
}

resource "aws_s3_object" "folder_not_pass" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "not_pass/"
}

# Seed initial coordinates CSV into spatial/ prefix
resource "aws_s3_object" "seed_coordinates" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "spatial/district_coordinates.csv"
  source = "${path.module}/../data/sample_district_coordinates.csv"
  etag   = filemd5("${path.module}/../data/sample_district_coordinates.csv")
}

# -----------------------------------------------------------------------------
# 2. Packaging Lambda Artifact
# -----------------------------------------------------------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/dist/ingestion_lambda.zip"

  source {
    content  = file("${path.module}/../src/bigtree/__init__.py")
    filename = "bigtree/__init__.py"
  }
  source {
    content  = file("${path.module}/../src/bigtree/ingestion/__init__.py")
    filename = "bigtree/ingestion/__init__.py"
  }
  source {
    content  = file("${path.module}/../src/bigtree/ingestion/weather_client.py")
    filename = "bigtree/ingestion/weather_client.py"
  }
  source {
    content  = file("${path.module}/../src/bigtree/ingestion/weather_collector.py")
    filename = "bigtree/ingestion/weather_collector.py"
  }
  source {
    content  = file("${path.module}/../src/bigtree/ingestion/s3_uploader.py")
    filename = "bigtree/ingestion/s3_uploader.py"
  }
  source {
    content  = file("${path.module}/../src/bigtree/ingestion/handler.py")
    filename = "bigtree/ingestion/handler.py"
  }
  source {
    content  = file("${path.module}/../data/sample_district_coordinates.csv")
    filename = "data/sample_district_coordinates.csv"
  }
}

# -----------------------------------------------------------------------------
# 3. IAM Least-Privilege Execution Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-ingestion-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-ingestion-policy-${var.environment}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Sid    = "S3DubaimaiAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.dubaimai_lake.arn,
          "${aws_s3_bucket.dubaimai_lake.arn}/*"
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# 4. AWS Lambda Ingestion Function
# -----------------------------------------------------------------------------
# AWS Managed Pandas / Requests Layer for Python 3.12 in ap-southeast-1
# Official ARN provided by AWS SDK for pandas (AWS Data Wrangler)
locals {
  pandas_layer_arn = "arn:aws:lambda:${var.aws_region}:336392948345:layer:AWSSDKPandas-Python312:12"
}

resource "aws_lambda_function" "weather_ingestion" {
  function_name    = "${var.project_name}-weather-ingestion-${var.environment}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "bigtree.ingestion.handler.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 180 # 3 minutes covers 50 API calls safely with retries
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  layers = [local.pandas_layer_arn]

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.dubaimai_lake.id
      START_DATE     = var.default_start_date
      END_DATE       = var.default_end_date
      S3_PREFIX      = "raw/weather"
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_policy,
  ]
}

# -----------------------------------------------------------------------------
# 5. Optional EventBridge Cron Trigger
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "schedule" {
  count               = var.schedule_cron != "" ? 1 : 0
  name                = "${var.project_name}-weather-cron-${var.environment}"
  description         = "Periodic trigger for Dubaimai weather ingestion"
  schedule_expression = var.schedule_cron
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  count     = var.schedule_cron != "" ? 1 : 0
  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "IngestionLambdaTarget"
  arn       = aws_lambda_function.weather_ingestion.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  count         = var.schedule_cron != "" ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.weather_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
