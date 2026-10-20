locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Single source of truth for what runs on ECS. Task definitions, services,
  # ECR repositories, log groups and IAM roles all iterate over this map
  # rather than repeating seven near-identical blocks.
  #
  #   build_dir   - path in the repo, used by the image push script
  #   port        - container port (also the Service Connect alias port)
  #   db          - database this service connects to, or null
  #   db_env_var  - which env var carries that connection string
  #   needs_kafka - attach the MSK IAM policy
  #   needs_anthropic - inject the Anthropic API key secret
  #   needs_s3    - attach the data lake policy
  #   alb_paths   - path patterns routed to it, or [] for internal-only
  services = {
    order-service = {
      needs_anthropic = false
      build_dir       = "services/order-service"
      port            = 8000
      cpu             = 256
      memory          = 512
      db              = "orders"
      db_env_var      = "DATABASE_URL"
      needs_kafka     = true
      needs_s3        = false
      alb_paths       = ["/orders", "/orders/*", "/docs", "/openapi.json"]
    }
    payment-service = {
      needs_anthropic = false
      build_dir       = "services/payment-service"
      port            = 8000
      cpu             = 256
      memory          = 512
      db              = "payments"
      db_env_var      = "DATABASE_URL"
      needs_kafka     = true
      needs_s3        = false
      alb_paths       = []
    }
    inventory-service = {
      needs_anthropic = false
      build_dir       = "services/inventory-service"
      port            = 8000
      cpu             = 256
      memory          = 512
      db              = "inventory"
      db_env_var      = "DATABASE_URL"
      needs_kafka     = true
      needs_s3        = false
      alb_paths       = []
    }
    notification-service = {
      needs_anthropic = false
      build_dir       = "services/notification-service"
      port            = 8000
      cpu             = 256
      memory          = 512
      db              = null
      db_env_var      = null
      needs_kafka     = true
      needs_s3        = false
      alb_paths       = []
    }
    data-pipeline = {
      needs_anthropic = false
      build_dir       = "data-pipeline"
      port            = 8000
      cpu             = 256
      memory          = 512
      db              = null
      db_env_var      = null
      needs_kafka     = true
      needs_s3        = true
      alb_paths       = []
    }
    ai-agent-service = {
      needs_anthropic = true
      build_dir       = "services/ai-agent-service"
      port            = 8000
      # Larger than the others: the image carries torch and the embedding
      # model, and RAG queries run inference in-process.
      cpu         = 512
      memory      = 1024
      db          = "agent_knowledge"
      db_env_var  = "AGENT_DB_URL"
      needs_kafka = false
      needs_s3    = false
      alb_paths   = []
    }
    agent-ui = {
      needs_anthropic = false
      build_dir       = "services/agent-ui"
      port            = 8501
      cpu             = 256
      memory          = 512
      db              = null
      db_env_var      = null
      needs_kafka     = false
      needs_s3        = false
      alb_paths       = ["/*"] # catch-all: the ALB's default target
    }
  }

  # Databases created by scripts/bootstrap_databases.sh, derived from the
  # map above so the two can't drift apart.
  service_databases = toset([for s in local.services : s.db if s.db != null])

  kafka_topics = [
    "order-created",
    "payment-processed",
    "inventory-reserved",
    "order-confirmed",
    "order-cancelled",
  ]
}