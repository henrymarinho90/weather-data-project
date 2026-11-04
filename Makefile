.DEFAULT_GOAL := help
.PHONY: help init up down ps logs seed superset-setup creds dbt-build backup backup-verify restore lint test

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

init: ## Generate .env files with random secrets
	./scripts/init_env.sh

up: ## Build and start the stack
	docker compose up -d --build

down: ## Stop the stack
	docker compose down

ps: ## Show container status
	docker compose ps

logs: ## Follow logs
	docker compose logs -f --tail=100

seed: ## Seed 30 days of synthetic weather data
	docker exec airflow_container python /opt/airflow/api-request/seed_test_data.py --days 30

superset-setup: ## Create Superset datasets and dashboards
	docker exec superset_app python /app/docker/superset_setup.py

creds: ## Show generated credentials
	./scripts/show_credentials.sh

dbt-build: ## Run dbt build
	docker compose run --rm dbt build

backup: ## Back up all databases now (into ./backups)
	docker exec db_backup /opt/backup/backup.sh once

backup-verify: ## Restore the newest backup into a scratch DB and compare row counts
	docker exec db_backup /opt/backup/verify.sh

restore: ## Restore a database: make restore RUN=backups/<timestamp> [DB=name]
	./scripts/restore_backup.sh $(RUN) $(DB)

lint: ## Run ruff
	ruff check . && ruff format --check .

test: ## Run unit tests
	pytest -q
