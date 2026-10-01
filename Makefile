.PHONY: help dev test lint clean docker-up docker-down

help:
	@echo "TradeForge Monorepo Commands:"
	@echo "  make dev          Start local development services"
	@echo "  make test         Run all unit and integration tests"
	@echo "  make lint         Run linters (ruff, eslint)"
	@echo "  make docker-up    Start TimescaleDB, Redis, and containers via docker-compose"
	@echo "  make docker-down  Stop all docker containers"
	@echo "  make clean        Remove cache files and build artifacts"

dev:
	@echo "Starting development environment..."
	docker compose up -d timescaledb redis
	@echo "Starting FastAPI in background and Next.js frontend..."

test:
	@echo "Running Python test suite..."
	python3 -m pytest services/ tests/ -v

lint:
	@echo "Running Python ruff linter..."
	python3 -m ruff check services/ packages/ tests/ || true
	@echo "Running web linter..."
	cd apps/web && npm run lint || true

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf apps/web/.next apps/web/node_modules
