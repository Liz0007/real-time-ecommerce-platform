.PHONY: up down build logs logs-kafka topics restart clean test lint

up:
	docker compose up -d
	@echo "order-service available at http://localhost:8000/health"

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f order-service

logs-kafka:
	docker compose logs -f kafka

topics:
	docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

restart:
	docker compose restart order-service

clean:
	docker compose down -v
	@echo "Stack stopped and volumes removed"

test:
	cd services/order-service && pip install -e ".[dev]" && pytest

lint:
	cd services/order-service && ruff check app