# TaskPilot Docker Management
# Verwendung: make <target>

COMPOSE_SHARED = docker compose -f docker/docker-compose.yml
COMPOSE_INT    = $(COMPOSE_SHARED) -f docker/docker-compose.integration.yml --profile clamav
COMPOSE_PROD   = docker compose --env-file .env.prod -f docker/docker-compose.prod.yml

.PHONY: help dev int prod build down logs-int logs-prod status health vendor sandbox test test-smoke test-contract test-e2e test-explore test-all schema-int

help: ## Zeigt diese Hilfe
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Shared Infra ──────────────────────────────────────────

infra: ## Shared Infra starten (Postgres + LiteLLM)
	$(COMPOSE_SHARED) up -d

infra-down: ## Shared Infra stoppen
	$(COMPOSE_SHARED) down

# ── Development ───────────────────────────────────────────

dev: infra ## Dev-Infra starten (Backend+Frontend laufen bare-metal)
	$(COMPOSE_SHARED) --profile clamav up -d clamav
	@echo ""
	@echo "Shared Infra laeuft (Postgres :5435, LiteLLM :4000, ClamAV :3310)."
	@echo ""
	@echo "Backend starten:"
	@echo "  cd $(PWD) && source .venv/bin/activate"
	@echo "  PYTHONPATH=src/backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src/backend"
	@echo ""
	@echo "Frontend starten:"
	@echo "  cd src/frontend && npm run dev"

# ── Integration ──────────────────────────────────────────

int: infra ## Integration starten (Full Docker + ClamAV)
	$(COMPOSE_INT) up -d --build

int-down: ## Integration stoppen (Shared Infra bleibt)
	$(COMPOSE_INT) down --remove-orphans

# ── Produktion ───────────────────────────────────────────

prod: ## Produktion starten (Standalone, eigene DB + ClamAV)
	$(COMPOSE_PROD) up -d --build

prod-down: ## Produktion stoppen
	$(COMPOSE_PROD) down

# ── Build ─────────────────────────────────────────────────

vendor: ## Vendor-Verzeichnis vorbereiten (private Packages)
	./docker/build.sh

sandbox: ## Sandbox-Image bauen
	docker build -t taskpilot-sandbox:latest docker/sandbox/

build: vendor ## Alle Images bauen (ohne Start)
	$(COMPOSE_INT) build
	$(COMPOSE_PROD) build
	@echo "Alle Images gebaut."

# ── Alles stoppen ─────────────────────────────────────────

down: ## Alle Umgebungen stoppen
	-$(COMPOSE_PROD) down 2>/dev/null
	-$(COMPOSE_INT) down 2>/dev/null
	-$(COMPOSE_SHARED) --profile clamav down 2>/dev/null
	@echo "Alle Container gestoppt."

# ── Logs ──────────────────────────────────────────────────

logs-int: ## Integration Logs (follow)
	$(COMPOSE_INT) logs -f

logs-prod: ## Produktion Logs (follow)
	$(COMPOSE_PROD) logs -f

logs-backend-int: ## Nur Backend-Int Logs
	docker logs -f taskpilot-backend-int

logs-backend-prod: ## Nur Backend-Prod Logs
	docker logs -f taskpilot-backend-prod

# ── Status ────────────────────────────────────────────────

status: ## Status aller TaskPilot-Container
	@docker ps --filter "name=taskpilot" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

health: ## Health-Checks ausfuehren
	@echo "=== Dev Backend ==="
	@curl -sf http://localhost:8000/api/health 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== Integration Backend ==="
	@curl -sf http://localhost:8100/api/health 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== Produktion Backend ==="
	@curl -sf http://localhost:8200/api/health 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== ClamAV ==="
	@echo "PING" | nc -w 2 localhost 3310 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== LiteLLM ==="
	@curl -sf http://localhost:4000/health 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== Ollama ==="
	@curl -sf http://localhost:11434/api/tags 2>/dev/null | head -c 100 || echo "  nicht erreichbar"
	@echo ""

# ── Tests ─────────────────────────────────────────────────

test: ## Backend Unit-Tests (pytest, Schicht 1)
	cd src/backend && ../../.venv/bin/python -m pytest tests/ -v --ignore=tests/e2e

test-smoke: ## Smoke-Tests gegen Integration (Schicht 2)
	.venv/bin/python -m pytest tests/smoke/ -v

test-contract: ## OpenAPI-Contract-Guard (gegen laufendes Backend, Default: Dev)
	.venv/bin/python -m pytest tests/contract/ -v

test-e2e: ## Playwright E2E-Tests gegen Integration (Schicht 3)
	cd tests/e2e && ../../.venv/bin/python -m pytest . -v

test-explore: ## AI-Explorations-Audit mit browser-use (Schicht 4)
	.venv/bin/python tests/ai-audit/run_audit.py

test-all: test test-smoke ## Alle automatisierten Tests (Schicht 1-2 + Contract gegen INT)
	TP_SMOKE_BACKEND_URL=$${TP_SMOKE_BACKEND_URL:-http://localhost:8100} \
	.venv/bin/python -m pytest tests/contract/ -v
	@echo "Alle Tests bestanden."

# ── DB-Schema & Migration ────────────────────────────────

schema-int: ## Schema direkt auf taskpilot_int anwenden (frische DB)
	docker exec -i taskpilot-postgres psql -U taskpilot -d taskpilot_int < db/schema.sql
	@echo "Schema auf taskpilot_int angewendet."

migrate-dev: ## Alembic-Migration auf Dev-DB ausfuehren
	cd src/backend && PYTHONPATH=. ../../.venv/bin/alembic upgrade head

migrate-int: ## Alembic-Migration auf Integration-DB ausfuehren
	docker exec taskpilot-backend-int alembic upgrade head

migrate-prod: ## Alembic-Migration auf Produktion-DB ausfuehren
	docker exec taskpilot-backend-prod alembic upgrade head
