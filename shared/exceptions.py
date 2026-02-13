"""
═══════════════════════════════════════════════════════════
RAGF Custom Exceptions
═══════════════════════════════════════════════════════════
"""


class RAGFException(Exception):
    """Excepción base para todo el framework"""
    pass


class SemanticDriftError(RAGFException):
    """
    Lanzada cuando la ontología no contiene el verbo solicitado.
    Indica que el LLM ha "alucinado" una acción fuera del vocabulario gobernado.
    """
    def __init__(self, verb: str, domain: str):
        self.verb = verb
        self.domain = domain
        super().__init__(
            f"Verb '{verb}' not found in ontology for domain '{domain}'. "
            "This is a semantic drift - the LLM proposed an ungoverned action."
        )


class ValidationTimeoutError(RAGFException):
    """
    Lanzada cuando un validador excede el presupuesto de latencia.
    Safety-first: timeout = DENY automático.
    """
    def __init__(self, validator_name: str, timeout_ms: float):
        self.validator_name = validator_name
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Validator '{validator_name}' exceeded timeout of {timeout_ms}ms. "
            "Action DENIED per fail-safe policy."
        )


class AMMViolationError(RAGFException):
    """
    Lanzada cuando el agente intenta una acción por encima de su nivel AMM.
    Ejemplo: Agente L2 (Human Teaming) intenta ejecutar (L3 action).
    """
    def __init__(self, action_verb: str, required_amm: int, current_amm: int):
        self.action_verb = action_verb
        self.required_amm = required_amm
        self.current_amm = current_amm
        super().__init__(
            f"Action '{action_verb}' requires AMM Level {required_amm}, "
            f"but agent is only Level {current_amm}"
        )


class OntologyNotFoundError(RAGFException):
    """
    Lanzada cuando no se encuentra una ontología para el dominio especificado.
    """
    def __init__(self, domain: str):
        self.domain = domain
        super().__init__(f"No ontology found for domain '{domain}'")


class AuditWriteError(RAGFException):
    """
    Lanzada cuando falla la escritura en el audit ledger.
    CRÍTICO: Si no podemos auditar, no podemos ejecutar.
    """
    def __init__(self, trace_id: str, reason: str):
        self.trace_id = trace_id
        self.reason = reason
        super().__init__(
            f"Failed to write audit log for trace_id '{trace_id}': {reason}"
        )
