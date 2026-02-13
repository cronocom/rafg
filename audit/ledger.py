"""
═══════════════════════════════════════════════════════════
RAGF Audit Ledger
Escritura inmutable en TimescaleDB
═══════════════════════════════════════════════════════════
"""

import asyncpg
import structlog
from datetime import datetime
from shared.models import Verdict
from shared.exceptions import AuditWriteError

logger = structlog.get_logger()


class AuditLedger:
    """
    Cliente para escribir en el audit log de TimescaleDB.
    
    CRÍTICO: Si la escritura falla, la acción NO se ejecuta.
    Sin auditoría = Sin certificación.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool: asyncpg.Pool | None = None
    
    async def connect(self):
        """Crear connection pool"""
        self.pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=2,
            max_size=10
        )
        logger.info("audit_ledger_connected", database=self.database)
    
    async def close(self):
        """Cerrar connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("audit_ledger_disconnected")
    
    async def write(self, verdict: Verdict) -> bool:
        """
        Escribe un veredicto en el audit log.
        
        Args:
            verdict: El veredicto a auditar
        
        Returns:
            True si se escribió correctamente
        
        Raises:
            AuditWriteError si falla la escritura
        """
        if not self.pool:
            raise AuditWriteError(
                verdict.trace_id,
                "Audit ledger not connected"
            )
        
        query = """
        INSERT INTO audit_log (
            trace_id,
            timestamp,
            decision,
            reason,
            agent_id,
            amm_level,
            action_verb,
            action_resource,
            action_domain,
            action_parameters,
            semantic_ontology_match,
            semantic_amm_authorized,
            semantic_coverage,
            validator_results,
            total_latency_ms,
            is_certifiable,
            metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17
        )
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    verdict.trace_id,
                    verdict.timestamp,
                    verdict.decision,
                    verdict.reason,
                    verdict.agent_id,
                    int(verdict.amm_level),
                    verdict.action.verb,
                    verdict.action.resource,
                    verdict.action.domain,
                    verdict.action.parameters,  # JSONB
                    verdict.semantic_verdict.ontology_match,
                    verdict.semantic_verdict.amm_authorized,
                    verdict.semantic_verdict.coverage,
                    [v.model_dump() for v in verdict.validator_results],  # JSONB
                    verdict.total_latency_ms,
                    verdict.is_certifiable,
                    {}  # metadata adicional
                )
            
            logger.info(
                "audit_written",
                trace_id=verdict.trace_id,
                decision=verdict.decision,
                is_certifiable=verdict.is_certifiable
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "audit_write_failed",
                trace_id=verdict.trace_id,
                error=str(e)
            )
            raise AuditWriteError(verdict.trace_id, str(e))
