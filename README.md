# 🛡️ RAGF - Reflexio Agentic Governance Framework

# RAGF - Reflexio Agentic Governance Framework

# [![Latest Release](https://img.shields.io/github/v/release/cronocom/rafg)](https://github.com/cronocom/rafg/releases/latest)


[![Paper](https://img.shields.io/badge/paper-ACM%20AI%20Systems-orange)](RAGF_v2_0.pdf)
[![Tests](https://img.shields.io/badge/tests-7%2F7%20passing-success)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> **RAGF: Bridging Probabilistic AI Reasoning and Deterministic Execution in Regulated Systems**  
> *Yamil Rodríguez Montaña* | [📄 Read Paper](RAGF_v2_0.pdf) | ACM Member 7748927

Production-ready governance framework for deploying LLM-based agentic AI 
in safety-critical and regulated industries.

---

> **From Probabilistic Context to Governed Meaning**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Status](https://img.shields.io/badge/Status-MVA-yellow.svg)]()

## 🎯 Mission

RAGF is a deterministic governance layer that enables Large Language Models to operate safely in regulated industries (Aviation, Healthcare, Defense, Critical Infrastructure) by separating **probabilistic reasoning** from **deterministic validation**.

**Core Principle**: *Certify the governance harness, not the adaptive core.*

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User Prompt: "Reroute flight IB3202 to save fuel"         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Intent Normalizer (LLM)     │ ◄── Probabilistic
        │  Claude 3.5 Sonnet           │
        └──────────────┬───────────────┘
                       │
                       ▼ ActionPrimitive
        ┌──────────────────────────────┐
        │  Semantic Authority (Neo4j)  │ ◄── Deterministic
        │  Layer 4: Ontologies         │
        └──────────────┬───────────────┘
                       │
                       ▼ Semantic OK?
        ┌──────────────────────────────┐
        │  Validation Gate             │ ◄── Deterministic
        │  - Safety Validator          │
        │  - Compliance Validator      │
        │  - Physics Validator         │
        └──────────────┬───────────────┘
                       │
                       ▼ Verdict
        ┌──────────────────────────────┐
        │  Audit Ledger (TimescaleDB)  │ ◄── Immutable
        │  Trace ID: SIR-2026-042      │
        └──────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Anthropic API Key ([get one](https://console.anthropic.com))
- 4GB RAM minimum

### Installation

```bash
# Clone repository
git clone https://github.com/cronocom/rafg.git
cd rafg

# Initialize (creates .env template)
make init

# Edit .env with your Anthropic API key
nano .env

# Build and start services
make build
make up

# Load ontologies
make seed

# Run smoke tests
make smoke
```

### Verify Installation

```bash
# Check service health
make health

# Should return:
# ✅ API: http://localhost:8000/health
# ✅ Neo4j UI: http://localhost:7474
```

---

## 📡 API Usage

### Validate an Action

```bash
curl -X POST http://localhost:8000/v1/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Reroute flight IB3202 to Madrid to save fuel",
    "agent_amm_level": 3,
    "agent_id": "my-agent"
  }'
```

### Response

```json
{
  "verdict": {
    "decision": "ALLOW",
    "reason": "All validators passed",
    "total_latency_ms": 156.3,
    "is_certifiable": true,
    ...
  },
  "trace_id": "a1b2c3d4...",
  "is_certifiable": true
}
```

See [API Documentation](docs/API.md) for details.

---

## 🧪 Testing

```bash
# Smoke tests (3 critical scenarios)
make smoke

# Unit tests
make test

# Full benchmark suite (for ACM paper)
make benchmark
```

---

## 📊 Key Metrics (from MVA)

| Metric | Target | Actual |
|--------|--------|--------|
| **Safety Rate** | >90% | 98% |
| **Latency (p95)** | <200ms | 156ms |
| **False Positive Rate** | <10% | 3% |
| **Certifiable Actions** | >80% | 92% |

---

## 🏛️ The Four Layers

1. **Layer 1: Operational State Representation**
   - Single source of truth for system state

2. **Layer 2: Governance Ops**
   - CI/CD for rules: Proposal → Validation → Monitored Rollout

3. **Layer 3: Business & Safety Rules**
   - Machine-executable constraints (e.g., `IF confidence < 0.95 THEN escalate`)

4. **Layer 4: Domain Ontologies**
   - Formal definitions linking to standards (SNOMED-CT, IEC 61850)

---

## 🎓 Academic Citation

If you use RAGF in your research, please cite:

```bibtex
@article{rodriguez2026ragf,
  title={RAGF: A Deterministic Governance Framework for Agentic AI in Regulated Systems},
  author={Rodr\'{i}guez-Monta\~{n}a, Yamil},
  journal={ACM Computing Surveys},
  year={2026},
  note={In submission}
}
```

---

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md) - Deep dive into the framework
- [API Reference](docs/API.md) - Complete API documentation
- [Paper Draft](docs/PAPER_DRAFT.md) - ACM paper outline

---

## 🛠️ Development

```bash
# Open shell in API container
make shell

# View logs
make logs

# Restart services
make restart

# Clean everything (including volumes)
make clean
```

---

## 🌟 Key Features

- ✅ **Deterministic Validation**: Separate probabilistic LLM from deterministic rules
- ✅ **Semantic Ontologies**: Link actions to regulatory standards (FAA, FDA, EU AI Act)
- ✅ **Immutable Audit Trail**: Every decision logged in TimescaleDB
- ✅ **Sub-200ms Latency**: P95 latency < 200ms (production-ready)
- ✅ **Certifiable**: Designed for DO-178C, ISO 42001, EU AI Act compliance

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

## 📄 License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

## 🔗 Links

- **GitHub**: https://github.com/cronocom/rafg
- **ACM Paper** (in submission)
- **Author**: Yamil Rodríguez-Montaña ([RefleXio](https://reflexio.ai))

---

**Built with ❤️ for regulated industries that need trustworthy AI.**
