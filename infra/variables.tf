variable "region" {
  description = "Home region of this AWS project account (the managed SCP denies most regional services elsewhere)"
  type        = string
  default     = "us-east-2"
}

variable "project" {
  description = "Name prefix, and the value of the Project tag on every resource"
  type        = string
  default     = "asap-chem-hub"
}

variable "excluded_azs" {
  description = "Default-VPC availability zones not to use (none needed in us-east-2: a, b and c all support t4g, arm64 Lambda and Fargate ARM)"
  type        = list(string)
  default     = []
}

# --- database ---
variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "asap_chem_hub"
}

variable "db_master_username" {
  description = "RDS master user (password managed by RDS in Secrets Manager); only for the admin task"
  type        = string
  default     = "asap_admin"
}

# --- API ---
variable "lambda_zip" {
  description = "Lambda package built by infra/build_lambda.sh"
  type        = string
  default     = "../build/lambda/api.zip"
}

variable "lambda_runtime" {
  description = "Newest generally available Lambda Python runtime (checked in the AWS docs, Nov 2026); same Python as Dockerfile.jobs"
  type        = string
  default     = "python3.14"
}

variable "lambda_reserved_concurrency" {
  description = "Caps simultaneous API instances (one reused MySQL connection each) so they cannot exhaust the db.t4g.micro's MySQL connections or run up cost. The account's Lambda concurrency is 400; AWS keeps at least 100 unreserved. Set to -1 for no reservation."
  type        = number
  default     = 25
}

variable "api_cache_seconds" {
  description = "CloudFront cache time for /api/* responses (query string is part of the cache key)"
  type        = number
  default     = 60
}

# --- jobs ---
variable "jobs_image_tag" {
  description = "Tag of the jobs image in ECR (Dockerfile.jobs)"
  type        = string
  default     = "latest"
}

variable "schedules_enabled" {
  description = "Turn the EventBridge schedules on only after the data migration is verified"
  type        = bool
  default     = false
}

variable "ssm_parameter_names" {
  description = "SecureString parameters under /<project>/ created by scripts/put_ssm_params.py (values never in Terraform)"
  type        = list(string)
  default     = ["EPO_KEY", "EPO_SECRET", "SPRINGER_META_KEY", "SPRINGER_OA_KEY", "CROSSREF_MAILTO"]
}

# --- optional custom domain (later) ---
variable "domain_name" {
  description = "Custom domain for the site, e.g. asapchemhub.org. Empty = the *.cloudfront.net address."
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate covering domain_name (required when domain_name is set). Must be in us-east-1 (CloudFront), even though the stack is in us-east-2."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone for domain_name; when set, Terraform adds the alias records. Empty = manage DNS elsewhere."
  type        = string
  default     = ""
}
