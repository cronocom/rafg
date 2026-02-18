"""
RAGF Demo Engine - FastAPI Application
=======================================
Interactive demo server for fintech validators.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import time
from pathlib import Path

# Add gateway to path
sys.path.insert(0, '/app')

# Import fintech validators directly
from gateway.validators.fintech.composite_validator import FintechValidationEngine
from app.demos.fintech_scenarios import FINTECH_SCENARIOS, get_scenario


app = FastAPI(
    title="RAGF Demo Engine",
    description="Interactive demos for AI governance in regulated sectors",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize validation engine
validation_engine = FintechValidationEngine(
    max_latency_ms=200,
    enable_circuit_breaker=True
)


class ValidationRequest(BaseModel):
    scenario_id: str


class ValidationResponse(BaseModel):
    scenario_id: str
    decision: str
    reason: str
    regulatory_ref: str
    remediation: str
    latency_ms: float
    teaching_point: str
    action_payload: dict


@app.get("/")
async def root():
    return {
        "service": "RAGF Demo Engine",
        "version": "1.0.0",
        "status": "running",
        "scenarios_available": len(FINTECH_SCENARIOS)
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/scenarios")
async def list_scenarios():
    """List all available demo scenarios."""
    return {
        "scenarios": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "expected_outcome": s.expected_outcome
            }
            for s in FINTECH_SCENARIOS
        ]
    }


@app.post("/validate", response_model=ValidationResponse)
async def validate_scenario(request: ValidationRequest):
    """Execute a demo scenario through RAGF validation."""
    try:
        scenario = get_scenario(request.scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    # Measure validation time
    start_time = time.time()
    result = validation_engine.validate(scenario.action)
    latency_ms = (time.time() - start_time) * 1000
    
    return ValidationResponse(
        scenario_id=scenario.id,
        decision=result.decision.value,
        reason=result.reason,
        regulatory_ref=result.regulatory_ref,
        remediation=result.remediation or "No action required",
        latency_ms=round(latency_ms, 2),
        teaching_point=scenario.teaching_point,
        action_payload=scenario.action
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
