provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      DataClass   = "confidential"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  artifact_bucket_name = join("-", [
    local.name_prefix,
    data.aws_caller_identity.current.account_id,
    var.aws_region,
    "artifacts",
  ])
}

resource "aws_kms_key" "application" {
  description             = "Criptografia de artefatos e filas do ${local.name_prefix}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "application" {
  name          = "alias/${local.name_prefix}-application"
  target_key_id = aws_kms_key.application.key_id
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.artifact_bucket_name
  force_destroy = false
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.application.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  # Retenção por CLASSE de objeto (ADR-0051): só expira o que o app marca como efêmero.
  # A evidência de campo durável (`surveys/`, `jobs/*/field-evidence/`) nasce sem a tag e
  # nunca entra aqui. Fail-safe: enquanto o app não marcar, nada expira.
  rule {
    id     = "expire-ephemeral-artifacts"
    status = "Enabled"

    filter {
      tag {
        key   = "lifecycle-class"
        value = "ephemeral"
      }
    }

    expiration {
      days = var.artifact_retention_days
    }
  }

  # Uploads multipart abandonados são sempre lixo, independem de classe.
  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  cors_rule {
    allowed_headers = ["Content-Type", "x-amz-checksum-sha256"]
    allowed_methods = ["PUT", "HEAD"]
    allowed_origins = [var.web_origin]
    expose_headers  = ["ETag"]
    max_age_seconds = 300
  }
}

resource "aws_sqs_queue" "processing_dead_letter" {
  name                      = "${local.name_prefix}-processing-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.application.arn
}

resource "aws_sqs_queue" "processing" {
  name                       = "${local.name_prefix}-processing"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  kms_master_key_id          = aws_kms_key.application.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.processing_dead_letter.arn
    maxReceiveCount     = 3
  })
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/aws/${var.project_name}/${var.environment}/application"
  retention_in_days = 30
}
