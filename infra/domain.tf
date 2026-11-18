# Optional custom domain for the site: <domain_name> and www.<domain_name> on the CloudFront distribution.
# Nothing here exists while domain_name is "" (the site stays on its *.cloudfront.net address).
#
# The domain itself is bought by hand at an outside registrar: this account is on the AWS Free plan,
# where Route 53 Domains answers "Free Tier accounts are not supported for this service", and AWS
# promotional credits never cover domain registration.
#
# dns_mode = "route53"   Terraform creates a Route 53 hosted zone ($0.50/month), the ACM certificate's
#                        validation records and A/AAAA alias records for both names. You point the
#                        domain's name servers at the registrar to output route53_name_servers.
# dns_mode = "external"  DNS stays at the registrar. Terraform creates only the ACM certificate; you add
#                        the records from outputs acm_validation_records and registrar_dns_records by hand.
#
# The certificate is in us-east-1 because CloudFront only uses certificates from there (allowed by the
# project SCP, which permits acm:*, route53:* and cloudfront:* in us-east-1). ACM public certificates
# used with CloudFront are free and renew automatically while the validation CNAMEs stay in DNS.

locals {
  site_names  = local.custom_domain ? [var.domain_name, "www.${var.domain_name}"] : []
  use_route53 = local.custom_domain && var.dns_mode == "route53"
}

resource "aws_route53_zone" "site" {
  count   = local.use_route53 ? 1 : 0
  name    = var.domain_name
  comment = "ASAP Chem Hub site (CloudFront)"
}

resource "aws_acm_certificate" "site" {
  count                     = local.custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"
  key_algorithm             = "RSA_2048"

  lifecycle {
    create_before_destroy = true
  }
}

# Route 53 mode: one DNS validation CNAME per name. Keyed on the names (known at plan time), not on
# domain_validation_options (known only after the certificate is requested).
resource "aws_route53_record" "cert_validation" {
  for_each        = local.use_route53 ? toset(local.site_names) : toset([])
  zone_id         = aws_route53_zone.site[0].zone_id
  name            = local.cert_validation[each.key].resource_record_name
  type            = local.cert_validation[each.key].resource_record_type
  records         = [local.cert_validation[each.key].resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

locals {
  cert_validation = local.custom_domain ? {
    for o in aws_acm_certificate.site[0].domain_validation_options : o.domain_name => o
  } : {}
}

# Waits until ACM has issued the certificate. In external mode that happens only after you add the
# validation CNAMEs at the registrar, so apply first with -target=aws_acm_certificate.site, add the
# records from output acm_validation_records, then run the full apply.
resource "aws_acm_certificate_validation" "site" {
  count                   = local.custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = local.use_route53 ? [for r in aws_route53_record.cert_validation : r.fqdn] : null

  timeouts {
    create = "2h"
  }
}

# Route 53 mode: apex and www -> CloudFront, IPv4 and IPv6 (alias queries to CloudFront are free)
resource "aws_route53_record" "site" {
  for_each = local.use_route53 ? {
    for p in setproduct(local.site_names, ["A", "AAAA"]) : "${p[0]} ${p[1]}" => { name = p[0], type = p[1] }
  } : {}
  zone_id = aws_route53_zone.site[0].zone_id
  name    = each.value.name
  type    = each.value.type
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

output "route53_name_servers" {
  description = "dns_mode=route53: set these four as the domain's name servers at the registrar"
  value       = local.use_route53 ? aws_route53_zone.site[0].name_servers : null
}

output "acm_validation_records" {
  description = "dns_mode=external: add these CNAMEs at the registrar (and keep them, for automatic renewal)"
  value = local.custom_domain && !local.use_route53 ? distinct([
    for o in aws_acm_certificate.site[0].domain_validation_options :
    { name = o.resource_record_name, type = o.resource_record_type, value = o.resource_record_value }
  ]) : null
}

output "registrar_dns_records" {
  description = "dns_mode=external: records pointing the site at CloudFront, to add at the registrar"
  value = local.custom_domain && !local.use_route53 ? [
    { name = "www.${var.domain_name}", type = "CNAME", value = aws_cloudfront_distribution.site.domain_name },
    { name = var.domain_name, type = "ALIAS / ANAME / flattened CNAME (registrar-specific)", value = aws_cloudfront_distribution.site.domain_name },
  ] : null
}
