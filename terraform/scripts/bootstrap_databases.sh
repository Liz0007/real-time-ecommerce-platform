#!/usr/bin/env bash
# Creates the three databases RDS didn't create at launch, enables pgvector,
# and runs every service's migrations.
#
# RDS creates only one database (orders) when the instance is launched, and
# unlike the local Postgres containers there is no docker-entrypoint-initdb.d
# hook to run migration SQL. This script is the AWS equivalent of that hook.
#
# Run from the repo root, after `terraform apply`, with admin_ip_cidr set so
# your IP can reach the instance:
#
#     ./terraform/scripts/bootstrap_databases.sh
#
# Requires: psql, terraform, aws CLI.

set -euo pipefail

cd "$(dirname "$0")/../.." # repo root

HOST=$(terraform -chdir=terraform output -raw rds_address)
SECRET=$(terraform -chdir=terraform output -raw db_password_secret_name)
REGION=$(terraform -chdir=terraform output -raw aws_region 2>/dev/null || echo "eu-south-2")

PGPASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET" --region "$REGION" --query SecretString --output text)
export PGPASSWORD

psql_run() { psql -h "$HOST" -U postgres -d "$1" -v ON_ERROR_STOP=1 "${@:2}"; }

echo "==> Creating databases"
for db in payments inventory agent_knowledge; do
  # CREATE DATABASE has no IF NOT EXISTS; this makes reruns safe.
  if psql_run postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    echo "    $db already exists"
  else
    psql_run postgres -c "CREATE DATABASE $db"
    echo "    created $db"
  fi
done

echo "==> Running migrations"
for f in services/order-service/migrations/*.sql; do
  echo "    orders <- $(basename "$f")"; psql_run orders -f "$f" >/dev/null
done
for f in services/payment-service/migrations/*.sql; do
  echo "    payments <- $(basename "$f")"; psql_run payments -f "$f" >/dev/null
done
for f in services/inventory-service/migrations/*.sql; do
  echo "    inventory <- $(basename "$f")"; psql_run inventory -f "$f" >/dev/null
done

echo "==> Enabling pgvector in agent_knowledge"
psql_run agent_knowledge -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null

echo "==> Verifying"
for db in orders payments inventory agent_knowledge; do
  echo -n "    $db: "; psql_run "$db" -tAc "SELECT count(*) || ' tables' FROM information_schema.tables WHERE table_schema='public'"
done

echo "Done."
