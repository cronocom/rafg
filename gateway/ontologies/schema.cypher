// ═══════════════════════════════════════════════════════════
// RAGF Neo4j Schema
// Layer 4: Domain Ontologies & Taxonomies
// ═══════════════════════════════════════════════════════════

// Limpiar base de datos (SOLO PARA MVA - NO EN PRODUCCIÓN)
MATCH (n) DETACH DELETE n;

// ═══════════════════════════════════════════════════════════
// CONSTRAINTS & INDEXES
// ═══════════════════════════════════════════════════════════

// Ontologies
CREATE CONSTRAINT ontology_domain_version IF NOT EXISTS
FOR (o:Ontology) REQUIRE (o.domain, o.version) IS UNIQUE;

// Actions
CREATE CONSTRAINT action_id IF NOT EXISTS
FOR (a:Action) REQUIRE a.id IS UNIQUE;

CREATE INDEX action_verb IF NOT EXISTS
FOR (a:Action) ON (a.verb);

// Regulations
CREATE CONSTRAINT regulation_id IF NOT EXISTS
FOR (r:Regulation) REQUIRE r.id IS UNIQUE;

// Validators
CREATE CONSTRAINT validator_name IF NOT EXISTS
FOR (v:Validator) REQUIRE v.name IS UNIQUE;

// AMM Levels
CREATE CONSTRAINT amm_level IF NOT EXISTS
FOR (l:MaturityLevel) REQUIRE l.value IS UNIQUE;

// Agents
CREATE CONSTRAINT agent_id IF NOT EXISTS
FOR (a:Agent) REQUIRE a.id IS UNIQUE;

// Roles
CREATE CONSTRAINT role_name IF NOT EXISTS
FOR (r:Role) REQUIRE r.name IS UNIQUE;

// ═══════════════════════════════════════════════════════════
// CORE STRUCTURE: AMM Levels (1-5)
// ═══════════════════════════════════════════════════════════

CREATE (l1:MaturityLevel {
    value: 1,
    name: 'Passive Knowledge',
    description: 'Read-only queries, no execution',
    risk_level: 'VERY_LOW'
});

CREATE (l2:MaturityLevel {
    value: 2,
    name: 'Human Teaming',
    description: 'AI proposes, human executes',
    risk_level: 'LOW'
});

CREATE (l3:MaturityLevel {
    value: 3,
    name: 'Actionable Agency',
    description: 'AI executes with validation gate',
    risk_level: 'CRITICAL'
});

CREATE (l4:MaturityLevel {
    value: 4,
    name: 'Autonomous Orchestration',
    description: 'AI coordinates multiple sub-agents',
    risk_level: 'VERY_HIGH'
});

CREATE (l5:MaturityLevel {
    value: 5,
    name: 'Full Systemic Autonomy',
    description: 'Self-regulating system',
    risk_level: 'EXTREME'
});

// ═══════════════════════════════════════════════════════════
// LOGGING
// ═══════════════════════════════════════════════════════════

RETURN 'Schema created successfully' AS status;
