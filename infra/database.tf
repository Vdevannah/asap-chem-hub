# RDS MySQL 8.4, single-AZ, private. App users (asap_api, asap_jobs) log in with RDS IAM auth tokens;
# the master password is created and rotated by RDS in Secrets Manager (never in Terraform state).

data "aws_rds_engine_version" "mysql" {
  engine  = "mysql"
  version = "8.4"
  latest  = true
}

# Fails at plan time if db.t4g.micro + gp3 is not orderable for this engine version
data "aws_rds_orderable_db_instance" "mysql" {
  engine         = data.aws_rds_engine_version.mysql.engine
  engine_version = data.aws_rds_engine_version.mysql.version_actual
  instance_class = var.db_instance_class
  storage_type   = "gp3"
}

resource "aws_db_subnet_group" "db" {
  name       = "${local.name}-db"
  subnet_ids = local.subnet_ids
}

resource "aws_db_parameter_group" "mysql" {
  name        = "${local.name}-mysql84"
  family      = data.aws_rds_engine_version.mysql.parameter_group_family
  description = "TLS required; utf8mb4 / utf8mb4_unicode_ci like the local database"

  parameter {
    name  = "require_secure_transport"
    value = "1"
  }
  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }
  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }
}

resource "aws_db_instance" "db" {
  identifier     = "${local.name}-db"
  engine         = "mysql"
  engine_version = data.aws_rds_orderable_db_instance.mysql.engine_version
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true
  # no max_allocated_storage: storage autoscaling stays off (no surprise growth)

  db_name                             = var.db_name
  username                            = var.db_master_username
  manage_master_user_password         = true
  iam_database_authentication_enabled = true

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.mysql.name
  publicly_accessible    = false
  multi_az               = false
  ca_cert_identifier     = "rds-ca-rsa2048-g1"

  backup_retention_period    = 7
  copy_tags_to_snapshot      = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${local.name}-db-final"
  auto_minor_version_upgrade = true

  performance_insights_enabled = false
  monitoring_interval          = 0
}
