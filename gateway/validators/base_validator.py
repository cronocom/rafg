"""
═══════════════════════════════════════════════════════════
RAGF Base Validator
Capa 3: The Validation Gate (Abstract)
═══════════════════════════════════════════════════════════

Define la interfaz que deben implementar todos los validadores.
"""

from abc import ABC, abstractmethod
import time
from shared.models import ActionPrimitive, ValidatorResult


class BaseValidator(ABC):
    """
    Clase abstracta para validadores independientes.
    
    Contrato:
    - validate() debe retornar ValidatorResult en < timeout_ms
    - NO debe hacer llamadas a LLMs (solo lógica determinista)
    - NO debe comunicarse con otros validadores (independencia)
    """
    
    def __init__(self, name: str, timeout_ms: float = 50.0):
        self.name = name
        self.timeout_ms = timeout_ms
    
    async def validate(self, action: ActionPrimitive) -> ValidatorResult:
        """
        Ejecuta validación con timeout automático.
        
        Returns:
            ValidatorResult con PASS/FAIL/TIMEOUT
        """
        start_time = time.perf_counter()
        
        try:
            # Delegar a implementación específica
            decision, reason, rule_violated = await self._validate_impl(action)
            
            latency = (time.perf_counter() - start_time) * 1000  # ms
            
            return ValidatorResult(
                validator_name=self.name,
                decision=decision,
                reason=reason,
                latency_ms=latency,
                rule_violated=rule_violated
            )
            
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            return ValidatorResult(
                validator_name=self.name,
                decision="FAIL",
                reason=f"Validator exception: {str(e)}",
                latency_ms=latency,
                rule_violated=None
            )
    
    @abstractmethod
    async def _validate_impl(
        self,
        action: ActionPrimitive
    ) -> tuple[str, str, str | None]:
        """
        Implementación específica del validador.
        
        Returns:
            (decision: "PASS"|"FAIL", reason: str, rule_violated: str|None)
        """
        pass
