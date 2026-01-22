<div align="center">
  <h1>🏛️ QWED-Legal</h1>
  <h3>Verification Guards for Legal Contracts</h3>
  
  > **Catch AI hallucinations before they become lawsuits.**
  
  <p>
    <b>Don't trust AI with legal analysis. Verify it.</b><br>
    <i>Deadline math • Clause contradictions • Liability calculations</i>
  </p>

  [![PyPI version](https://img.shields.io/pypi/v/qwed-legal)](https://pypi.org/project/qwed-legal/)
  [![Tests](https://github.com/QWED-AI/qwed-legal/actions/workflows/ci.yml/badge.svg)](https://github.com/QWED-AI/qwed-legal/actions)
  [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

---

## 🚨 The Problem

**Lawyers are using AI to review contracts. AI makes mistakes.**

| Case | What Happened | Impact |
|------|--------------|--------|
| **Mata v. Avianca (2023)** | ChatGPT cited 6 fake legal cases | $5,000 fine, sanctions |
| **Contract Review Errors** | LLMs miss contradictory clauses | Disputes, litigation |
| **Date Calculation Bugs** | "30 business days" miscalculated | Missed deadlines, defaults |

---

## ⚡ Quick Start

### Installation

```bash
pip install qwed-legal
```

### Verify a Deadline Calculation

```python
from qwed_legal import DeadlineGuard

guard = DeadlineGuard()
result = guard.verify(
    signing_date="2026-01-15",
    term="30 business days",
    claimed_deadline="2026-02-14"  # LLM claimed this
)

print(result.verified)   # False!
print(result.computed_deadline)  # 2026-02-27 (correct)
print(result.message)
# ❌ ERROR: Deadline mismatch. Expected 2026-02-27, but LLM claimed 2026-02-14.
```

### Verify a Liability Cap

```python
from qwed_legal import LiabilityGuard

guard = LiabilityGuard()
result = guard.verify_cap(
    contract_value=5_000_000,
    cap_percentage=200,
    claimed_cap=15_000_000  # LLM said 15M
)

print(result.verified)  # False!
print(result.computed_cap)  # 10,000,000 (200% of 5M)
# ❌ ERROR: 200% of $5M = $10M, not $15M
```

### Detect Contradictory Clauses

```python
from qwed_legal import ClauseGuard

guard = ClauseGuard()
result = guard.check_consistency([
    "Seller may terminate with 30 days notice",
    "Neither party may terminate before 90 days",
    "Seller may terminate immediately upon breach"
])

print(result.consistent)  # False!
# ⚠️ WARNING: Clauses 1 and 2 may conflict (days 30-90)
```

---

## 🛡️ The Three Guards

| Guard | What It Verifies |
|-------|------------------|
| **DeadlineGuard** | Date calculations, business days, leap years |
| **LiabilityGuard** | Cap percentages, tiered liability, indemnity limits |
| **ClauseGuard** | Clause contradictions, termination conflicts |

---

## 🏦 All-in-One Guard

```python
from qwed_legal import LegalGuard

guard = LegalGuard()

# All verification methods in one object
guard.verify_deadline(...)
guard.verify_liability_cap(...)
guard.check_clause_consistency(...)
```

---

## 🌍 Jurisdiction Support

DeadlineGuard supports jurisdiction-specific holidays:

```python
from qwed_legal import DeadlineGuard

# US holidays (default)
us_guard = DeadlineGuard(country="US")

# UK holidays
uk_guard = DeadlineGuard(country="GB")

# California-specific holidays
ca_guard = DeadlineGuard(country="US", state="CA")
```

---

## 🔗 Related QWED Packages

| Package | Purpose |
|---------|---------|
| [qwed-verification](https://github.com/QWED-AI/qwed-verification) | Core verification engine |
| [qwed-finance](https://github.com/QWED-AI/qwed-finance) | Banking & financial verification |
| [qwed-ucp](https://github.com/QWED-AI/qwed-ucp) | E-commerce transaction verification |
| [qwed-mcp](https://github.com/QWED-AI/qwed-mcp) | Claude Desktop integration |

---

## 📄 License

Apache 2.0 - See [LICENSE](LICENSE)

---

<div align="center">
  <b>⭐ Star us if you believe AI needs verification in legal domains</b>
  <br><br>
  <i>"In law, precision isn't optional. QWED makes it verifiable."</i>
</div>
