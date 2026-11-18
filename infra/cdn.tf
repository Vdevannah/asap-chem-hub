# One CloudFront distribution: the React site from S3, and /api/* to the Lambda Function URL.
# Same domain for both, so the browser needs no CORS.

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.name}-site"
  description                       = "CloudFront -> private S3 site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "${local.name}-api"
  description                       = "CloudFront -> Lambda Function URL (AWS_IAM)"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# API responses: cached var.api_cache_seconds; the whole query string is part of the cache key
# (q, journals, topics, days, since, limit, offset ...). No cookies, no headers in the key.
resource "aws_cloudfront_cache_policy" "api" {
  name        = "${local.name}-api-${var.api_cache_seconds}s"
  comment     = "API: ${var.api_cache_seconds} s, keyed on all query strings"
  min_ttl     = 0
  default_ttl = var.api_cache_seconds
  max_ttl     = var.api_cache_seconds

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    query_strings_config {
      query_string_behavior = "all"
    }
    headers_config {
      header_behavior = "none"
    }
    cookies_config {
      cookie_behavior = "none"
    }
  }
}

locals {
  api_origin_domain = replace(replace(aws_lambda_function_url.api.function_url, "https://", ""), "/", "")
  custom_domain     = var.domain_name != ""
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "ASAP Chem Hub"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  aliases             = local.site_names # apex + www (domain.tf)

  origin {
    origin_id                = "site"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  origin {
    origin_id                = "api"
    domain_name              = local.api_origin_domain
    origin_access_control_id = aws_cloudfront_origin_access_control.api.id
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Website (hashed asset names cache for long; index.html is uploaded with a short Cache-Control)
  default_cache_behavior {
    target_origin_id           = "site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
  }

  # API: /api/* -> Lambda (Mangum strips the /api prefix). Read-only API: GET/HEAD/OPTIONS.
  ordered_cache_behavior {
    path_pattern               = "/api/*"
    target_origin_id           = "api"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.api.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # *.cloudfront.net certificate, or the issued ACM certificate when domain_name is set (domain.tf)
  viewer_certificate {
    cloudfront_default_certificate = !local.custom_domain
    acm_certificate_arn            = local.custom_domain ? aws_acm_certificate_validation.site[0].certificate_arn : null
    ssl_support_method             = local.custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }
}
