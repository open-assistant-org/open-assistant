.PHONY: help install dev-install test lint format clean build build-job-runner run migrate

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install production dependencies
	uv sync

dev-install: ## Install development dependencies
	uv sync --extra dev

test: ## Run tests
	uv run pytest

lint: ## Run linter
	uv run ruff check src tests

format: ## Format code
	uv run black src tests
	uv run ruff check --fix src tests

clean: ## Clean build artifacts and caches
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache .coverage htmlcov

build: ## Build main application Docker image (also used for cron jobs)
	docker build -t personal-assistant:latest .

run: ## Run the application locally
	uv run python -m src.main

migrate: ## Run database migrations
	uv run python -m src.core.database init

docker-up: ## Start services with docker-compose
	docker-compose up -d

docker-down: ## Stop services with docker-compose
	docker-compose down

docker-logs: ## Show docker-compose logs
	docker-compose logs -f

docker-rebuild: build-all docker-down docker-up ## Rebuild images and restart services
