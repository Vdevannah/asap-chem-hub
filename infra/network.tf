# Default VPC, no NAT gateway, no VPC endpoints.
# - Lambda ENIs and RDS sit in the default subnets (RDS is not publicly accessible).
# - Fargate tasks get a public IP for RSS, Crossref, Springer, EPO and AWS APIs (ECR, SSM, Logs, S3).

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnet" "default" {
  for_each = toset(data.aws_subnets.default.ids)
  id       = each.value
}

locals {
  subnet_ids = sort([for s in data.aws_subnet.default : s.id if !contains(var.excluded_azs, s.availability_zone)])
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "RDS MySQL: only the API Lambda and the Fargate jobs"
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "${local.name}-db" }
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "API Lambda: MySQL only"
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "${local.name}-api" }
}

resource "aws_security_group" "jobs" {
  name        = "${local.name}-jobs"
  description = "Fargate jobs: HTTPS/HTTP out, MySQL"
  vpc_id      = data.aws_vpc.default.id
  tags        = { Name = "${local.name}-jobs" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_api" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from the API Lambda"
}

resource "aws_vpc_security_group_ingress_rule" "db_from_jobs" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.jobs.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from the Fargate jobs"
}

resource "aws_vpc_security_group_egress_rule" "api_to_db" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL"
}

resource "aws_vpc_security_group_egress_rule" "jobs_to_db" {
  security_group_id            = aws_security_group.jobs.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL"
}

resource "aws_vpc_security_group_egress_rule" "jobs_https" {
  security_group_id = aws_security_group.jobs.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Feeds, Crossref, Springer, EPO, AWS APIs"
}

resource "aws_vpc_security_group_egress_rule" "jobs_http" {
  security_group_id = aws_security_group.jobs.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "Feeds that redirect from http"
}
