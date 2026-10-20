#!/usr/bin/env python3
"""Print current on-demand AWS prices for the resources this stack uses.

Reads the AWS Price List API through the aws CLI (no boto3 needed), so the
figures come from AWS itself, not from a third-party site. Read-only: it
calls pricing:GetProducts and nothing else.

    python3 terraform/scripts/price_check.py [region]     # default eu-south-2
"""

import json
import subprocess
import sys

REGION = sys.argv[1] if len(sys.argv) > 1 else "eu-south-2"

# (label, service code, extra TERM_MATCH filters, words the description must contain[, words to allow from SKIP])
QUERIES = [
    ("Fargate vCPU (Linux)", "AmazonECS", {}, ["Fargate", "vCPU"]),
    ("Fargate memory (Linux)", "AmazonECS", {}, ["Fargate", "Memory"]),
    ("Fargate vCPU (Linux/ARM, what this stack uses)", "AmazonECS", {}, ["Fargate", "vCPU", "ARM"], ["ARM"]),
    ("Fargate memory (Linux/ARM, what this stack uses)", "AmazonECS", {}, ["Fargate", "Memory", "ARM"], ["ARM"]),
    ("MSK broker kafka.t3.small", "AmazonMSK", {}, ["t3.small"]),
    ("MSK storage", "AmazonMSK", {}, ["storage"]),
    ("MSK Serverless (cluster, partition, data)", "AmazonMSK", {}, ["serverless"]),
    ("RDS PostgreSQL db.t3.micro", "AmazonRDS",
     {"instanceType": "db.t3.micro", "databaseEngine": "PostgreSQL", "deploymentOption": "Single-AZ"}, []),
    ("RDS gp2/gp3 storage", "AmazonRDS",
     {"productFamily": "Database Storage", "databaseEngine": "PostgreSQL", "deploymentOption": "Single-AZ"}, []),
    ("NAT gateway", "AmazonEC2", {"productFamily": "NAT Gateway"}, []),
    ("Application Load Balancer", "AWSELB", {"productFamily": "Load Balancer-Application"}, []),
    ("Secrets Manager", "AWSSecretsManager", {}, ["secret"]),
    ("Public IPv4 address (NAT, ALB)", "AmazonVPC", {}, ["IPv4"]),
    ("ECR storage", "AmazonECR", {}, ["storage"]),
]

SKIP = ("Spot", "Windows", "ARM", "Arm", "Graviton", "Ephemeral", "Outposts", "Reserved")


def products(service, extra):
    filters = [f"Type=TERM_MATCH,Field=regionCode,Value={REGION}"]
    filters += [f"Type=TERM_MATCH,Field={k},Value={v}" for k, v in extra.items()]
    out = subprocess.run(
        ["aws", "pricing", "get-products", "--region", "us-east-1",
         "--service-code", service, "--filters", *filters, "--output", "json"],
        check=True, capture_output=True, text=True).stdout
    for raw in json.loads(out)["PriceList"]:
        yield json.loads(raw)


def on_demand(product):
    for term in product.get("terms", {}).get("OnDemand", {}).values():
        for dim in term["priceDimensions"].values():
            yield dim["description"], dim["unit"], float(dim["pricePerUnit"].get("USD", 0))


def main():
    print(f"On-demand prices in {REGION} (USD), from the AWS Price List API\n")
    for label, service, extra, words, *allow in QUERIES:
        allow = allow[0] if allow else []
        skip = [w for w in SKIP if w not in allow]
        print(f"== {label}")
        seen = set()
        for product in products(service, extra):
            for desc, unit, price in on_demand(product):
                if price == 0 or any(s in desc for s in skip):
                    continue
                if words and not all(w.lower() in desc.lower() for w in words):
                    continue
                if (desc, unit) in seen:
                    continue
                seen.add((desc, unit))
                print(f"   {price:>10.5f} per {unit:<10} {desc[:110]}")
        if not seen:
            print("   (nothing matched; the filter may need adjusting)")
        print()


if __name__ == "__main__":
    main()