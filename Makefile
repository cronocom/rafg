# ═══════════════════════════════════════════════════════════
# RAGF Makefile - Automation for MVA
# ═══════════════════════════════════════════════════════════

.PHONY: help init build up down logs shell test smoke benchmark clean seed

help: ## Mostrar este mensaje de ayuda
	@echo "════════════════════════════════════════════════════════"
	@echo "  RAGF - Reflexio Agentic Governance Framework"
	@echo "════════════════════════════════════════════════════════"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

init: ## Inicializar proyecto (primera vez)
	@echo "🔧 Inicializando RAGF..."
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@echo "⚠️  EDITA .env con tu ANTHROPIC_API_KEY antes de continuar"
	@echo "✅ Ejecuta 'make build' después de configurar .env"

build: ## Construir contenedores Docker
	@echo "🏗️  Construyendo imágenes..."
	docker-compose build --no-cache

up: ## Levantar todos los servicios
	@echo "🚀 Levantando servicios..."
	docker-compose up -d
	@echo "⏳ Esperando health checks..."
	@sleep 10
	@make status

down: ## Detener todos los servicios
	@echo "🛑 Deteniendo servicios..."
	docker-compose down

logs: ## Ver logs de todos los servicios
	docker-compose logs -f

logs-api: ## Ver logs solo de FastAPI
	docker-compose logs -f api

status: ## Verificar estado de servicios
	@echo "📊 Estado de servicios:"
	@docker-compose ps

shell: ## Abrir shell en contenedor de API
	docker-compose exec api /bin/bash

shell-neo4j: ## Abrir Cypher shell
	docker-compose exec neo4j cypher-shell -u neo4j -p ragf_secure_2026

seed: ## Cargar ontologías en Neo4j
	@echo "🌱 Cargando ontologías..."
	@docker-compose exec -T neo4j cypher-shell -u neo4j -p ragf_secure_2026 < gateway/ontologies/schema.cypher
	@docker-compose exec -T neo4j cypher-shell -u neo4j -p ragf_secure_2026 < gateway/ontologies/aviation_seed.cypher
	@echo "✅ Ontologías cargadas"

test: ## Ejecutar tests unitarios
	docker-compose exec api pytest tests/unit -v

smoke: ## Ejecutar smoke tests (3 escenarios críticos)
	@echo "💨 Ejecutando smoke tests..."
	docker-compose exec api pytest tests/smoke_test.py -v

benchmark: ## Ejecutar suite completa de benchmarks
	@echo "📊 Ejecutando benchmarks (esto tomará ~5 minutos)..."
	docker-compose exec api pytest tests/benchmark/benchmark_suite.py -v

clean: ## Limpiar contenedores y volúmenes
	@echo "🧹 Limpiando..."
	docker-compose down -v
	docker system prune -f

restart: down up ## Reiniciar todos los servicios

health: ## Verificar salud de todos los endpoints
	@echo "🏥 Verificando salud del sistema..."
	@curl -s http://localhost:8001/health | python3 -m json.tool || echo "❌ API no responde"
	@curl -s http://localhost:7475 > /dev/null && echo "✅ Neo4j UI: http://localhost:7475" || echo "❌ Neo4j no responde"

watch: ## Ver métricas en tiempo real
	watch -n 2 'docker stats --no-stream'

.PHONY: help analyze-escalations install test

PYTHON := python3
VENV := venv

help:
	@echo "RAGF Development Commands"
	@echo "========================="
	@echo "make install            - Install dependencies"
	@echo "make analyze-escalations - Generate escalation metrics"
	@echo "make test              - Run test suite"
	@echo "make clean             - Clean generated files"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

analyze-escalations:
	@echo "Generating escalation metrics for AIES camera-ready..."
	$(PYTHON) scripts/analyze_escalations.py

test:
	$(PYTHON) -m pytest tests/ -v

clean:
	rm -rf results/escalation_analysis/*
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
