# Data lake: what data-pipeline writes to when SINK_MODE=s3, replacing the
# local volume it uses in docker-compose.

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "data_lake" {
  bucket = "${local.name_prefix}-data-lake-${random_id.bucket_suffix.hex}"

  # Bucket names are globally unique, hence the random suffix.
  #
  # force_destroy lets `terraform destroy` delete the bucket even when it
  # still holds objects. Without it, teardown fails on a non-empty bucket —
  # the most common way a demo stack is left behind, still billing.
  force_destroy = true

  tags = { Name = "${local.name_prefix}-data-lake" }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "expire-raw-events"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
  }
}
