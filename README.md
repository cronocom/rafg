# RAGF: Reflexio Agentic Governance Framework

**Boundary Enforcement as Governance Infrastructure for Agentic AI in Regulated Systems**

[![Paper](https://img.shields.io/badge/Paper-AIES%202026-blue)](papers/RAGF_v2_3.pdf)
[![Status](https://img.shields.io/badge/Status-Submission%20Ready-green)]()
[![Tests](https://img.shields.io/badge/Tests-7%2F7%20Passing-success)]()
[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](LICENSE)

## 🎯 Overview

RAGF provides deterministic boundary enforcement for agentic AI systems in regulated domains (aviation, healthcare, finance). Rather than certifying probabilistic AI models, RAGF certifies the **governance harness** that validates actions before execution.

**Key Innovation**: Architectural separation of adaptive reasoning (uncertifiable) from execution authority (certifiable through established methods).

## 📄 Paper

- **Latest Version**: [RAGF v2.3](papers/RAGF_v2_3.pdf) (FINAL - Submission Ready)
- **Venue**: AIES 2026 (AAAI/ACM Conference on AI, Ethics, and Society)
- **Submission Deadline**: May 21, 2026
- **Conference**: October 12-14, 2026 (Malmö, Sweden)
- **Status**: 9.5/10 quality, 9 pages, ready for submission

### Key Results

| Metric | Aviation | Healthcare | Total |
|--------|----------|------------|-------|
| **Actions Evaluated** | 12,847 | 1,893 | **14,740** |
| **ALLOW** | 11,203 (87.2%) | 1,612 (85.2%) | 12,815 |
| **DENY** | 1,544 (12.0%) | 243 (12.8%) | 1,787 |
| **ESCALATE** | 100 (0.8%) | 38 (2.0%) | 138 |
| **Unsafe Prevented** | 37 | 4 | **41** |
| **False Positives** | 0 | 0 | **0** |

**Performance**: Sub-30ms governance latency at p95 (28.1ms)  
**Reliability**: Fail-closed across 7 failure categories (3,500 injections, 0 unintended ALLOW)

### Critical Contribution: Section 7.6 Operational Sustainability

**Ontology Maintenance Burden** (unique in AI governance literature):
- **Aviation**: 23 updates over 90 days (stable regulatory environment)
- **Healthcare**: 47 updates over 60 days (volatile domain with frequent formulary changes)
- **Key Insight**: "Cost may approach or exceed operational savings in high-volatility domains"

**State Integration Complexity**:
- Aviation: 3 state sources (crew scheduling, flight planning, maintenance) with 50ms timeout
- Healthcare: HL7 FHIR integration with eventual consistency challenges

**Single Point of Trust**: Explicit acknowledgment that Validation Gate is root of trust; compromise would subvert governance silently.

## 🏗️ Architecture
```
┌─────────────┐
│   LLM Agent │  (Proposes actions)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────┐
│    Validation Gate              │
│  ┌──────────────────────────┐  │
│  │  Semantic Authority      │  │  (Neo4j ontologies)
│  │  Safety Validators       │  │  (Domain-specific rules)
│  │  Cryptographic Audit     │  │  (HMAC-SHA256 + TimescaleDB)
│  └──────────────────────────┘  │
└──────┬──────────────────┬───────┘
       │                  │
   ALLOW/DENY         ESCALATE
       │                  │
       ▼                  ▼
  Execute          Human Review
```

### Components

- **Validation Gate**: Deterministic enforcement with fail-closed semantics
- **Semantic Layer**: Neo4j ontologies grounding actions in domain knowledge
- **Audit Trail**: Cryptographic signatures + append-only ledger (TimescaleDB)
- **Escalation**: Human-in-the-loop for ambiguous cases

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Neo4j 5.x
- TimescaleDB (PostgreSQL extension)

### Installation
```bash
# Clone repository
git clone https://github.com/cronocom/rafg.git
cd rafg

# Start infrastructure
docker-compose up -d

# Initialize ontologies
./scripts/init_db.sh
./scripts/seed_ontology.sh

# Run tests
make test

# Start gateway
make run
```

### Example Usage
```python
from gateway.main import ValidationGateway

gateway = ValidationGateway()

# Propose an action
action = {
    "verb": "reroute_flight",
    "resource": "IB3202",
    "params": {"new_route": "MAD-BCN", "fuel_reserve": 45}
}

# Validate before execution
verdict = await gateway.validate(action)

if verdict.decision == "ALLOW":
    execute_action(action)
elif verdict.decision == "ESCALATE":
    route_to_human_review(action, verdict.reason)
else:  # DENY
    log_denial(action, verdict.reason)
```

## 📊 Project Structure
```
rafg/
├── papers/                    # Academic publications
│   ├── RAGF_v2_3.pdf         # Final paper (AIES 2026)
│   └── RAGF_v2_3.tex         # LaTeX source
├── gateway/                   # Core validation engine
│   ├── decision_engine.py    # Validation orchestration
│   ├── validators/           # Domain-specific validators
│   └── ontologies/           # Neo4j schema + seed data
├── audit/                     # Cryptographic audit trail
│   ├── ledger.py             # TimescaleDB persistence
│   └── metrics.py            # Performance tracking
├── tests/                     # Test suite (7/7 passing)
│   ├── integration/          # End-to-end validation tests
│   ├── unit/                 # Component tests
│   └── benchmark/            # Performance benchmarks
├── docs/                      # Technical documentation
│   ├── ARCHITECTURE.md       # System design
│   ├── DEPLOYMENT_GUIDE.md   # Production deployment
│   └── audit/                # Security audits
└── scripts/                   # Automation scripts
    ├── init_db.sh            # Database initialization
    └── seed_ontology.sh      # Ontology seeding
```

## 🧪 Testing
```bash
# Run full test suite
make test

# Run integration tests only
pytest tests/integration/ -v

# Run failure injection tests
./run_failure_tests.sh

# Run benchmarks
pytest tests/benchmark/ -v
```

**Test Coverage**: 7/7 passing (100%)
- Unit tests: Core models and validators
- Integration tests: End-to-end validation flow
- Failure mode tests: 3,500 systematic injections across 7 categories
- Benchmarks: Latency and throughput under load

## 📈 Performance

| Metric | p50 | p95 | p99 |
|--------|-----|-----|-----|
| Semantic Layer | 4.2ms | 6.8ms | 9.1ms |
| Validation Gate | 8.7ms | 12.4ms | 14.3ms |
| Signature | 0.5ms | 0.7ms | 0.9ms |
| Ledger Write | 4.9ms | 8.2ms | 8.9ms |
| **Total Governance** | **18.3ms** | **28.1ms** | **33.2ms** |

Measured under sustained 50 req/s load over 90-day aviation deployment.

## 🔒 Security

- **Threat Model**: Documented in [Section 5](papers/RAGF_v2_3.pdf#page=4)
- **Fail-Closed**: All failures default to DENY (3,500 injections, 0 unintended ALLOW)
- **Audit Trail**: HMAC-SHA256 signed verdicts + append-only ledger
- **Security Audit**: See [docs/audit/SECURITY_AUDIT_v2.0.md](docs/audit/SECURITY_AUDIT_v2.0.md)

## 📚 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Migration to v2](docs/migration/V2_MIGRATION_COMPLETE.md)

## 🤝 Contributing

This is an academic research project. Contributions are welcome for:
- Additional domain validators (energy, finance, etc.)
- Ontology extensions
- Performance optimizations
- Documentation improvements

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📖 Citation
```bibtex
@inproceedings{rodriguez2026ragf,
  title={RAGF: Boundary Enforcement as Governance Infrastructure 
         for Agentic AI in Regulated Systems},
  author={Rodríguez-Montaña, Yamil},
  booktitle={AAAI/ACM Conference on AI, Ethics, and Society (AIES)},
  year={2026},
  address={Malmö, Sweden}
}
```

## 📧 Contact

**Yamil Rodríguez-Montaña**  
Founder & Managing Partner  
Cronodata / Reflexio  
📧 yrm@reflexio.es  
🌐 [reflexio.es](https://reflexio.es)

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

---

**Status**: RAGF v2.3 is submission-ready for AIES 2026. The paper demonstrates that deterministic boundary enforcement is operationally viable while explicitly documenting governance trade-offs that technical architecture alone cannot resolve.
