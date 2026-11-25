# NiveshCouncil developer commands. `make help` lists them.
SHELL := /bin/bash
COMPOSE ?= docker compose
WEB := apps/web

-include .env
POSTGRES_USER ?= nivesh
POSTGRES_PASSWORD ?= nivesh
POSTGRES_DB ?= nivesh
DATABASE_URL ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:5432/$(POSTGRES_DB)
TEST_DATABASE_URL ?= $(DATABASE_URL)

.DEFAULT_GOAL := help
.PHONY: help deps dev up down logs db-up migrate test test-py test-web lint fmt \
        ingest guidance screen council nightly

help: ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(firstword $(MAKEFILE_LIST)) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

.venv: pyproject.toml uv.lock
	uv sync --frozen
	@touch .venv

$(WEB)/node_modules: $(WEB)/package-lock.json
	npm --prefix $(WEB) ci
	@touch $(WEB)/node_modules

deps: .venv $(WEB)/node_modules ## Install Python and web dependencies on the host

dev: .env ## Start web :3000, api :8000, worker and db (foreground)
	$(COMPOSE) up --build

up: .env ## Start the stack in the background and wait until it is healthy
	$(COMPOSE) up --build --detach --wait

down: ## Stop the stack (the database volume is kept)
	$(COMPOSE) down

logs: ## Follow logs from every service
	$(COMPOSE) logs --follow

db-up: .env
	$(COMPOSE) up --detach --wait db

migrate: db-up .venv ## Apply database migrations from the host
	DATABASE_URL='$(DATABASE_URL)' uv run python -m services.migrate

test: test-py test-web ## Run pytest (with Postgres) and vitest

test-py: db-up .venv
	TEST_DATABASE_URL='$(TEST_DATABASE_URL)' uv run pytest

test-web: $(WEB)/node_modules
	npm --prefix $(WEB) test

lint: .venv $(WEB)/node_modules ## Run ruff, mypy, eslint and tsc
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	npm --prefix $(WEB) run lint
	npm --prefix $(WEB) run typecheck

fmt: .venv ## Auto-fix lint and formatting
	uv run ruff check --fix .
	uv run ruff format .

ingest: .venv ## Load data: make ingest ARGS="security-master --nse ... " (ARGS=--help lists commands)
	uv run python -m services.ingest $(if $(ARGS),$(ARGS),--help)

guidance: .venv ## Guidance extraction and review: make guidance ARGS="extract --dry-run"
	uv run python -m services.mgmt_guidance $(if $(ARGS),$(ARGS),--help)

screen: ## Recompute today's factor scores (Phase 2)
	@echo "make screen: not implemented yet (Phase 2, docs/SPEC.md section 11)"; exit 1

council: ## One council run: make council ISIN=INE000X01010 (Phase 3)
	@echo "make council ISIN=$(ISIN): not implemented yet (Phase 3, docs/SPEC.md section 11)"; exit 1

nightly: ## Full nightly pipeline on the Batches API (Phase 6)
	@echo "make nightly: not implemented yet (Phase 6, docs/SPEC.md section 11)"; exit 1
