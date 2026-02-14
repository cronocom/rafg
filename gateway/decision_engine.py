"""
═══════════════════════════════════════════════════════════
RAGF Decision Engine
El Orquestador Central del Validation Gate
═══════════════════════════════════════════════════════════

Combina:
- Semantic Verdict (Neo4j)
- Validator Results (Independent Validators)

Produce:
- Verdict final (ALLOW/DENY/ESCALATE)
"""

from __future__ import annotations

import asyncio
import time
import structlog
from typing import List
from shared.models import (
    ActionPrimitive,
    AMMLevel,
    SemanticVerdict,
    ValidatorResult,
    Verdict
)
from shared.exceptions import ValidationTimeoutError
from gateway.neo4j_client import Neo4jClient
from gateway.validators.safety_validator import get_validator

logger = structlog.get_logger()


class DecisionEngine:
    """
    Motor de decisión que orquesta el Validation Gate.
    
    Secuencia:
    1. Validación semántica (Neo4j)
    2. Si ALLOW → Ejecutar validadores en paralelo
    3. Agregar resultados → Verdict final
    """
    
    def __init__(
        self,
        neo4j_client: Neo4jClient,
        validation_timeout_ms: float = 200.0
    ):
        self.neo4j = neo4j_client
        self.validation_timeout_ms = validation_timeout_ms
        self.validator_timeout_ms = 150.0  # Presupuesto para validators
        self._health_check_cache = {"healthy": True, "last_check": 0.0}
    
    async def _check_validator_health(self) -> bool:
        """
        Health check del Validation Gate (v2.0 feature).
        
        Verifica:
        - Neo4j responde a pings
        - Cache no se usa si health check falló hace <30s
        
        Returns:
            True si todos los validadores están operacionales
        """
        current_time = time.time()
        
        # Use cache if recent check passed
        if (self._health_check_cache["healthy"] and 
            current_time - self._health_check_cache["last_check"] < 30):
            return True
        
        try:
            # Ping Neo4j using the actual driver API
            if not self.neo4j.driver:
                raise Exception("Neo4j driver not connected")
            
            async with self.neo4j.driver.session() as session:
                await asyncio.wait_for(
                    session.run("RETURN 1 AS ping"),
                    timeout=0.5  # 500ms timeout for health check
                )
            
            self._health_check_cache = {
                "healthy": True,
                "last_check": current_time
            }
            return True
        
        except Exception as e:
            logger.warning(
                "health_check_failed",
                error=str(e),
                component="neo4j"
            )
            self._health_check_cache = {
                "healthy": False,
                "last_check": current_time
            }
            return False
    
    async def evaluate(
        self,
        action: ActionPrimitive,
        amm_level: AMMLevel,
        trace_id: str,
        agent_id: str | None = None
    ) -> Verdict:
        """
        Evalúa una acción a través del Validation Gate completo.
        
        v2.0 Features:
        - Health check before validation
        - Timeout and error handling on all operations
        - HMAC signature generation
        - Ultimate catch-all fail-closed wrapper
        
        Args:
            action: La acción a validar
            amm_level: Nivel AMM del agente
            trace_id: ID de transacción para auditoría
            agent_id: Identificador del agente (opcional)
        
        Returns:
            Verdict con decisión final (includes HMAC signature)
        """
        start_time = time.perf_counter()
        
        # Ultimate fail-safe: Catch ANY unexpected exception
        try:
            return await self._evaluate_internal(
                action, amm_level, trace_id, agent_id, start_time
            )
        except Exception as e:
            # CRITICAL: Unexpected exception in Validation Gate - fail-closed
            logger.critical(
                "gate_internal_error",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__,
                verb=action.verb if action else "unknown"
            )
            
            return Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason=f"GATE_INTERNAL_ERROR | Unexpected exception: {str(e)}",
                amm_level=amm_level,
                semantic_verdict=SemanticVerdict(
                    decision="DENY",
                    reason="Validation Gate internal error - fail-closed for safety",
                    ontology_match=False,
                    amm_authorized=False,
                    coverage=0.0
                ),
                validator_results=[],
                total_latency_ms=(time.perf_counter() - start_time) * 1000,
                action=action,
                agent_id=agent_id,
                signature=""
            )
    
    async def _evaluate_internal(
        self,
        action: ActionPrimitive,
        amm_level: AMMLevel,
        trace_id: str,
        agent_id: str | None,
        start_time: float
    ) -> Verdict:
        """
        Internal evaluation logic (wrapped by evaluate() for fail-closed safety).
        """
        
        # ═══════════════════════════════════════════════════════
        # v2.0: Health Check (Fail-Closed Pattern)
        # ═══════════════════════════════════════════════════════
        
        if not await self._check_validator_health():
            logger.error(
                "validation_denied_unhealthy",
                trace_id=trace_id,
                reason="Validators unhealthy"
            )
            
            return Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason="VALIDATOR_UNHEALTHY | Neo4j connection failed",
                amm_level=amm_level,
                semantic_verdict=SemanticVerdict(
                    decision="DENY",
                    reason="Health check failed",
                    ontology_match=False,
                    amm_authorized=False,
                    coverage=0.0
                ),
                validator_results=[],
                total_latency_ms=(time.perf_counter() - start_time) * 1000,
                action=action,
                agent_id=agent_id
            )
        
        start_time = time.perf_counter()
        
        # ═══════════════════════════════════════════════════════
        # FASE 1: Validación Semántica (Neo4j)
        # ═══════════════════════════════════════════════════════
        
        logger.info(
            "validation_started",
            trace_id=trace_id,
            verb=action.verb,
            amm_level=int(amm_level)
        )
        
        # Semantic validation with timeout and error handling (fail-closed)
        try:
            semantic_verdict = await asyncio.wait_for(
                self.neo4j.validate_semantic_authority(action, amm_level),
                timeout=0.5  # 500ms timeout for semantic validation
            )
        except asyncio.TimeoutError:
            logger.error(
                "semantic_validation_timeout",
                trace_id=trace_id,
                timeout_ms=500
            )
            
            return Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason="SEMANTIC_VALIDATION_TIMEOUT | Neo4j query exceeded 500ms",
                amm_level=amm_level,
                semantic_verdict=SemanticVerdict(
                    decision="DENY",
                    reason="Semantic validation timeout",
                    ontology_match=False,
                    amm_authorized=False,
                    coverage=0.0
                ),
                validator_results=[],
                total_latency_ms=(time.perf_counter() - start_time) * 1000,
                action=action,
                agent_id=agent_id,
                signature=""
            )
        except Exception as e:
            logger.error(
                "semantic_validation_error",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__
            )
            
            return Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason=f"SEMANTIC_VALIDATION_ERROR | {str(e)}",
                amm_level=amm_level,
                semantic_verdict=SemanticVerdict(
                    decision="DENY",
                    reason=f"Semantic validation failed: {str(e)}",
                    ontology_match=False,
                    amm_authorized=False,
                    coverage=0.0
                ),
                validator_results=[],
                total_latency_ms=(time.perf_counter() - start_time) * 1000,
                action=action,
                agent_id=agent_id,
                signature=""
            )
        
        # Fast rejection: si semántica falla, no ejecutar validadores
        if semantic_verdict.decision == "DENY":
            latency = (time.perf_counter() - start_time) * 1000
            
            verdict = Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason=semantic_verdict.reason,
                amm_level=amm_level,
                semantic_verdict=semantic_verdict,
                validator_results=[],
                total_latency_ms=latency,
                action=action,
                agent_id=agent_id
            )
            
            logger.info(
                "validation_denied_semantic",
                trace_id=trace_id,
                reason=semantic_verdict.reason,
                latency_ms=latency
            )
            
            return verdict
        
        # ═══════════════════════════════════════════════════════
        # FASE 2: Obtener Validadores Requeridos
        # ═══════════════════════════════════════════════════════
        
        required_validator_names = await self.neo4j.get_required_validators(action)
        
        if not required_validator_names:
            # No hay validadores → ALLOW directo
            latency = (time.perf_counter() - start_time) * 1000
            
            verdict = Verdict(
                trace_id=trace_id,
                decision="ALLOW",
                reason="No validators required for this action",
                amm_level=amm_level,
                semantic_verdict=semantic_verdict,
                validator_results=[],
                total_latency_ms=latency,
                action=action,
                agent_id=agent_id
            )
            
            logger.info(
                "validation_allowed_no_validators",
                trace_id=trace_id,
                latency_ms=latency
            )
            
            return verdict
        
        # ═══════════════════════════════════════════════════════
        # FASE 3: Ejecutar Validadores en Paralelo
        # ═══════════════════════════════════════════════════════
        
        validators = [get_validator(name) for name in required_validator_names]
        
        try:
            validator_results = await asyncio.wait_for(
                asyncio.gather(
                    *[v.validate(action) for v in validators],
                    return_exceptions=True
                ),
                timeout=self.validator_timeout_ms / 1000.0
            )
            
            # Convertir excepciones en ValidatorResults
            processed_results: List[ValidatorResult] = []
            for i, result in enumerate(validator_results):
                if isinstance(result, Exception):
                    processed_results.append(ValidatorResult(
                        validator_name=validators[i].name,
                        decision="FAIL",
                        reason=f"Validator raised exception: {str(result)}",
                        latency_ms=0.0,
                        rule_violated=None
                    ))
                else:
                    processed_results.append(result)
        
        except asyncio.TimeoutError:
            # Timeout crítico → DENY automático
            latency = (time.perf_counter() - start_time) * 1000
            
            logger.error(
                "validators_timeout",
                trace_id=trace_id,
                timeout_ms=self.validator_timeout_ms
            )
            
            # Crear resultados de timeout para todos los validadores
            timeout_results = [
                ValidatorResult(
                    validator_name=v.name,
                    decision="TIMEOUT",
                    reason=f"Validator exceeded timeout of {self.validator_timeout_ms}ms",
                    latency_ms=self.validator_timeout_ms,
                    rule_violated=None
                )
                for v in validators
            ]
            
            verdict = Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason=f"Validation timeout: exceeded {self.validator_timeout_ms}ms budget",
                amm_level=amm_level,
                semantic_verdict=semantic_verdict,
                validator_results=timeout_results,
                total_latency_ms=latency,
                action=action,
                agent_id=agent_id
            )
            
            return verdict
        
        # ═══════════════════════════════════════════════════════
        # FASE 4: Agregación de Resultados → Decisión Final
        # ═══════════════════════════════════════════════════════
        
        latency = (time.perf_counter() - start_time) * 1000
        
        # Determinar decisión final
        final_decision, final_reason = self._aggregate_decisions(
            semantic_verdict,
            processed_results
        )
        
        verdict = Verdict(
            trace_id=trace_id,
            decision=final_decision,
            reason=final_reason,
            amm_level=amm_level,
            semantic_verdict=semantic_verdict,
            validator_results=processed_results,
            total_latency_ms=latency,
            action=action,
            agent_id=agent_id
        )
        
        # v2.0: Generate HMAC signature for non-repudiation (fail-closed on error)
        try:
            verdict.signature = verdict.compute_signature()
            
            logger.info(
                "validation_complete",
                trace_id=trace_id,
                decision=final_decision,
                latency_ms=latency,
                validator_count=len(processed_results),
                is_certifiable=verdict.is_certifiable,
                signature=verdict.signature[:16] + "..."  # Log first 16 chars
            )
            
            return verdict
            
        except Exception as e:
            # CRITICAL: Signature generation failed - fail-closed
            logger.critical(
                "signature_generation_failed",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__
            )
            
            # Return DENY verdict - cannot guarantee integrity without signature
            return Verdict(
                trace_id=trace_id,
                decision="DENY",
                reason=f"SIGNATURE_GENERATION_FAILED | {str(e)}",
                amm_level=amm_level,
                semantic_verdict=SemanticVerdict(
                    decision="DENY",
                    reason="Signature generation failed - system integrity compromised",
                    ontology_match=False,
                    amm_authorized=False,
                    coverage=0.0
                ),
                validator_results=[],
                total_latency_ms=(time.perf_counter() - start_time) * 1000,
                action=action,
                agent_id=agent_id,
                signature=""  # No signature on error
            )
    
    def _aggregate_decisions(
        self,
        semantic_verdict: SemanticVerdict,
        validator_results: List[ValidatorResult]
    ) -> tuple[str, str]:
        """
        Lógica de agregación de veredictos.
        
        Reglas:
        1. Si algún validator FAIL o TIMEOUT → DENY
        2. Si semantic coverage < 1.0 → ESCALATE
        3. Si todos PASS y coverage = 1.0 → ALLOW
        
        Returns:
            (decision: "ALLOW"|"DENY"|"ESCALATE", reason: str)
        """
        # Regla 1: Veto por FAIL o TIMEOUT
        failed_validators = [
            v for v in validator_results 
            if v.decision in ["FAIL", "TIMEOUT"]
        ]
        
        if failed_validators:
            failed_names = [v.validator_name for v in failed_validators]
            violations = [
                v.rule_violated for v in failed_validators 
                if v.rule_violated
            ]
            
            reason = f"Validators failed: {', '.join(failed_names)}"
            if violations:
                reason += f" | Regulations violated: {', '.join(violations)}"
            
            return ("DENY", reason)
        
        # Regla 2: Escalate si cobertura semántica imperfecta
        if semantic_verdict.coverage < 1.0:
            return (
                "ESCALATE",
                f"Semantic coverage {semantic_verdict.coverage:.2f} < 1.0 | "
                f"Human review required for edge case"
            )
        
        # Regla 3: ALLOW si todo pasa
        passed_validators = [v.validator_name for v in validator_results]
        return (
            "ALLOW",
            f"All validators passed: {', '.join(passed_validators)} | "
            f"Semantic coverage: 1.0"
        )
