# Networking layer: VPC, public + private subnets across two AZs, and a
# single NAT gateway for private-subnet egress.
#
# Public subnets hold only the ALB. Everything else — ECS tasks, RDS, MSK
# — sits in private subnets with no inbound route from the internet.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # MSK and RDS endpoints are resolved by name

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-igw" }
}

resource "aws_subnet" "public" {
  for_each = toset(var.availability_zones)

  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, index(var.availability_zones, each.value))
  map_public_ip_on_launch = true

  tags = { Name = "${local.name_prefix}-public-${each.value}" }
}

resource "aws_subnet" "private" {
  for_each = toset(var.availability_zones)

  # +10 keeps private CIDRs visually distinct from public ones
  # (10.0.0.x/10.0.1.x public, 10.0.10.x/10.0.11.x private).
  vpc_id            = aws_vpc.main.id
  availability_zone = each.value
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, index(var.availability_zones, each.value) + 10)

  tags = { Name = "${local.name_prefix}-private-${each.value}" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat-eip" }
}

# One NAT gateway, not one per AZ: a deliberate cost trade-off (~$35/mo
# each). It is a single point of failure for private-subnet egress, which
# would be worth fixing before this carried real traffic.
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = values(aws_subnet.public)[0].id
  tags          = { Name = "${local.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-public-rt" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}
