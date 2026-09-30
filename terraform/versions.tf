terraform {
  required_version = ">= 1.9"

  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.60" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }

  # State is local, which is fine for a solo project that is created and
  # destroyed in a session. If this ever outlives a session or gains a
  # second contributor, move it to S3 + DynamoDB locking:
  #
  # backend "s3" {
  #   bucket         = "<your-tfstate-bucket>"
  #   key            = "real-time-ecommerce-platform/terraform.tfstate"
  #   region         = "eu-south-2"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  # Every resource gets these, so a forgotten stack is easy to find in
  # Cost Explorer and easy to identify in the console.
  default_tags {
    tags = {
      Project     = "real-time-ecommerce-platform"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
