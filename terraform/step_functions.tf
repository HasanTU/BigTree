# -----------------------------------------------------------------------------
# AWS Step Functions State Machine: End-to-End Orchestration
# -----------------------------------------------------------------------------

resource "aws_iam_role" "step_functions_role" {
  name = "${var.project_name}-sfn-pipeline-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "step_functions_policy" {
  name = "${var.project_name}-sfn-pipeline-policy-${var.environment}"
  role = aws_iam_role.step_functions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokePipelineLambdas"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.weather_ingestion.arn,
          aws_lambda_function.data_transformation.arn,
          aws_lambda_function.research_analysis.arn
        ]
      }
    ]
  })
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-pipeline-orchestrator-${var.environment}"
  role_arn = aws_iam_role.step_functions_role.arn

  definition = jsonencode({
    Comment = "Dubaimai End-to-End Big Data Critical-Path Pipeline"
    StartAt = "IngestWeatherData"
    States = {
      IngestWeatherData = {
        Type     = "Task"
        Resource = aws_lambda_function.weather_ingestion.arn
        Next     = "TransformAndValidate"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed"]
            IntervalSeconds = 3
            MaxAttempts     = 2
            BackoffRate     = 2.0
          }
        ]
        ResultPath = "$.ingestion_result"
      }

      TransformAndValidate = {
        Type     = "Task"
        Resource = aws_lambda_function.data_transformation.arn
        Next     = "AnalyzeResearchQuestions"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed"]
            IntervalSeconds = 2
            MaxAttempts     = 2
            BackoffRate     = 2.0
          }
        ]
        ResultPath = "$.transformation_result"
      }

      AnalyzeResearchQuestions = {
        Type     = "Task"
        Resource = aws_lambda_function.research_analysis.arn
        End      = true
      }
    }
  })
}

# -----------------------------------------------------------------------------
# Optional EventBridge Rule to trigger Step Functions automatically
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "sfn_schedule" {
  count               = var.schedule_cron != "" ? 1 : 0
  name                = "${var.project_name}-sfn-cron-${var.environment}"
  description         = "Periodic trigger for Dubaimai Step Functions State Machine"
  schedule_expression = var.schedule_cron
}

resource "aws_iam_role" "eventbridge_sfn_role" {
  count = var.schedule_cron != "" ? 1 : 0
  name  = "${var.project_name}-eventbridge-sfn-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_sfn_policy" {
  count = var.schedule_cron != "" ? 1 : 0
  name  = "${var.project_name}-eventbridge-sfn-policy-${var.environment}"
  role  = aws_iam_role.eventbridge_sfn_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [aws_sfn_state_machine.pipeline.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_event_target" "sfn_target" {
  count    = var.schedule_cron != "" ? 1 : 0
  rule     = aws_cloudwatch_event_rule.sfn_schedule[0].name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.eventbridge_sfn_role[0].arn
}
