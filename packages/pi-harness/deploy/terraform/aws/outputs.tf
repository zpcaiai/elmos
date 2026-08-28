output "exact_target" {
  value = {
    account_id  = data.aws_caller_identity.current.account_id
    region      = data.aws_region.current.region
    environment = var.environment
  }
}

output "artifact_bucket" {
  value = {
    name        = aws_s3_bucket.artifacts.id
    kms_key_arn = aws_kms_key.data.arn
  }
}

output "database" {
  value = {
    arn                     = aws_db_instance.database.arn
    endpoint                = aws_db_instance.database.endpoint
    engine_version          = aws_db_instance.database.engine_version_actual
    master_user_secret      = aws_db_instance.database.master_user_secret
    security_group_id       = aws_security_group.database.id
    publicly_accessible     = aws_db_instance.database.publicly_accessible
    deletion_protection     = aws_db_instance.database.deletion_protection
    backup_retention_period = aws_db_instance.database.backup_retention_period
  }
  sensitive = true
}
