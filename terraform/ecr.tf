# One repository per service. Images are built and pushed by
# scripts/push_images.sh, not by Terraform.

resource "aws_ecr_repository" "services" {
  for_each = local.services

  name                 = "${local.name_prefix}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # let `terraform destroy` remove repos that still hold images

  image_scanning_configuration { scan_on_push = true }

  tags = { Name = "${local.name_prefix}-${each.key}" }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}
