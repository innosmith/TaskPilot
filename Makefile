# TaskPilot Docker Management
# Verwendung: make <target>

COMPOSE_SHARED = docker compose -f docker/docker-compose.yml
COMPOSE_INT    = $(COMPOSE_SHARED) -f docker/docker-compose.integration.yml
COMPOSE_PROD   = docker compose --env-file .env.prod -f docker/docker-compose.prod.yml

.PHONY: help dev int prod build down logs-int logs-prod status health vendor sandbox

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
	@echo ""
	@echo "Shared Infra laeuft (Postgres :5435, LiteLLM :4000)."
	@echo ""
	@echo "Backend starten:"
	@echo "  cd $(PWD) && source .venv/bin/activate"
	@echo "  PYTHONPATH=src/backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src/backend"
	@echo ""
	@echo "Frontend starten:"
	@echo "  cd src/frontend && npm run dev"

# ── Integration ──────────────────────────────────────────

int: infra ## Integration starten (Full Docker)
	$(COMPOSE_INT) up -d --build

int-down: ## Integration stoppen (Shared Infra bleibt)
	$(COMPOSE_INT) down --remove-orphans

# ── Produktion ───────────────────────────────────────────

prod: ## Produktion starten (Standalone, eigene DB)
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
	-$(COMPOSE_SHARED) down 2>/dev/null
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
	@echo "=== LiteLLM ==="
	@curl -sf http://localhost:4000/health 2>/dev/null || echo "  nicht erreichbar"
	@echo ""
	@echo "=== Ollama ==="
	@curl -sf http://localhost:11434/api/tags 2>/dev/null | head -c 100 || echo "  nicht erreichbar"
	@echo ""

# ── DB-Migration (Schema auf Int/Prod anwenden) ──────────

migrate-int: ## Schema auf Integration-DB anwenden
	docker exec -i taskpilot-postgres psql -U taskpilot -d taskpilot_int < db/schema.sql

migrate-prod: ## Schema auf Produktion-DB anwenden
	docker exec -i taskpilot-postgres-prod psql -U taskpilot -d taskpilot_prod < db/schema.sql
