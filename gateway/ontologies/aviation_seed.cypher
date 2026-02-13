// ═══════════════════════════════════════════════════════════
// RAGF Aviation Ontology Seed
// Domain: Aviation (FAA Regulations)
// Version: 1.0.0
// Certification Target: DO-178C
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
// 1. CREATE ONTOLOGY NODE
// ═══════════════════════════════════════════════════════════

CREATE (ont:Ontology {
    domain: 'aviation',
    version: '1.0.0',
    valid_from: datetime(),
    certification_ref: 'DO-178C-2024',
    active: true,
    description: 'Federal Aviation Administration operational constraints'
});

// ═══════════════════════════════════════════════════════════
// 2. CREATE REGULATIONS (FAA 14 CFR)
// ═══════════════════════════════════════════════════════════

CREATE (reg_fuel:Regulation {
    id: 'FAA-14-CFR-91.151',
    title: 'Fuel requirements for flight in VFR conditions',
    authority: 'Federal Aviation Administration',
    version: '2024-01',
    url: 'https://www.ecfr.gov/current/title-14/section-91.151',
    summary: 'No person may begin a flight in an airplane under VFR conditions unless there is enough fuel to fly to the first point of intended landing and, assuming normal cruising speed, to fly after that for at least 30 minutes (day) or 45 minutes (night).'
});

CREATE (reg_crew_rest:Regulation {
    id: 'FAA-14-CFR-121.471',
    title: 'Flight time limitations and rest requirements',
    authority: 'Federal Aviation Administration',
    version: '2024-01',
    url: 'https://www.ecfr.gov/current/title-14/section-121.471',
    summary: 'Maximum flight duty period: 9 hours (augmented crew may extend). Minimum rest period: 10 consecutive hours.'
});

CREATE (reg_airspace:Regulation {
    id: 'FAA-14-CFR-91.119',
    title: 'Minimum safe altitudes: General',
    authority: 'Federal Aviation Administration',
    version: '2024-01',
    url: 'https://www.ecfr.gov/current/title-14/section-91.119',
    summary: 'Except when necessary for takeoff or landing, no person may operate an aircraft below: (a) Over congested areas: 1,000 feet above highest obstacle within 2,000 feet horizontal radius.'
});

CREATE (reg_maintenance:Regulation {
    id: 'FAA-14-CFR-91.405',
    title: 'Maintenance required',
    authority: 'Federal Aviation Administration',
    version: '2024-01',
    url: 'https://www.ecfr.gov/current/title-14/section-91.405',
    summary: 'Each owner or operator shall have that aircraft inspected as prescribed and shall between required inspections have defects repaired.'
});

// ═══════════════════════════════════════════════════════════
// 3. CREATE ACTIONS (Governed Verbs)
// ═══════════════════════════════════════════════════════════

// L3: Actionable Agency Level
CREATE (act_reroute:Action {
    id: 'aviation_reroute_flight',
    verb: 'reroute_flight',
    domain: 'aviation',
    requires_amm: 3,
    description: 'Modify flight path to alternate destination or waypoint',
    risk_category: 'OPERATIONAL',
    requires_validation: true
});

CREATE (act_adjust_altitude:Action {
    id: 'aviation_adjust_altitude',
    verb: 'adjust_altitude',
    domain: 'aviation',
    requires_amm: 3,
    description: 'Change cruising altitude',
    risk_category: 'SAFETY',
    requires_validation: true
});

CREATE (act_schedule_maintenance:Action {
    id: 'aviation_schedule_maintenance',
    verb: 'schedule_maintenance',
    domain: 'aviation',
    requires_amm: 3,
    description: 'Schedule aircraft for maintenance inspection',
    risk_category: 'OPERATIONAL',
    requires_validation: true
});

// L2: Human Teaming Level
CREATE (act_query_weather:Action {
    id: 'aviation_query_weather',
    verb: 'query_weather',
    domain: 'aviation',
    requires_amm: 2,
    description: 'Retrieve weather data for route planning',
    risk_category: 'INFORMATIONAL',
    requires_validation: false
});

CREATE (act_calculate_fuel:Action {
    id: 'aviation_calculate_fuel',
    verb: 'calculate_fuel_requirement',
    domain: 'aviation',
    requires_amm: 2,
    description: 'Compute fuel needs for proposed route',
    risk_category: 'INFORMATIONAL',
    requires_validation: false
});

// L4: Autonomous Orchestration Level
CREATE (act_optimize_fleet:Action {
    id: 'aviation_optimize_fleet',
    verb: 'optimize_fleet_allocation',
    domain: 'aviation',
    requires_amm: 4,
    description: 'Coordinate multiple aircraft assignments across routes',
    risk_category: 'STRATEGIC',
    requires_validation: true
});

// ═══════════════════════════════════════════════════════════
// 4. CREATE VALIDATORS
// ═══════════════════════════════════════════════════════════

CREATE (val_fuel:Validator {
    name: 'FuelReserveValidator',
    implementation: 'validators.safety_validator.FuelReserveValidator',
    deterministic: true,
    description: 'Ensures fuel reserves meet FAA minimums',
    timeout_ms: 50
});

CREATE (val_crew:Validator {
    name: 'CrewRestValidator',
    implementation: 'validators.safety_validator.CrewRestValidator',
    deterministic: true,
    description: 'Validates crew duty time and rest requirements',
    timeout_ms: 50
});

CREATE (val_airspace:Validator {
    name: 'AirspaceValidator',
    implementation: 'validators.safety_validator.AirspaceValidator',
    deterministic: true,
    description: 'Checks altitude constraints and airspace restrictions',
    timeout_ms: 50
});

// ═══════════════════════════════════════════════════════════
// 5. CREATE RELATIONSHIPS
// ═══════════════════════════════════════════════════════════

// Ontology defines Actions
MATCH (ont:Ontology {domain: 'aviation'})
MATCH (a:Action {domain: 'aviation'})
CREATE (ont)-[:DEFINES]->(a);

// Actions governed by Regulations
MATCH (act_reroute:Action {id: 'aviation_reroute_flight'})
MATCH (reg_fuel:Regulation {id: 'FAA-14-CFR-91.151'})
CREATE (act_reroute)-[:GOVERNED_BY {
    constraint_type: 'SAFETY',
    rule_description: 'Reroute must not reduce fuel below VFR minimums',
    machine_readable: 'fuel_remaining >= (new_distance * burn_rate) + 30min_reserve'
}]->(reg_fuel);

MATCH (act_reroute:Action {id: 'aviation_reroute_flight'})
MATCH (reg_crew:Regulation {id: 'FAA-14-CFR-121.471'})
CREATE (act_reroute)-[:GOVERNED_BY {
    constraint_type: 'OPERATIONAL',
    rule_description: 'Reroute must not extend crew duty beyond limits',
    machine_readable: 'new_flight_duration + current_duty_time <= 540min'
}]->(reg_crew);

MATCH (act_adjust:Action {id: 'aviation_adjust_altitude'})
MATCH (reg_airspace:Regulation {id: 'FAA-14-CFR-91.119'})
CREATE (act_adjust)-[:GOVERNED_BY {
    constraint_type: 'SAFETY',
    rule_description: 'New altitude must respect minimum safe altitudes',
    machine_readable: 'new_altitude >= min_safe_altitude[terrain_type]'
}]->(reg_airspace);

// Regulations enforced by Validators
MATCH (reg_fuel:Regulation {id: 'FAA-14-CFR-91.151'})
MATCH (val_fuel:Validator {name: 'FuelReserveValidator'})
CREATE (reg_fuel)-[:ENFORCED_BY]->(val_fuel);

MATCH (reg_crew:Regulation {id: 'FAA-14-CFR-121.471'})
MATCH (val_crew:Validator {name: 'CrewRestValidator'})
CREATE (reg_crew)-[:ENFORCED_BY]->(val_crew);

MATCH (reg_airspace:Regulation {id: 'FAA-14-CFR-91.119'})
MATCH (val_airspace:Validator {name: 'AirspaceValidator'})
CREATE (reg_airspace)-[:ENFORCED_BY]->(val_airspace);

// Actions require Validators
MATCH (act_reroute:Action {id: 'aviation_reroute_flight'})
MATCH (val_fuel:Validator {name: 'FuelReserveValidator'})
CREATE (act_reroute)-[:REQUIRES_VALIDATOR]->(val_fuel);

MATCH (act_reroute:Action {id: 'aviation_reroute_flight'})
MATCH (val_crew:Validator {name: 'CrewRestValidator'})
CREATE (act_reroute)-[:REQUIRES_VALIDATOR]->(val_crew);

MATCH (act_adjust:Action {id: 'aviation_adjust_altitude'})
MATCH (val_airspace:Validator {name: 'AirspaceValidator'})
CREATE (act_adjust)-[:REQUIRES_VALIDATOR]->(val_airspace);

// Actions require AMM Level
MATCH (act:Action {requires_amm: 3})
MATCH (l:MaturityLevel {value: 3})
CREATE (act)-[:REQUIRES_AMM]->(l);

MATCH (act:Action {requires_amm: 2})
MATCH (l:MaturityLevel {value: 2})
CREATE (act)-[:REQUIRES_AMM]->(l);

MATCH (act:Action {requires_amm: 4})
MATCH (l:MaturityLevel {value: 4})
CREATE (act)-[:REQUIRES_AMM]->(l);

// ═══════════════════════════════════════════════════════════
// 6. VERIFICATION QUERIES
// ═══════════════════════════════════════════════════════════

// Contar acciones por nivel AMM
MATCH (a:Action)-[:REQUIRES_AMM]->(l:MaturityLevel)
RETURN l.value AS AMM_Level, l.name AS Level_Name, count(a) AS Action_Count
ORDER BY l.value;

// Mostrar cadena de gobernanza para reroute_flight
MATCH path = (a:Action {verb: 'reroute_flight'})-[:GOVERNED_BY]->(r:Regulation)-[:ENFORCED_BY]->(v:Validator)
RETURN a.verb AS Action, r.id AS Regulation, v.name AS Validator;

RETURN 'Aviation ontology seeded successfully' AS status;
