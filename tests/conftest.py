"""
═══════════════════════════════════════════════════════════
RAGF Pytest Configuration
Fixtures compartidos para todos los tests
═══════════════════════════════════════════════════════════
"""

import pytest
import pytest_asyncio
import os

# Configurar variables de entorno para tests
# IMPORTANTE: Dentro de Docker, usar nombres de servicio, no localhost
os.environ["NEO4J_URI"] = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
os.environ["NEO4J_USER"] = os.getenv("NEO4J_USER", "neo4j")
os.environ["NEO4J_PASSWORD"] = os.getenv("NEO4J_PASSWORD", "ragf_secure_2026")
os.environ["POSTGRES_HOST"] = os.getenv("POSTGRES_HOST", "timescaledb")
os.environ["POSTGRES_PORT"] = os.getenv("POSTGRES_PORT", "5432")
os.environ["POSTGRES_DB"] = os.getenv("POSTGRES_DB", "ragf_audit")
os.environ["POSTGRES_USER"] = os.getenv("POSTGRES_USER", "ragf")
os.environ["POSTGRES_PASSWORD"] = os.getenv("POSTGRES_PASSWORD", "audit_secure_2026")
os.environ["REDIS_HOST"] = os.getenv("REDIS_HOST", "redis")
os.environ["REDIS_PORT"] = os.getenv("REDIS_PORT", "6379")
os.environ["REDIS_PASSWORD"] = os.getenv("REDIS_PASSWORD", "redis_secure_2026")
os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "test-key")


@pytest_asyncio.fixture
async def neo4j_client():
    """Neo4j client fixture - usando pytest_asyncio.fixture"""
    from gateway.neo4j_client import Neo4jClient
    
    client = Neo4jClient(
        uri=os.getenv("NEO4J_URI"),
        user=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD")
    )
    await client.connect()
    
    yield client
    
    await client.close()


@pytest_asyncio.fixture
async def redis_client():
    """Redis client fixture"""
    import redis.asyncio as redis
    
    client = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT")),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True
    )
    
    yield client
    
    await client.close()


@pytest.fixture
def sample_action():
    """Sample ActionPrimitive for testing"""
    from shared.models import ActionPrimitive
    
    return ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB3202",
        parameters={
            "new_destination": "MAD",
            "current_fuel_kg": 12000,  # Suficiente para 180nm + 30min reserva
            "new_distance_nm": 180,
            "current_duty_minutes": 300,
            "additional_flight_minutes": 60,
            "is_night": False
        },
        domain="aviation",
        confidence=0.95
    )
