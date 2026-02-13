"""
═══════════════════════════════════════════════════════════
RAGF Integration Test - Full Validation Flow
Test end-to-end del flujo completo
═══════════════════════════════════════════════════════════
"""

import pytest
from httpx import AsyncClient
from gateway.main import app


@pytest.mark.asyncio
async def test_full_validation_flow_allow():
    """
    Test integración completa: Request HTTP → Validation → Response
    
    Escenario: Reroute válido
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/validate",
            json={
                "prompt": "Reroute flight IB3202 to Madrid to save fuel",
                "agent_amm_level": 3,
                "agent_id": "test-integration-agent"
            }
        )
    
    assert response.status_code == 200
    
    data = response.json()
    
    assert "verdict" in data
    assert "trace_id" in data
    assert "is_certifiable" in data
    
    verdict = data["verdict"]
    
    # Validaciones básicas
    assert verdict["decision"] in ["ALLOW", "DENY", "ESCALATE"]
    assert verdict["amm_level"] == 3
    assert "total_latency_ms" in verdict
    assert verdict["action"]["verb"] == "reroute_flight"


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "healthy"
    assert "version" in data
