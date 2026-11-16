# FastAPI on Lambda (Mangum), in the VPC to reach RDS, exposed only through CloudFront:
# the Function URL uses AWS_IAM auth and CloudFront signs requests with Origin Access Control.

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# ENIs in the VPC + CloudWatch Logs
resource "aws_iam_role_policy_attachment" "api_vpc" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# RDS IAM auth as the read-only user asap_api, nothing else
data "aws_iam_policy_document" "api_db" {
  statement {
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${local.region}:${local.account_id}:dbuser:${aws_db_instance.db.resource_id}/asap_api"]
  }
}

resource "aws_iam_role_policy" "api_db" {
  name   = "rds-iam-connect"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_db.json
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name}-api"
  description      = "ASAP Chem Hub API (FastAPI + Mangum)"
  role             = aws_iam_role.api.arn
  runtime          = var.lambda_runtime
  architectures    = ["arm64"]
  handler          = "api.lambda_handler.handler"
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)
  memory_size      = 512
  timeout          = 15

  reserved_concurrent_executions = var.lambda_reserved_concurrency

  vpc_config {
    subnet_ids         = local.subnet_ids
    security_group_ids = [aws_security_group.api.id]
  }

  environment {
    variables = {
      DB_HOST   = aws_db_instance.db.address
      DB_PORT   = tostring(aws_db_instance.db.port)
      DB_NAME   = var.db_name
      DB_USER   = "asap_api"
      DB_AUTH   = "iam"
      DB_SSL_CA = "/var/task/certs/global-bundle.pem"
      DOCS      = "off"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [aws_iam_role_policy_attachment.api_vpc, aws_cloudwatch_log_group.api]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
}

# CloudFront (this distribution only) may call the Function URL ...
resource "aws_lambda_permission" "cloudfront_url" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.site.arn
  function_url_auth_type = "AWS_IAM"
}

# ... and, as Function URLs now also require, InvokeFunction - but only via the Function URL
resource "aws_lambda_permission" "cloudfront_invoke" {
  statement_id             = "AllowCloudFrontInvokeFunctionViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.site.arn
  invoked_via_function_url = true
}
