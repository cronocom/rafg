-- ═══════════════════════════════════════════════════════════
-- RAGF Audit Ledger Schema (TimescaleDB) - MVA SIMPLIFIED
-- ═══════════════════════════════════════════════════════════

-- Habilitar extensión TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Tabla principal de auditoría
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL,
    trace_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Decisión
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    
    -- Contexto del agente
    agent_id TEXT,
    amm_level INTEGER NOT NULL,
    
    -- Acción original
    action_verb TEXT NOT NULL,
    action_resource TEXT NOT NULL,
    action_domain TEXT NOT NULL,
    action_parameters JSONB,
    
    -- Veredicto semántico
    semantic_ontology_match BOOLEAN NOT NULL,
    semantic_amm_authorized BOOLEAN NOT NULL,
    semantic_coverage FLOAT NOT NULL,
    
    -- Resultados de validadores
    validator_results JSONB NOT NULL,
    
    -- Métricas de performance
    total_latency_ms FLOAT NOT NULL,
    is_certifiable BOOLEAN NOT NULL,
    
    -- Firma digital
    signature TEXT,
    
    -- Metadata adicional
    metadata JSONB,
    
    PRIMARY KEY (timestamp, id)
);

-- Índices básicos
CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_log (trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_log (decision);
CREATE INDEX IF NOT EXISTS idx_audit_action_verb ON audit_log (action_verb);

-- Vista simple para KPIs del dashboard
CREATE OR REPLACE VIEW dashboard_kpis AS
SELECT
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as actions_last_24h,
    AVG(total_latency_ms) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as avg_latency_24h,
    COUNT(*) FILTER (WHERE decision = 'DENY' AND timestamp > NOW() - INTERVAL '24 hours')::FLOAT /
        NULLIF(COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours'), 0) * 100 as deny_rate_pct,
    0 as open_incidents,
    COUNT(*) FILTER (WHERE is_certifiable = TRUE AND timestamp > NOW() - INTERVAL '24 hours')::FLOAT /
        NULLIF(COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours'), 0) * 100 as certifiable_rate_pct
FROM audit_log;
