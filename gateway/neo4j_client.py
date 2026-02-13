"""
═══════════════════════════════════════════════════════════
RAGF Neo4j Client
Layer 2 & 4: Semantic Authority + Governance Ops
═══════════════════════════════════════════════════════════

Este módulo gestiona la "Autoridad Semántica":
- Valida si una acción existe en la ontología (Layer 4)
- Verifica permisos según AMM level (Layer 2)
- Devuelve los validadores requeridos para la acción
"""

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import Optional, List
from shared.models import ActionPrimitive, SemanticVerdict, AMMLevel
from shared.exceptions import SemanticDriftError, AMMViolationError, OntologyNotFoundError

logger = structlog.get_logger()


class Neo4jClient:
    """Cliente asíncrono para Neo4j con queries de gobernanza"""
    
    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[AsyncDriver] = None
    
    async def connect(self):
        """Inicializar conexión"""
        self.driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )
        logger.info("neo4j_connected", uri=self.uri)
    
    async def close(self):
        """Cerrar conexión"""
        if self.driver:
            await self.driver.close()
            logger.info("neo4j_disconnected")
    
    async def validate_semantic_authority(
        self,
        action: ActionPrimitive,
        agent_amm_level: AMMLevel
    ) -> SemanticVerdict:
        """
        QUERY CRÍTICO: Valida si la acción está gobernada.
        
        Pasos:
        1. ¿Existe el verbo en la ontología del dominio?
        2. ¿El nivel AMM del agente es suficiente?
        3. Calcular cobertura semántica
        
        Returns:
            SemanticVerdict con decisión ALLOW/DENY
        """
        query = """
        // 1. Buscar ontología activa para el dominio
        MATCH (ont:Ontology {domain: $domain, active: true})
        
        // 2. Buscar acción por verbo
        OPTIONAL MATCH (ont)-[:DEFINES]->(a:Action {verb: $verb})
        
        // 3. Verificar nivel AMM requerido
        OPTIONAL MATCH (a)-[:REQUIRES_AMM]->(required_level:MaturityLevel)
        
        // 4. Obtener nivel AMM del agente
        MATCH (agent_level:MaturityLevel {value: $agent_amm_level})
        
        RETURN 
            ont.version AS ontology_version,
            a.verb AS action_verb,
            a.requires_amm AS required_amm,
            required_level.value AS required_amm_value,
            agent_level.value AS agent_amm_value,
            CASE 
                WHEN a IS NULL THEN false
                ELSE true
            END AS ontology_match,
            CASE
                WHEN a IS NULL THEN false
                WHEN required_level.value <= agent_level.value THEN true
                ELSE false
            END AS amm_authorized
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, {
                "domain": action.domain,
                "verb": action.verb,
                "agent_amm_level": int(agent_amm_level)
            })
            
            record = await result.single()
            
            if not record:
                raise OntologyNotFoundError(action.domain)
            
            ontology_match = record["ontology_match"]
            amm_authorized = record["amm_authorized"]
            
            # Calcular cobertura semántica
            coverage = 0.0
            if ontology_match:
                coverage += 0.5  # Verbo existe
                if amm_authorized:
                    coverage += 0.5  # AMM suficiente
            
            # Determinar decisión
            if not ontology_match:
                decision = "DENY"
                reason = f"Verb '{action.verb}' not found in ontology '{action.domain}' v{record['ontology_version']}"
            elif not amm_authorized:
                decision = "DENY"
                reason = f"Action requires AMM Level {record['required_amm_value']}, but agent is Level {record['agent_amm_value']}"
            else:
                decision = "ALLOW"
                reason = f"Action authorized: {action.verb} @ AMM L{agent_amm_level}"
            
            verdict = SemanticVerdict(
                decision=decision,
                reason=reason,
                ontology_match=ontology_match,
                amm_authorized=amm_authorized,
                coverage=coverage
            )
            
            logger.info(
                "semantic_validation_complete",
                verb=action.verb,
                decision=decision,
                coverage=coverage
            )
            
            return verdict
    
    async def get_required_validators(
        self,
        action: ActionPrimitive
    ) -> List[str]:
        """
        Obtiene la lista de validadores que deben ejecutarse para esta acción.
        
        Query: Action -[:REQUIRES_VALIDATOR]-> Validator
        
        Returns:
            Lista de nombres de validators (ej: ['FuelReserveValidator', 'CrewRestValidator'])
        """
        query = """
        MATCH (ont:Ontology {domain: $domain, active: true})
        MATCH (ont)-[:DEFINES]->(a:Action {verb: $verb})
        MATCH (a)-[:REQUIRES_VALIDATOR]->(v:Validator)
        RETURN v.name AS validator_name, v.implementation AS implementation
        ORDER BY v.name
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, {
                "domain": action.domain,
                "verb": action.verb
            })
            
            validators = []
            async for record in result:
                validators.append(record["validator_name"])
            
            logger.info(
                "validators_retrieved",
                verb=action.verb,
                validator_count=len(validators),
                validators=validators
            )
            
            return validators
    
    async def get_action_regulations(
        self,
        action: ActionPrimitive
    ) -> List[dict]:
        """
        Obtiene las regulaciones que gobiernan esta acción.
        Útil para generar reportes de auditoría detallados.
        
        Returns:
            Lista de regulaciones con constraint details
        """
        query = """
        MATCH (a:Action {verb: $verb, domain: $domain})-[g:GOVERNED_BY]->(r:Regulation)
        RETURN 
            r.id AS regulation_id,
            r.title AS title,
            r.authority AS authority,
            g.constraint_type AS constraint_type,
            g.rule_description AS description,
            g.machine_readable AS machine_rule
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, {
                "verb": action.verb,
                "domain": action.domain
            })
            
            regulations = []
            async for record in result:
                regulations.append({
                    "regulation_id": record["regulation_id"],
                    "title": record["title"],
                    "authority": record["authority"],
                    "constraint_type": record["constraint_type"],
                    "description": record["description"],
                    "machine_rule": record["machine_readable"]
                })
            
            return regulations
