#!/usr/bin/env bash
# Builds every service image and pushes it to its ECR repository.
#
# Images are built for linux/arm64 to match the ECS task definitions'
# runtime_platform. On an Apple Silicon Mac that is the native build, so no
# emulation is involved — the reason ARM64 Fargate was chosen over x86.
#
# Run from the repo root, after `terraform apply` has created the ECR repos:
#
#     ./terraform/scripts/push_images.sh
#
# Requires: docker, terraform, aws CLI, jq.

set -euo pipefail
cd "$(dirname "$0")/../.."

REGION=$(terraform -chdir=terraform output -raw aws_region)
REPOS=$(terraform -chdir=terraform output -json ecr_repository_urls)
REGISTRY=$(echo "$REPOS" | jq -r 'to_entries[0].value | split("/")[0]')
TAG="${IMAGE_TAG:-latest}"

echo "==> Logging in to $REGISTRY"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# service:directory pairs, matching locals.services in Terraform.
# Plain strings rather than an associative array, since macOS ships bash 3.2
# and `declare -A` needs bash 4+.
SERVICES="
order-service:services/order-service
payment-service:services/payment-service
inventory-service:services/inventory-service
notification-service:services/notification-service
data-pipeline:data-pipeline
ai-agent-service:services/ai-agent-service
agent-ui:services/agent-ui
"

for entry in $SERVICES; do
  svc="${entry%%:*}"
  dir="${entry##*:}"
  repo=$(echo "$REPOS" | jq -r --arg s "$svc" '.[$s]')

  if [ "$repo" = "null" ] || [ -z "$repo" ]; then
    echo "!! no ECR repository for $svc — has terraform apply created it yet?" >&2
    exit 1
  fi

  echo "==> $svc  ($dir)"
  docker build --platform linux/arm64 -t "$repo:$TAG" "$dir"
  docker push "$repo:$TAG"
done

echo "Done. Pushed tag: $TAG"