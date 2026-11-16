.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help sync db-up db-down db-logs migrate migrations-check run check lint format test verify

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install locked runtime and development dependencies
	$(UV) sync --locked

db-up: ## Start PostgreSQL and wait until ready
	docker compose up -d --wait db

db-down: ## Stop services, preserving database data
	docker compose down

db-logs: ## Follow PostgreSQL logs
	docker compose logs -f db

migrate: ## Apply database migrations
	$(UV) run python manage.py migrate

migrations-check: ## Check for missing model migrations
	$(UV) run python manage.py makemigrations --check --dry-run

run: ## Run the local Django development server
	$(UV) run python manage.py runserver

check: ## Run Django system checks
	$(UV) run python manage.py check

lint: ## Run Ruff, formatting checks, and mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy .

format: ## Apply Ruff lint fixes and formatting
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Run pytest (database tests use PostgreSQL)
	$(UV) run pytest

verify: lint check migrations-check test ## Run all project checks
