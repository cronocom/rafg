# RAGF: Reflexio Agentic Governance Framework

**Boundary Enforcement as Governance Infrastructure for Agentic AI in Regulated Systems**

[![Paper](https://img.shields.io/badge/Paper-AIES%202026-blue)](papers/RAGF_v2_4.pdf)
[![Status](https://img.shields.io/badge/Status-Under%20Review-orange)]()
[![Tests](https://img.shields.io/badge/Tests-7%2F7%20Passing-success)]()
[![License](https://img.shields.io/badge/License-Apache%202.0-blue)](LICENSE)

## 🎯 Overview

RAGF provides deterministic boundary enforcement for agentic AI systems in regulated domains (aviation, healthcare, finance). Rather than certifying probabilistic AI models, RAGF certifies the **governance harness** that validates actions before execution.

**Key Innovation**: Architectural separation of adaptive reasoning (uncertifiable) from execution authority (certifiable through established methods).

## 📄 Paper

- **Latest Version**: [RAGF v2.4](papers/RAGF_v2_4.pdf) ✨ **NEW**
- **Venue**: AIES 2026 (AAAI/ACM Conference on AI, Ethics, and Society)
- **Paper ID**: #3
- **Submission**: February 16, 2026
- **Updated**: February 17, 2026 (v2.4 with escalation analysis)
- **Status**: Under Review
- **Conference**: October 12-14, 2026 (Malmö, Sweden)

### 🆕 What's New in v2.4

**Section 7.7: Human Escalation Analysis** (addressing reviewer concerns)
- **Inter-operator consistency**: 95.3% agreement (aviation), 94.7% (healthcare)
- **Resolution times**: Mean 187s (aviation), 301s (healthcare); all P95 < 10min
- **Jurisprudence growth**: 40% rule creation (aviation), 34% (healthcare)
- Comparable to expert judgment literature (Cohen's Kappa ≈0.85-0.90)

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

### Escalation Pathway Analysis ✨ NEW

| Domain | Cases | Mean Resolution | Inter-Operator Agreement | New Rules Created |
|--------|-------|-----------------|-------------------------|-------------------|
| Aviation | 100 | 187s (3.1 min) | 95.3% | 40 (40%) |
| Healthcare | 38 | 301s (5.0 min) | 94.7% | 13 (34%) |

**Key Insights**:
- High consistency suggests ontology provides robust decision guidance
- Resolution times maintain operational viability (P95 < 10 min)
- Rule creation rate indicates maturing but not stagnant ontology

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
│  │  Escalation Tracker      │  │  (Resolution analysis) ✨ NEW
│  └──────────────────────────┘  │
└──────┬──────────────────┬───────┘
       │                  │
   ALLOW/DENY         ESCALATE
       │                  │
       ▼                  ▼
  Execute          Human Review
                   (95% consistency)
```

### Components

- **Validation Gate**: Deterministic enforcement with fail-closed semantics
- **Semantic Layer**: Neo4j ontologies grounding actions in domain knowledge
- **Audit Trail**: Cryptographic signatures + append-only ledger (TimescaleDB)
- **Escalation Tracker**: Resolution time & consistency analysis ✨ NEW
- **Escalation Pathway**: Human-in-the-loop with 95% inter-operator agreement

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
│   ├── RAGF_v2_4.pdf         # Latest paper (AIES 2026) ✨
│   ├── RAGF_v2_3.tex         # LaTeX source
│   └── Makefile              # LaTeX build system ✨ NEW
├── gateway/                   # Core validation engine
│   ├── decision_engine.py    # Validation orchestration
│   ├── validators/           # Domain-specific validators
│   └── ontologies/           # Neo4j schema + seed data
├── ragf_core/                 # Extended analysis modules ✨ NEW
│   ├── escalation/           # Resolution tracking & analysis
│   ├── governance/           # Bias detection & proportionality testing
│   └── state/                # Uncertainty-aware state management
├── audit/                     # Cryptographic audit trail
│   ├── ledger.py             # TimescaleDB persistence
│   └── metrics.py            # Performance tracking
├── tests/                     # Test suite (7/7 passing)
│   ├── integration/          # End-to-end validation tests
│   ├── unit/                 # Component tests
│   └── benchmark/            # Performance benchmarks
├── scripts/                   # Automation scripts
│   ├── init_db.sh            # Database initialization
│   ├── seed_ontology.sh      # Ontology seeding
│   └── analyze_escalations.py # Escalation metrics ✨ NEW
├── results/                   # Analysis outputs ✨ NEW
│   └── escalation_analysis/  # Resolution metrics (JSON)
└── docs/                      # Technical documentation
    ├── ARCHITECTURE.md       # System design
    └── DEPLOYMENT_GUIDE.md   # Production deployment
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

# Generate escalation metrics ✨ NEW
python3 scripts/analyze_escalations.py
```

**Test Coverage**: 7/7 passing (100%)
- Unit tests: Core models and validators
- Integration tests: End-to-end validation flow
- Failure mode tests: 3,500 systematic injections across 7 categories
- Benchmarks: Latency and throughput under load
- Escalation analysis: Resolution consistency & jurisprudence growth ✨ NEW

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

- **Threat Model**: Documented in [Section 5](papers/RAGF_v2_4.pdf#page=4)
- **Fail-Closed**: All failures default to DENY (3,500 injections, 0 unintended ALLOW)
- **Audit Trail**: HMAC-SHA256 signed verdicts + append-only ledger
- **Security Audit**: See [docs/audit/SECURITY_AUDIT_v2.0.md](docs/audit/SECURITY_AUDIT_v2.0.md)

## 📚 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Migration to v2](docs/migration/V2_MIGRATION_COMPLETE.md)
- [Escalation Analysis Summary](ESCALATION_ANALYSIS_SUMMARY.md) ✨ NEW

## 🔨 Build System

### Compile Paper Locally
```bash
cd papers/

# Full compilation (4-pass with bibliography)
make

# Quick draft (single pass)
make draft

# Compile and open
make view

# Specific version
make VERSION=camera_ready

# Clean build artifacts
make clean
```

See [papers/Makefile](papers/Makefile) for all options.

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
  address={Malmö, Sweden},
  note={Paper \#3, includes comprehensive escalation pathway analysis}
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

## 📄 Publication Status

**Academic Paper**: RAGF v2.4 submitted to AIES 2026
- **Conference**: AAAI/ACM Conference on AI, Ethics, and Society
- **Paper ID**: #3
- **Initial Submission**: February 16, 2026
- **Updated Version**: February 17, 2026 (v2.4)
- **Status**: ✅ Under Review
- **Expected Notification**: April-May 2026
- **Conference Dates**: October 12-14, 2026 (Malmö, Sweden)

**Latest Paper**: [RAGF_v2_4.pdf](papers/RAGF_v2_4.pdf) (511 KB, 10 pages)

### Version History
- **v2.4** (Feb 17, 2026): Added Section 7.7 (Human Escalation Analysis) with inter-operator consistency metrics, resolution times, and jurisprudence growth patterns
- **v2.3** (Feb 16, 2026): Initial AIES submission with operational sustainability analysis
- **v2.0** (Dec 2025): Complete rewrite with production deployment results

---

**Status**: RAGF v2.4 demonstrates that deterministic boundary enforcement is operationally viable with 95% inter-operator consistency in human escalation pathways, while explicitly documenting governance trade-offs that technical architecture alone cannot resolve.
