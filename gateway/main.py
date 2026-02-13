"""
═══════════════════════════════════════════════════════════
RAGF FastAPI Gateway
Punto de entrada HTTP para el Validation Gate
═══════════════════════════════════════════════════════════
"""

import os
import uuid
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from shared.models import ActionRequest, ValidationResponse, AMMLevel
from gateway.neo4j_client import Neo4jClient
from gateway.intent_normalizer import IntentNormalizer
from gateway.decision_engine import DecisionEngine
from audit.ledger import AuditLedger
from audit.metrics import AuditMetrics

# Configurar structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN DESDE ENVIRONMENT
# ═══════════════════════════════════════════════════════════

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "ragf_secure_2026")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "ragf_audit")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ragf")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "audit_secure_2026")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "redis_secure_2026")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.warning("ANTHROPIC_API_KEY not set - Intent Normalizer will fail")

VALIDATION_TIMEOUT_MS = float(os.getenv("VALIDATION_TIMEOUT_MS", "200"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT = os.getenv("ENVIRONMENT", "mva")

# ═══════════════════════════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════════════════════════

class AppState:
    """Global application state"""
    neo4j_client: Neo4jClient
    redis_client: redis.Redis
    intent_normalizer: IntentNormalizer
    decision_engine: DecisionEngine
    audit_ledger: AuditLedger
    audit_metrics: AuditMetrics


app_state = AppState()


# ═══════════════════════════════════════════════════════════
# LIFECYCLE MANAGEMENT
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    
    # STARTUP
    logger.info("ragf_starting", environment=ENVIRONMENT)
    
    # Conectar Neo4j
    app_state.neo4j_client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await app_state.neo4j_client.connect()
    
    # Conectar Redis
    app_state.redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    await app_state.redis_client.ping()
    logger.info("redis_connected")
    
    # Conectar Audit Ledger
    app_state.audit_ledger = AuditLedger(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    await app_state.audit_ledger.connect()
    
    # Inicializar componentes
    app_state.intent_normalizer = IntentNormalizer(
        anthropic_api_key=ANTHROPIC_API_KEY or "",
        redis_client=app_state.redis_client,
        timeout_ms=100.0
    )
    
    app_state.decision_engine = DecisionEngine(
        neo4j_client=app_state.neo4j_client,
        validation_timeout_ms=VALIDATION_TIMEOUT_MS
    )
    
    app_state.audit_metrics = AuditMetrics(app_state.audit_ledger.pool)
    
    logger.info("ragf_started")
    
    yield
    
    # SHUTDOWN
    logger.info("ragf_shutting_down")
    
    await app_state.neo4j_client.close()
    await app_state.redis_client.close()
    await app_state.audit_ledger.close()
    
    logger.info("ragf_stopped")


# ═══════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title="RAGF - Reflexio Agentic Governance Framework",
    description="Deterministic governance layer for LLMs in regulated systems",
    version="1.0.0",
    lifespan=lifespan
)

# CORS (para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": ENVIRONMENT,
        "version": "1.0.0"
    }


@app.post("/v1/validate", response_model=ValidationResponse)
async def validate_action(
    request: ActionRequest,
    x_trace_id: str | None = Header(None)
):
    """
    ENDPOINT PRINCIPAL: Valida una acción del agente.
    
    Flujo completo:
    1. Intent Normalization (Claude)
    2. Semantic Validation (Neo4j)
    3. Independent Validators (Safety)
    4. Audit Log (TimescaleDB)
    
    Returns:
        ValidationResponse con veredicto final
    """
    trace_id = x_trace_id or str(uuid.uuid4())
    
    logger.info(
        "validation_request_received",
        trace_id=trace_id,
        amm_level=int(request.agent_amm_level),
        prompt=request.prompt[:100]
    )
    
    try:
        # ═══════════════════════════════════════════════════════
        # PASO 1: Intent Normalization
        # ═══════════════════════════════════════════════════════
        
        action, normalization_method = await app_state.intent_normalizer.normalize(
            prompt=request.prompt,
            domain="aviation"  # Hardcoded para MVA
        )
        
        logger.info(
            "intent_normalized",
            trace_id=trace_id,
            verb=action.verb,
            method=normalization_method,
            confidence=action.confidence
        )
        
        # ═══════════════════════════════════════════════════════
        # PASO 2: Decision Engine (Semantic + Validators)
        # ═══════════════════════════════════════════════════════
        
        verdict = await app_state.decision_engine.evaluate(
            action=action,
            amm_level=request.agent_amm_level,
            trace_id=trace_id,
            agent_id=request.agent_id
        )
        
        # ═══════════════════════════════════════════════════════
        # PASO 3: Audit Log (CRÍTICO)
        # ═══════════════════════════════════════════════════════
        
        await app_state.audit_ledger.write(verdict)
        
        # ═══════════════════════════════════════════════════════
        # PASO 4: Response
        # ═══════════════════════════════════════════════════════
        
        response = ValidationResponse(
            verdict=verdict,
            trace_id=trace_id,
            is_certifiable=verdict.is_certifiable
        )
        
        logger.info(
            "validation_request_completed",
            trace_id=trace_id,
            decision=verdict.decision,
            latency_ms=verdict.total_latency_ms,
            is_certifiable=verdict.is_certifiable
        )
        
        return response
    
    except Exception as e:
        logger.error(
            "validation_request_failed",
            trace_id=trace_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/metrics/dashboard")
async def get_dashboard_metrics():
    """
    Obtiene KPIs principales para el dashboard.
    
    Returns:
        Dict con métricas clave
    """
    try:
        kpis = await app_state.audit_metrics.get_dashboard_kpis()
        return kpis
    except Exception as e:
        logger.error("metrics_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/metrics/mttv")
async def get_mttv(hours: int = 24):
    """
    Mean Time To Validation (p95).
    
    Args:
        hours: Ventana de tiempo (default: 24h)
    
    Returns:
        MTTV en milisegundos
    """
    try:
        mttv = await app_state.audit_metrics.get_mttv(hours)
        return {"mttv_ms": mttv, "hours": hours}
    except Exception as e:
        logger.error("mttv_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/metrics/pass-rate")
async def get_pass_rate(amm_level: int | None = None):
    """
    Validation Pass Rate (últimas 24h).
    
    Args:
        amm_level: Filtrar por nivel AMM (opcional)
    
    Returns:
        Pass rate como porcentaje
    """
    try:
        pass_rate = await app_state.audit_metrics.get_validation_pass_rate(amm_level)
        return {"pass_rate_pct": pass_rate, "amm_level": amm_level}
    except Exception as e:
        logger.error("pass_rate_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
