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
    
    async def evaluate(
        self,
        action: ActionPrimitive,
        amm_level: AMMLevel,
        trace_id: str,
        agent_id: str | None = None
    ) -> Verdict:
        """
        Evalúa una acción a través del Validation Gate completo.
        
        Args:
            action: La acción a validar
            amm_level: Nivel AMM del agente
            trace_id: ID de transacción para auditoría
            agent_id: Identificador del agente (opcional)
        
        Returns:
            Verdict con decisión final
        """
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
        
        semantic_verdict = await self.neo4j.validate_semantic_authority(
            action, amm_level
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
        
        logger.info(
            "validation_complete",
            trace_id=trace_id,
            decision=final_decision,
            latency_ms=latency,
            validator_count=len(processed_results),
            is_certifiable=verdict.is_certifiable
        )
        
        return verdict
    
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
