"""
═══════════════════════════════════════════════════════════
RAGF Audit Metrics
Consultas de KPIs para el dashboard
═══════════════════════════════════════════════════════════
"""

import asyncpg
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


class AuditMetrics:
    """Cliente para consultar métricas del audit log"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def get_dashboard_kpis(self) -> Dict[str, Any]:
        """
        Obtiene KPIs principales para el dashboard.
        
        Returns:
            Dict con métricas clave
        """
        query = "SELECT * FROM dashboard_kpis"
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            
            if not row:
                return {}
            
            return {
                "actions_last_24h": row["actions_last_24h"] or 0,
                "avg_latency_24h": round(row["avg_latency_24h"] or 0, 2),
                "deny_rate_pct": round(row["deny_rate_pct"] or 0, 2),
                "open_incidents": row["open_incidents"] or 0,
                "certifiable_rate_pct": round(row["certifiable_rate_pct"] or 0, 2)
            }
    
    async def get_mttv(self, hours: int = 24) -> float:
        """
        Mean Time To Validation (MTTV) - KPI crítico para certificación.
        
        Args:
            hours: Ventana de tiempo (default: últimas 24h)
        
        Returns:
            MTTV en milisegundos (p95)
        """
        query = """
        SELECT 
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) as p95_latency
        FROM audit_log
        WHERE timestamp > NOW() - INTERVAL '$1 hours'
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, hours)
            return round(row["p95_latency"] or 0, 2)
    
    async def get_validation_pass_rate(self, amm_level: int | None = None) -> float:
        """
        % de acciones que pasan el Validation Gate sin escalación.
        
        Args:
            amm_level: Filtrar por nivel AMM (opcional)
        
        Returns:
            Pass rate como porcentaje (0-100)
        """
        if amm_level:
            query = """
            SELECT 
                COUNT(CASE WHEN decision = 'ALLOW' THEN 1 END)::FLOAT / 
                NULLIF(COUNT(*), 0) * 100 as pass_rate
            FROM audit_log
            WHERE amm_level = $1
              AND timestamp > NOW() - INTERVAL '24 hours'
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, amm_level)
        else:
            query = """
            SELECT 
                COUNT(CASE WHEN decision = 'ALLOW' THEN 1 END)::FLOAT / 
                NULLIF(COUNT(*), 0) * 100 as pass_rate
            FROM audit_log
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            """
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query)
        
        return round(row["pass_rate"] or 0, 2)
