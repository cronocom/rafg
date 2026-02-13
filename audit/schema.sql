-- ═══════════════════════════════════════════════════════════
-- RAGF Audit Ledger Schema (TimescaleDB)
-- Diseñado para inmutabilidad y compliance (EU AI Act, DO-178C)
-- ═══════════════════════════════════════════════════════════

-- Habilitar extensión TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Tabla principal de auditoría (hypertable para series temporales)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL,
    trace_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Decisión
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('ALLOW', 'DENY', 'ESCALATE')),
    reason TEXT NOT NULL,
    
    -- Contexto del agente
    agent_id VARCHAR(100),
    amm_level INTEGER NOT NULL CHECK (amm_level BETWEEN 1 AND 5),
    
    -- Acción original
    action_verb VARCHAR(50) NOT NULL,
    action_resource VARCHAR(100) NOT NULL,
    action_domain VARCHAR(50) NOT NULL,
    action_parameters JSONB,
    
    -- Veredicto semántico
    semantic_ontology_match BOOLEAN NOT NULL,
    semantic_amm_authorized BOOLEAN NOT NULL,
    semantic_coverage FLOAT NOT NULL CHECK (semantic_coverage BETWEEN 0 AND 1),
    
    -- Resultados de validadores
    validator_results JSONB NOT NULL,
    
    -- Métricas de performance
    total_latency_ms FLOAT NOT NULL CHECK (total_latency_ms >= 0),
    is_certifiable BOOLEAN NOT NULL,
    
    -- Firma digital (para inmutabilidad)
    signature VARCHAR(256),
    
    -- Metadata adicional
    metadata JSONB,
    
    PRIMARY KEY (timestamp, id)
);

-- Convertir a hypertable (particionado por timestamp)
SELECT create_hypertable('audit_log', 'timestamp', if_not_exists => TRUE);

-- Índices para queries comunes
CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit_log (trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_agent_id ON audit_log (agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_log (decision);
CREATE INDEX IF NOT EXISTS idx_audit_action_verb ON audit_log (action_verb);
CREATE INDEX IF NOT EXISTS idx_audit_domain ON audit_log (action_domain);
CREATE INDEX IF NOT EXISTS idx_audit_certifiable ON audit_log (is_certifiable);

-- Continuous aggregate para métricas (actualización cada hora)
CREATE MATERIALIZED VIEW IF NOT EXISTS audit_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    action_domain,
    decision,
    COUNT(*) as total_actions,
    AVG(total_latency_ms) as avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) as p95_latency_ms,
    SUM(CASE WHEN is_certifiable THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as certifiable_rate,
    SUM(CASE WHEN semantic_coverage = 1.0 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as perfect_coverage_rate
FROM audit_log
GROUP BY bucket, action_domain, decision
WITH NO DATA;

-- Refrescar automáticamente cada hora
SELECT add_continuous_aggregate_policy('audit_metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- Política de retención: mantener datos detallados por 90 días
SELECT add_retention_policy('audit_log', INTERVAL '90 days', if_not_exists => TRUE);

-- Tabla de incidentes semánticos (para el paper ACM)
CREATE TABLE IF NOT EXISTS semantic_incidents (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(100) NOT NULL REFERENCES audit_log(trace_id),
    incident_type VARCHAR(50) NOT NULL CHECK (incident_type IN (
        'SEMANTIC_DRIFT',
        'AMM_VIOLATION',
        'CONSTRAINT_VIOLATION',
        'VALIDATOR_TIMEOUT'
    )),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    description TEXT NOT NULL,
    resolution_status VARCHAR(20) DEFAULT 'OPEN' CHECK (resolution_status IN ('OPEN', 'INVESTIGATING', 'RESOLVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_incidents_trace ON semantic_incidents (trace_id);
CREATE INDEX IF NOT EXISTS idx_incidents_type ON semantic_incidents (incident_type);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON semantic_incidents (resolution_status);

-- Vista para KPIs del dashboard
CREATE OR REPLACE VIEW dashboard_kpis AS
SELECT
    (SELECT COUNT(*) FROM audit_log WHERE timestamp > NOW() - INTERVAL '24 hours') as actions_last_24h,
    (SELECT AVG(total_latency_ms) FROM audit_log WHERE timestamp > NOW() - INTERVAL '24 hours') as avg_latency_24h,
    (SELECT COUNT(*) FROM audit_log WHERE decision = 'DENY' AND timestamp > NOW() - INTERVAL '24 hours')::FLOAT /
        NULLIF((SELECT COUNT(*) FROM audit_log WHERE timestamp > NOW() - INTERVAL '24 hours'), 0) * 100 as deny_rate_pct,
    (SELECT COUNT(*) FROM semantic_incidents WHERE resolution_status = 'OPEN') as open_incidents,
    (SELECT COUNT(*) FROM audit_log WHERE is_certifiable = TRUE AND timestamp > NOW() - INTERVAL '24 hours')::FLOAT /
        NULLIF((SELECT COUNT(*) FROM audit_log WHERE timestamp > NOW() - INTERVAL '24 hours'), 0) * 100 as certifiable_rate_pct;

-- Función para generar firma digital (SHA256 del contenido)
CREATE OR REPLACE FUNCTION generate_audit_signature(
    p_trace_id VARCHAR,
    p_decision VARCHAR,
    p_timestamp TIMESTAMPTZ
) RETURNS VARCHAR AS $$
BEGIN
    RETURN encode(
        digest(
            p_trace_id || p_decision || p_timestamp::TEXT,
            'sha256'
        ),
        'hex'
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger para calcular firma automáticamente
CREATE OR REPLACE FUNCTION set_audit_signature()
RETURNS TRIGGER AS $$
BEGIN
    NEW.signature := generate_audit_signature(NEW.trace_id, NEW.decision, NEW.timestamp);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_signature_trigger
    BEFORE INSERT ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION set_audit_signature();
