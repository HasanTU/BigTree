provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "Dubaimai"
      Course    = "CS341"
      ManagedBy = "Terraform"
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

resource "aws_s3_object" "folder_reports" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "reports/"
}

# Seed 50 district coordinates and green space data into S3
resource "aws_s3_object" "seed_coordinates" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "spatial/district_coordinates.csv"
  source = "${path.module}/../data/district_coordinates.csv"
  etag   = filemd5("${path.module}/../data/district_coordinates.csv")
}

resource "aws_s3_object" "seed_green_space" {
  bucket = aws_s3_bucket.dubaimai_lake.id
  key    = "data/green_space.csv"
  source = "${path.module}/../data/green_space.csv"
  etag   = filemd5("${path.module}/../data/green_space.csv")
}

# -----------------------------------------------------------------------------
# 2. Packaging Lambda Artifact
# -----------------------------------------------------------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/dist/pipeline_bundle.zip"
}

# -----------------------------------------------------------------------------
# 3. IAM Least-Privilege Execution Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-pipeline-role-${var.environment}"

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
  name = "${var.project_name}-lambda-pipeline-policy-${var.environment}"
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

locals {
  pandas_layer_arn = "arn:aws:lambda:${var.aws_region}:336392948345:layer:AWSSDKPandas-Python312:12"
}

# -----------------------------------------------------------------------------
# 4. AWS Lambda Pipeline Functions
# -----------------------------------------------------------------------------

# Step 1: Ingestion Lambda (Person 1)
resource "aws_lambda_function" "weather_ingestion" {
  function_name    = "${var.project_name}-weather-ingestion-${var.environment}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "bigtree.ingestion.handler.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 256
  timeout          = 180
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

  depends_on = [aws_iam_role_policy.lambda_policy]
}

# Step 2: Transformation & Quality Validation Lambda (Person 3)
resource "aws_lambda_function" "data_transformation" {
  function_name    = "${var.project_name}-data-transformation-${var.environment}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "bigtree.entrypoints.lambda_transform.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 120
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  layers = [local.pandas_layer_arn]

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.dubaimai_lake.id
    }
  }

  depends_on = [aws_iam_role_policy.lambda_policy]
}

# Step 3: Statistical Research Analysis Lambda (Person 4)
resource "aws_lambda_function" "research_analysis" {
  function_name    = "${var.project_name}-research-analysis-${var.environment}"
  role             = aws_iam_role.lambda_role.arn
  handler          = "bigtree.entrypoints.lambda_analyze.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 120
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  layers = [local.pandas_layer_arn]

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.dubaimai_lake.id
    }
  }

  depends_on = [aws_iam_role_policy.lambda_policy]
}
