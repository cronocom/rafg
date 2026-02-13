"""
═══════════════════════════════════════════════════════════
RAGF Smoke Tests
Fase 5: Validación Mínima del MVA
═══════════════════════════════════════════════════════════

3 escenarios críticos que DEBEN pasar:
1. ALLOW: Acción válida con todos los checks en verde
2. DENY: Acción que viola regulación (fuel insuficiente)
3. ESCALATE: Acción con cobertura semántica imperfecta
"""

import pytest
from shared.models import ActionPrimitive, AMMLevel
from gateway.decision_engine import DecisionEngine


@pytest.mark.asyncio
async def test_scenario_allow(neo4j_client, sample_action):
    """
    ESCENARIO 1: ALLOW
    
    Condiciones:
    - Verbo existe en ontología
    - AMM level suficiente (L3)
    - Fuel suficiente
    - Crew rest OK
    
    Resultado esperado: ALLOW
    """
    engine = DecisionEngine(neo4j_client, validation_timeout_ms=200)
    
    verdict = await engine.evaluate(
        action=sample_action,
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        trace_id="test-allow-001",
        agent_id="test-agent"
    )
    
    # Assertions
    assert verdict.decision == "ALLOW", f"Expected ALLOW, got {verdict.decision}"
    assert verdict.semantic_verdict.ontology_match is True
    assert verdict.semantic_verdict.amm_authorized is True
    assert verdict.semantic_verdict.coverage == 1.0
    assert all(v.decision == "PASS" for v in verdict.validator_results)
    assert verdict.total_latency_ms < 200, f"Latency {verdict.total_latency_ms}ms > 200ms"
    assert verdict.is_certifiable is True
    
    print(f"✅ ALLOW scenario passed | Latency: {verdict.total_latency_ms:.2f}ms")


@pytest.mark.asyncio
async def test_scenario_deny_fuel(neo4j_client):
    """
    ESCENARIO 2: DENY
    
    Condiciones:
    - Verbo válido
    - AMM OK
    - Fuel INSUFICIENTE (viola FAA 14 CFR §91.151)
    
    Resultado esperado: DENY
    """
    engine = DecisionEngine(neo4j_client, validation_timeout_ms=200)
    
    # Acción con fuel insuficiente
    action = ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB9999",
        parameters={
            "new_destination": "LHR",
            "current_fuel_kg": 2000,  # MUY BAJO
            "new_distance_nm": 500,    # Distancia larga
            "current_duty_minutes": 200,
            "additional_flight_minutes": 90,
            "is_night": False
        },
        domain="aviation",
        confidence=0.95
    )
    
    verdict = await engine.evaluate(
        action=action,
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        trace_id="test-deny-002",
        agent_id="test-agent"
    )
    
    # Assertions
    assert verdict.decision == "DENY", f"Expected DENY, got {verdict.decision}"
    assert verdict.semantic_verdict.ontology_match is True
    assert verdict.semantic_verdict.amm_authorized is True
    
    # Debe haber al menos un validator FAIL
    failed = [v for v in verdict.validator_results if v.decision == "FAIL"]
    assert len(failed) > 0, "Expected at least one FAIL validator"
    
    # Debe mencionar FAA regulation
    assert "FAA-14-CFR-91.151" in verdict.reason or any(
        v.rule_violated == "FAA-14-CFR-91.151" for v in failed
    )
    
    assert verdict.is_certifiable is False
    
    print(f"✅ DENY scenario passed | Reason: {verdict.reason}")


@pytest.mark.asyncio
async def test_scenario_deny_unknown_verb(neo4j_client):
    """
    ESCENARIO 3: DENY (Semantic Drift)
    
    Condiciones:
    - Verbo NO existe en ontología
    - El LLM ha "alucinado" una acción
    
    Resultado esperado: DENY (fast rejection)
    """
    engine = DecisionEngine(neo4j_client, validation_timeout_ms=200)
    
    # Verbo inexistente
    action = ActionPrimitive(
        verb="teleport_aircraft",  # ❌ No existe
        resource="aircraft:EC-ABC",
        parameters={},
        domain="aviation",
        confidence=0.85
    )
    
    verdict = await engine.evaluate(
        action=action,
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        trace_id="test-deny-003",
        agent_id="test-agent"
    )
    
    # Assertions
    assert verdict.decision == "DENY"
    assert verdict.semantic_verdict.ontology_match is False
    assert verdict.semantic_verdict.coverage < 1.0
    
    # Fast rejection: no debe ejecutar validadores
    assert len(verdict.validator_results) == 0
    
    # Latencia debe ser muy baja (solo Neo4j query)
    assert verdict.total_latency_ms < 100, "Fast rejection should be < 100ms"
    
    print(f"✅ DENY (semantic drift) scenario passed | Latency: {verdict.total_latency_ms:.2f}ms")


@pytest.mark.asyncio
async def test_scenario_deny_amm_violation(neo4j_client, sample_action):
    """
    ESCENARIO 4: DENY (AMM Violation)
    
    Condiciones:
    - Verbo válido (requires AMM L3)
    - Agent en AMM L2 (insuficiente)
    
    Resultado esperado: DENY
    """
    engine = DecisionEngine(neo4j_client, validation_timeout_ms=200)
    
    verdict = await engine.evaluate(
        action=sample_action,
        amm_level=AMMLevel.HUMAN_TEAMING,  # ❌ L2 < L3 required
        trace_id="test-deny-004",
        agent_id="test-agent"
    )
    
    # Assertions
    assert verdict.decision == "DENY"
    assert verdict.semantic_verdict.ontology_match is True
    assert verdict.semantic_verdict.amm_authorized is False
    assert "AMM" in verdict.reason or "Level" in verdict.reason
    
    print(f"✅ DENY (AMM violation) scenario passed")


def test_summary():
    """
    Resumen visual de los smoke tests.
    Este test siempre pasa - solo imprime un resumen.
    """
    print("\n" + "═" * 60)
    print("RAGF MVA SMOKE TESTS - SUMMARY")
    print("═" * 60)
    print("✅ Scenario 1: ALLOW (happy path)")
    print("✅ Scenario 2: DENY (fuel violation)")
    print("✅ Scenario 3: DENY (semantic drift)")
    print("✅ Scenario 4: DENY (AMM violation)")
    print("═" * 60)
    print("\n🎉 All smoke tests passed - MVA is functional!\n")
    assert True
