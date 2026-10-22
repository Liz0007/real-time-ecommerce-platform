# One public entry point. agent-ui is the default target (the demo UI);
# order-service is reachable on its API paths so orders can be created
# from outside.
#
# HTTP only: HTTPS would need an ACM certificate and therefore a domain,
# which this demo doesn't have. Noted as a production gap rather than
# silently omitted.

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [for s in aws_subnet.public : s.id]

  tags = { Name = "${local.name_prefix}-alb" }
}

resource "aws_lb_target_group" "services" {
  for_each = { for k, v in local.services : k => v if length(v.alb_paths) > 0 }

  name        = "${local.name_prefix}-${substr(each.key, 0, 20)}"
  port        = each.value.port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # required for Fargate's awsvpc networking

  health_check {
    # Streamlit doesn't serve /health; it has its own probe endpoint.
    path                = each.key == "agent-ui" ? "/_stcore/health" : "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["agent-ui"].arn
  }
}

# Path rules for everything that isn't the default target.
resource "aws_lb_listener_rule" "services" {
  for_each = {
    for k, v in local.services : k => v
    if length(v.alb_paths) > 0 && k != "agent-ui"
  }

  listener_arn = aws_lb_listener.http.arn
  priority     = 100 + index(keys(local.services), each.key)

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services[each.key].arn
  }

  condition {
    path_pattern { values = each.value.alb_paths }
  }
}
