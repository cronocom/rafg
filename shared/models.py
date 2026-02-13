"""
═══════════════════════════════════════════════════════════
RAGF Core Models
Nivel 0: El Contrato (Shared Models)
═══════════════════════════════════════════════════════════

Este módulo define la "lengua franca" del sistema:
- ActionPrimitive: La unidad mínima de significado gobernado
- Verdict: El resultado de la validación
- AMMLevel: Niveles de madurez agéntica (1-5)
"""

from enum import IntEnum
from typing import Literal, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class AMMLevel(IntEnum):
    """Agentic Maturity Model - 5 niveles de autonomía"""
    PASSIVE_KNOWLEDGE = 1      # Solo lectura, consultas
    HUMAN_TEAMING = 2          # Asistente, humano ejecuta
    ACTIONABLE_AGENCY = 3      # Ejecuta acciones con validación
    AUTONOMOUS_ORCHESTRATION = 4  # Coordina múltiples agentes
    FULL_SYSTEMIC_AUTONOMY = 5    # Auto-regulación completa


class ActionPrimitive(BaseModel):
    """
    Unidad atómica de acción gobernada.
    Toda acción del agente DEBE ser destilada a este formato.
    """
    verb: str = Field(
        ..., 
        description="Acción en infinitivo (ej: 'reroute_flight', 'prescribe_medication')",
        min_length=3,
        max_length=50
    )
    resource: str = Field(
        ...,
        description="Entidad afectada (ej: 'flight:IB3202', 'patient:12345')",
        min_length=1,
        max_length=100
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros específicos de la acción"
    )
    domain: str = Field(
        ...,
        description="Dominio de conocimiento (aviation, healthcare, energy)",
        pattern="^[a-z_]+$"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confianza del LLM en la interpretación (0-1)"
    )
    
    @field_validator('verb')
    @classmethod
    def verb_must_be_lowercase(cls, v: str) -> str:
        if not v.islower():
            raise ValueError("Verb must be lowercase with underscores")
        return v


class SemanticVerdict(BaseModel):
    """Resultado de la validación semántica (Neo4j Layer 4)"""
    decision: Literal["ALLOW", "DENY", "ESCALATE"]
    reason: str = Field(..., min_length=10)
    ontology_match: bool = Field(
        ...,
        description="¿El verbo existe en la ontología?"
    )
    amm_authorized: bool = Field(
        ...,
        description="¿El nivel AMM actual permite esta acción?"
    )
    coverage: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cobertura semántica: 1.0 = totalmente definido"
    )


class ValidatorResult(BaseModel):
    """Resultado de un validador independiente (Layer 3)"""
    validator_name: str
    decision: Literal["PASS", "FAIL", "TIMEOUT"]
    reason: str
    latency_ms: float = Field(..., ge=0)
    rule_violated: Optional[str] = None  # ej: "FAA-14-CFR-91.151"


class Verdict(BaseModel):
    """
    Veredicto final del Validation Gate.
    Este es el objeto que se audita en TimescaleDB.
    """
    trace_id: str = Field(..., description="ID único de la transacción")
    decision: Literal["ALLOW", "DENY", "ESCALATE"]
    reason: str
    amm_level: AMMLevel
    
    # Desglose de cobertura
    semantic_verdict: SemanticVerdict
    validator_results: list[ValidatorResult] = Field(default_factory=list)
    
    # Métricas
    total_latency_ms: float = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Contexto para auditoría
    action: ActionPrimitive
    agent_id: Optional[str] = None
    
    @property
    def is_certifiable(self) -> bool:
        """
        Determina si esta acción es certificable según estándares.
        Requisitos:
        - Decisión ALLOW con cobertura semántica 1.0
        - Todos los validadores PASS
        - Latencia bajo presupuesto (200ms)
        """
        return (
            self.decision == "ALLOW"
            and self.semantic_verdict.coverage == 1.0
            and all(v.decision == "PASS" for v in self.validator_results)
            and self.total_latency_ms <= 200
        )


class ActionRequest(BaseModel):
    """Request DTO para el endpoint /v1/validate"""
    prompt: str = Field(
        ...,
        description="Intención del usuario en lenguaje natural",
        min_length=5,
        max_length=500
    )
    agent_amm_level: AMMLevel = Field(
        default=AMMLevel.ACTIONABLE_AGENCY,
        description="Nivel de madurez del agente que hace la petición"
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Identificador del agente (para auditoría)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Contexto adicional (ej: estado del sistema)"
    )


class ValidationResponse(BaseModel):
    """Response DTO del endpoint /v1/validate"""
    verdict: Verdict
    trace_id: str
    is_certifiable: bool
