"""
RAGF Benchmark — PSD2 Ontology Definition
Verbos, regulaciones y constraints para el dominio fintech/PSD2
Prefijo BM_ en labels para separar del espacio de la demo
"""

REGULATIONS = [
    {"code": "PSD2-ART97",  "title": "Strong Customer Authentication",    "authority": "EBA"},
    {"code": "PSD2-ART67",  "title": "Access to Payment Account Data",    "authority": "EBA"},
    {"code": "PSD2-ART98",  "title": "SCA Exemptions",                    "authority": "EBA"},
    {"code": "AML5-ART18",  "title": "Enhanced Due Diligence",            "authority": "FATF"},
    {"code": "AML5-ART47",  "title": "Account Freezing Powers",           "authority": "FATF"},
    {"code": "GDPR-ART20",  "title": "Right to Data Portability",         "authority": "EDPB"},
    {"code": "EBA-GL-2022", "title": "EBA Guidelines on SCA and CSC",     "authority": "EBA"},
]

CONSTRAINTS = [
    {"id": "c1", "predicate": "amount_eur <= 15000",      "unit": "EUR"},
    {"id": "c2", "predicate": "sca_verified == True",     "unit": "boolean"},
    {"id": "c3", "predicate": "amount_eur <= 100000",     "unit": "EUR"},
    {"id": "c4", "predicate": "risk_score <= 0.3",        "unit": "float"},
    {"id": "c5", "predicate": "operator_confirmed == True","unit": "boolean"},
]

VERBS = [
    # ── 1-hop: verbo → dominio (query simple) ──────────────────────────────
    {
        "name": "query_account_balance",
        "description": "Read account balance",
        "min_amm_level": 1,
        "regulations": ["PSD2-ART67"],
        "constraints": [],
    },
    {
        "name": "list_transactions",
        "description": "List transaction history",
        "min_amm_level": 1,
        "regulations": ["PSD2-ART67"],
        "constraints": [],
    },
    {
        "name": "get_payment_status",
        "description": "Query status of a payment",
        "min_amm_level": 1,
        "regulations": ["PSD2-ART67"],
        "constraints": [],
    },
    # ── 2-hop: verbo → regulación (query media) ────────────────────────────
    {
        "name": "initiate_payment",
        "description": "Initiate a SEPA payment",
        "min_amm_level": 2,
        "regulations": ["PSD2-ART97"],
        "constraints": ["c1", "c2"],
    },
    {
        "name": "approve_payment",
        "description": "Approve a pending payment",
        "min_amm_level": 3,
        "regulations": ["PSD2-ART97"],
        "constraints": ["c2"],
    },
    {
        "name": "cancel_payment",
        "description": "Cancel a pending payment",
        "min_amm_level": 3,
        "regulations": ["PSD2-ART97"],
        "constraints": [],
    },
    {
        "name": "initiate_refund",
        "description": "Initiate a payment refund",
        "min_amm_level": 3,
        "regulations": ["PSD2-ART97"],
        "constraints": ["c1"],
    },
    {
        "name": "export_transaction_history",
        "description": "Export full transaction history",
        "min_amm_level": 2,
        "regulations": ["PSD2-ART67", "GDPR-ART20"],
        "constraints": ["c5"],
    },
    {
        "name": "flag_suspicious_transaction",
        "description": "Flag transaction for AML review",
        "min_amm_level": 2,
        "regulations": ["AML5-ART18"],
        "constraints": ["c4"],
    },
    {
        "name": "request_sca_exemption",
        "description": "Request SCA exemption for low-risk tx",
        "min_amm_level": 3,
        "regulations": ["PSD2-ART98"],
        "constraints": ["c4"],
    },
    # ── 3-hop: verbo → múltiples regulaciones + constraints ────────────────
    {
        "name": "approve_refund",
        "description": "Approve a refund request",
        "min_amm_level": 4,
        "regulations": ["PSD2-ART97", "EBA-GL-2022"],
        "constraints": ["c1", "c2"],
    },
    {
        "name": "approve_high_value_transfer",
        "description": "Approve transfer over 15k EUR",
        "min_amm_level": 4,
        "regulations": ["PSD2-ART97", "AML5-ART18"],
        "constraints": ["c3", "c2", "c4"],
    },
    {
        "name": "escalate_aml_alert",
        "description": "Escalate AML alert to compliance",
        "min_amm_level": 3,
        "regulations": ["AML5-ART18", "EBA-GL-2022"],
        "constraints": ["c5"],
    },
    {
        "name": "freeze_account",
        "description": "Freeze account pending investigation",
        "min_amm_level": 4,
        "regulations": ["AML5-ART47", "AML5-ART18"],
        "constraints": ["c5"],
    },
    {
        "name": "grant_sca_exemption",
        "description": "Grant SCA exemption approval",
        "min_amm_level": 5,
        "regulations": ["PSD2-ART98", "EBA-GL-2022"],
        "constraints": ["c4", "c2"],
    },
    {
        "name": "override_fraud_flag",
        "description": "Override AML fraud flag",
        "min_amm_level": 5,
        "regulations": ["AML5-ART18", "AML5-ART47", "EBA-GL-2022"],
        "constraints": ["c5", "c4"],
    },
    {
        "name": "unfreeze_account",
        "description": "Unfreeze account after investigation",
        "min_amm_level": 5,
        "regulations": ["AML5-ART47", "EBA-GL-2022"],
        "constraints": ["c5", "c2"],
    },
]
