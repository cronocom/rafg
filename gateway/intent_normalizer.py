"""
═══════════════════════════════════════════════════════════
RAGF Intent Normalizer
Nivel 1: El Cerebro Probabilístico
═══════════════════════════════════════════════════════════

Traduce lenguaje natural → ActionPrimitive determinista.
Restricción: No puede inventar verbos fuera de la ontología.
"""

import asyncio
import structlog
import anthropic
from typing import Tuple, Literal
import json
import redis.asyncio as redis
from shared.models import ActionPrimitive
from shared.exceptions import SemanticDriftError

logger = structlog.get_logger()

NormalizationMethod = Literal["CLAUDE", "FALLBACK", "CACHE"]


class IntentNormalizer:
    """
    Normaliza intenciones del usuario en ActionPrimitives.
    
    Arquitectura de 3 capas:
    1. Cache (Redis): Sub-5ms
    2. Claude API: 50-150ms (con timeout)
    3. Fallback determinista: 5-10ms
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        redis_client: redis.Redis,
        timeout_ms: float = 100.0
    ):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.redis = redis_client
        self.timeout_seconds = timeout_ms / 1000.0
        self.cache_ttl = 3600  # 1 hora
        
    async def normalize(
        self,
        prompt: str,
        domain: str = "aviation"
    ) -> Tuple[ActionPrimitive, NormalizationMethod]:
        """
        Normaliza prompt a ActionPrimitive.
        
        Returns:
            (ActionPrimitive, method: "CLAUDE" | "FALLBACK" | "CACHE")
        """
        # 1. Check cache
        cache_key = f"intent:{domain}:{hash(prompt)}"
        cached = await self.redis.get(cache_key)
        
        if cached:
            action = ActionPrimitive.model_validate_json(cached)
            logger.info("intent_normalized", method="CACHE", verb=action.verb)
            return action, "CACHE"
        
        # 2. Try Claude with aggressive timeout
        try:
            action = await asyncio.wait_for(
                self._call_claude(prompt, domain),
                timeout=self.timeout_seconds
            )
            
            # Cache success
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                action.model_dump_json()
            )
            
            logger.info("intent_normalized", method="CLAUDE", verb=action.verb)
            return action, "CLAUDE"
            
        except asyncio.TimeoutError:
            logger.warning(
                "claude_timeout",
                timeout_ms=self.timeout_seconds * 1000,
                falling_back=True
            )
            action = self._fallback_parser(prompt, domain)
            return action, "FALLBACK"
            
        except Exception as e:
            logger.error("claude_error", error=str(e), falling_back=True)
            action = self._fallback_parser(prompt, domain)
            return action, "FALLBACK"
    
    async def _call_claude(
        self,
        prompt: str,
        domain: str
    ) -> ActionPrimitive:
        """
        Llama a Claude 3.5 Sonnet para normalización semántica.
        
        Prompt Engineering:
        - Few-shot examples
        - Strict JSON schema
        - Explicit ontology constraints
        """
        system_prompt = f"""You are a semantic normalizer for the RAGF (Reflexio Agentic Governance Framework).

Your ONLY job is to convert user intentions into ActionPrimitive objects in strict JSON format.

Domain: {domain}
Allowed verbs for aviation: reroute_flight, adjust_altitude, schedule_maintenance, query_weather, calculate_fuel_requirement, optimize_fleet_allocation

CRITICAL RULES:
1. You MUST only use verbs from the allowed list above
2. If the user requests something not in the list, respond with verb "unknown_action"
3. Extract the resource being acted upon (e.g., "flight:IB3202")
4. Extract relevant parameters as key-value pairs
5. Assess your confidence in the interpretation (0.0 to 1.0)

Output ONLY valid JSON matching this schema:
{{
  "verb": "reroute_flight",
  "resource": "flight:IB3202",
  "parameters": {{"new_destination": "MAD", "reason": "fuel_optimization"}},
  "domain": "{domain}",
  "confidence": 0.95
}}

Examples:

User: "Reroute flight IB3202 to Madrid to save fuel"
Output: {{"verb": "reroute_flight", "resource": "flight:IB3202", "parameters": {{"new_destination": "MAD", "reason": "fuel_optimization"}}, "domain": "aviation", "confidence": 0.95}}

User: "What's the weather like for the route to Paris?"
Output: {{"verb": "query_weather", "resource": "route:CDG", "parameters": {{"destination": "CDG"}}, "domain": "aviation", "confidence": 0.90}}

User: "Schedule maintenance for aircraft EC-ABC"
Output: {{"verb": "schedule_maintenance", "resource": "aircraft:EC-ABC", "parameters": {{}}, "domain": "aviation", "confidence": 0.85}}

Now process this user request:"""

        response = await asyncio.to_thread(
            self.client.messages.create,
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            temperature=0.0,  # Determinista
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Extraer JSON de la respuesta
        content = response.content[0].text.strip()
        
        # Limpiar markdown si existe
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        
        try:
            data = json.loads(content)
            action = ActionPrimitive(**data)
            
            # Validar que no sea unknown_action
            if action.verb == "unknown_action":
                raise SemanticDriftError(action.verb, domain)
            
            return action
            
        except json.JSONDecodeError as e:
            logger.error("claude_invalid_json", content=content, error=str(e))
            raise
    
    def _fallback_parser(self, prompt: str, domain: str) -> ActionPrimitive:
        """
        Parser determinista basado en reglas para cuando Claude falla.
        
        Limitado pero confiable. Busca keywords:
        - "reroute" → reroute_flight
        - "altitude" → adjust_altitude
        - "maintenance" → schedule_maintenance
        - "weather" → query_weather
        """
        prompt_lower = prompt.lower()
        
        # Reglas simples
        if "reroute" in prompt_lower or "re-route" in prompt_lower:
            verb = "reroute_flight"
            # Intentar extraer flight number (ej: IB3202)
            import re
            match = re.search(r'\b([A-Z]{2}\d{3,4})\b', prompt)
            resource = f"flight:{match.group(1)}" if match else "flight:UNKNOWN"
            params = {"reason": "unspecified"}
            confidence = 0.6
            
        elif "altitude" in prompt_lower:
            verb = "adjust_altitude"
            resource = "flight:UNKNOWN"
            params = {}
            confidence = 0.5
            
        elif "maintenance" in prompt_lower:
            verb = "schedule_maintenance"
            resource = "aircraft:UNKNOWN"
            params = {}
            confidence = 0.5
            
        elif "weather" in prompt_lower:
            verb = "query_weather"
            resource = "route:UNKNOWN"
            params = {}
            confidence = 0.7
            
        else:
            # No pudimos parsearlo
            verb = "unknown_action"
            resource = "unknown"
            params = {"raw_prompt": prompt}
            confidence = 0.1
        
        action = ActionPrimitive(
            verb=verb,
            resource=resource,
            parameters=params,
            domain=domain,
            confidence=confidence
        )
        
        logger.warning(
            "fallback_parser_used",
            verb=verb,
            confidence=confidence,
            prompt=prompt[:50]
        )
        
        return action
