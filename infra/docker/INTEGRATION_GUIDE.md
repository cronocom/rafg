# RAGF Integration Guide

## 🔌 How to Integrate RAGF with Your AI Agent

### The Question Everyone Asks

> "Do I need to move my agent code? Connect to your API? Or can I run RAGF in my own infrastructure?"

**Answer:** You choose! RAGF offers **3 deployment models** to fit your needs.

---

## 🎯 Deployment Models

### 1️⃣ SaaS API (Recommended for Most)

**What it is:** Your agent calls our hosted API for validation.

**Architecture:**
```
Your Agent → HTTPS → RAGF API (Agent Save Cloud) → Validation Response
                              ↓
                      (PSD2, AML, MiCA validators)
```

**Integration:**
```python
import requests

# Your agent proposes an action
action = {
    "amount": 350.0,
    "currency": "EUR",
    "sca_completed": False,
    "beneficiary_iban": "ES91..."
}

# Call RAGF API
response = requests.post(
    "https://api.agentsave.one/v1/validate",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"action": action, "domain": "fintech"}
)

result = response.json()

# Check decision
if result["decision"] == "allow":
    execute_payment(action)  # Your existing code
elif result["decision"] == "escalate":
    send_to_human_review(action, result["reason"])
else:  # deny
    log_blocked_action(action, result["reason"])
```

**Pros:**
- ✅ Zero infrastructure setup
- ✅ Always up-to-date validators
- ✅ Managed compliance updates
- ✅ Multi-region for low latency

**Cons:**
- ⚠️ Requires internet connectivity
- ⚠️ Data leaves your infrastructure (encrypted)

**Best for:** Startups, fintechs <100 employees, rapid deployment

**Pricing:** €250-€1,000/month (Startup/Scale tiers)

---

### 2️⃣ Self-Hosted (Docker)

**What it is:** Run RAGF validators in your own infrastructure.

**Architecture:**
```
Your Agent → Internal Network → RAGF Container (your VPS/K8s)
                                      ↓
                              (Validators run locally)
```

**Integration:**
```bash
# 1. Deploy RAGF on your infrastructure
docker run -d \
  -p 8000:8000 \
  -e RAGF_LICENSE_KEY=your-key \
  agentsave/ragf:latest

# 2. Your agent calls localhost
curl -X POST http://localhost:8000/validate \
  -H "Content-Type: application/json" \
  -d '{
    "action": {"amount": 350, "sca_completed": false},
    "domain": "fintech"
  }'
```

**Pros:**
- ✅ Data never leaves your network
- ✅ Sub-millisecond latency
- ✅ Full control over updates
- ✅ Meets strict compliance requirements

**Cons:**
- ⚠️ You manage infrastructure
- ⚠️ Manual validator updates (unless automated)

**Best for:** Banks, regulated enterprises, on-premise requirements

**Pricing:** €5,000+/month (Enterprise tier + license)

---

### 3️⃣ SDK/Library (Future)

**What it is:** Embed RAGF validators directly in your code.

**Architecture:**
```
Your Agent Process
  ├── Your business logic
  └── RAGF SDK (in-process validation)
```

**Integration (planned):**
```python
from ragf import FintechValidator

# Initialize once
validator = FintechValidator(
    config_path="./ragf_config.yaml"
)

# Validate in-process (no network call)
result = validator.validate(action)

if result.is_allowed():
    execute_payment(action)
```

**Pros:**
- ✅ Zero network latency
- ✅ Works offline
- ✅ Complete control

**Cons:**
- ⚠️ Must update SDK manually
- ⚠️ Compliance changes = code deploy

**Best for:** High-frequency trading, ultra-low latency needs

**Availability:** Q3 2026 (roadmap)

---

## 📊 Comparison Table

| Feature | SaaS API | Self-Hosted | SDK |
|---------|----------|-------------|-----|
| **Setup Time** | <5 min | 1-2 hours | 30 min |
| **Latency** | 20-50ms | <5ms | <0.1ms |
| **Data Locality** | Cloud | Your infra | Your infra |
| **Updates** | Automatic | Manual/Auto | Manual |
| **Compliance Burden** | Agent Save | Shared | You |
| **Price** | €250-€1K | €5K+ | TBD |
| **Best For** | Most teams | Enterprises | HFT |

---

## 🚀 Quick Start (SaaS API)

### Step 1: Sign Up
```bash
# Request beta access
curl -X POST https://api.agentsave.one/beta-access \
  -d '{"email": "cto@yourfintech.com"}'
```

### Step 2: Get API Key
```
Email → API Key + Dashboard access
```

### Step 3: Integrate (5 lines of code)
```python
import requests

API_KEY = "sk_live_..."  # From dashboard

def validate_action(action: dict) -> dict:
    """Validate action through RAGF before execution."""
    response = requests.post(
        "https://api.agentsave.one/v1/validate",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=action,
        timeout=0.5  # Fail-closed if timeout
    )
    
    if response.status_code != 200:
        return {"decision": "deny", "reason": "Validation service error"}
    
    return response.json()

# In your agent
action = {"amount": 100, "type": "payment"}
result = validate_action(action)

if result["decision"] == "allow":
    execute(action)
```

### Step 4: Monitor
```
Dashboard: https://dashboard.agentsave.one
- See all validations
- Audit trail
- Compliance reports
```

---

## 🔐 Data Security

All deployment models include:
- ✅ TLS 1.3 encryption in transit
- ✅ AES-256 encryption at rest
- ✅ No PII stored (only transaction metadata)
- ✅ GDPR compliant
- ✅ SOC 2 Type II (in progress)

---

## 🎓 Example: LangChain Integration

```python
from langchain.agents import AgentExecutor
from langchain.tools import Tool
from ragf_client import RAGFValidator

# Initialize RAGF
ragf = RAGFValidator(api_key="sk_live_...")

# Wrap your tools with RAGF validation
def ragf_validated_tool(func):
    def wrapper(*args, **kwargs):
        action = {"tool": func.__name__, "args": kwargs}
        
        # Validate before execution
        result = ragf.validate(action)
        
        if result.decision == "allow":
            return func(*args, **kwargs)
        elif result.decision == "escalate":
            return f"Action requires approval: {result.reason}"
        else:
            return f"Action denied: {result.reason}"
    
    return wrapper

# Your existing tools
@ragf_validated_tool
def initiate_payment(amount: float, iban: str):
    # Your payment logic
    pass

# LangChain agent works as before
agent = AgentExecutor(tools=[initiate_payment], ...)
```

---

## 📞 Next Steps

1. **Try the demo** → Test validators with your scenarios
2. **Read API docs** → /api/docs endpoint
3. **Request beta access** → cto@reflexio.studio
4. **Schedule integration call** → 30 min technical walkthrough

---

## 💬 Common Questions

**Q: Can I test with my own data?**  
A: Yes! API docs at /api/docs show all parameters.

**Q: What if RAGF API is down?**  
A: Fail-closed design denies actions. Self-hosted avoids this.

**Q: How do I update validators?**  
A: SaaS = automatic. Self-hosted = docker pull. SDK = upgrade package.

**Q: Can I customize validators?**  
A: Yes, Enterprise tier includes custom validator development.

**Q: Does this work with non-Python agents?**  
A: Yes! REST API works with any language. SDKs planned for JS, Go, Java.

---

**Ready to integrate? Start with the SaaS API →** [Request Access]
