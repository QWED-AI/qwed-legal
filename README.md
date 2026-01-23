<div align="center">
  <h1>🏛️ QWED-Legal</h1>
  <h3>Verification Guards for Legal Contracts</h3>
  
  > **Catch AI hallucinations before they become lawsuits.**
  
  <p>
    <b>Don't trust AI with legal analysis. Verify it.</b><br>
    <i>Deadline math • Clause contradictions • Liability calculations</i>
  </p>

  [![Verified by QWED](https://img.shields.io/badge/Verified_by-QWED-00C853?style=flat&logo=checkmarx)](https://github.com/QWED-AI/qwed-legal)
  [![GitHub Developer Program](https://img.shields.io/badge/GitHub_Developer_Program-Member-4c1?style=flat&logo=github)](https://github.com/QWED-AI)
  [![PyPI](https://img.shields.io/pypi/v/qwed-legal?color=blue&cacheSeconds=60)](https://pypi.org/project/qwed-legal/)
  [![npm](https://img.shields.io/npm/v/@qwed-ai/legal?color=red)](https://www.npmjs.com/package/@qwed-ai/legal)
  [![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
  [![Tests](https://github.com/QWED-AI/qwed-legal/actions/workflows/ci.yml/badge.svg)](https://github.com/QWED-AI/qwed-legal/actions)

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

### 📦 Installation

| Language | Package | Command |
|----------|---------|---------|
| **Python** | `qwed-legal` | `pip install qwed-legal` |
| **TypeScript/JS** | `@qwed-ai/legal` | `npm install @qwed-ai/legal` |

**Python:**
```bash
pip install qwed-legal
```

**TypeScript/JavaScript:**
```bash
npm install @qwed-ai/legal
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

## 🛡️ The Six Guards

| Guard | What It Verifies |
|-------|------------------|
| **DeadlineGuard** | Date calculations, business days, leap years |
| **LiabilityGuard** | Cap percentages, tiered liability, indemnity limits |
| **ClauseGuard** | Clause contradictions, termination conflicts |
| **CitationGuard** | Legal citations (Bluebook format, case names, reporters) |
| **JurisdictionGuard** | Choice of law, forum selection, cross-border conflicts |
| **StatuteOfLimitationsGuard** | Claim periods by jurisdiction and claim type |

### Verify Legal Citations

```python
from qwed_legal import CitationGuard

guard = CitationGuard()
result = guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")

print(result.valid)  # True
print(result.parsed_components)
# {'plaintiff': 'Brown', 'defendant': 'Board of Education', 'volume': 347, 'reporter': 'U.S.', 'page': 483, 'year': 1954}
```

### Verify Jurisdiction (New in v0.2.0!)

```python
from qwed_legal import JurisdictionGuard

guard = JurisdictionGuard()
result = guard.verify_choice_of_law(
    parties_countries=["US", "UK"],
    governing_law="Delaware",
    forum="London"
)

print(result.conflicts)  # ['Governing law Delaware (US state) but forum London is non-US...']
```

### Check Statute of Limitations (New in v0.2.0!)

```python
from qwed_legal import StatuteOfLimitationsGuard

guard = StatuteOfLimitationsGuard()
result = guard.verify(
    claim_type="breach_of_contract",
    jurisdiction="California",
    incident_date="2020-01-15",
    filing_date="2026-06-01"
)

print(result.verified)  # False - 4 year limit exceeded!
print(result.message)   # ❌ EXPIRED: Statute of limitations expired...
```

---

## 📦 TypeScript/JavaScript (npm)

```bash
npm install @qwed-ai/legal
```

### Available Verifiers

| Verifier | Description |
|----------|-------------|
| `DeadlineVerifier` | Verify date calculations |
| `LiabilityVerifier` | Verify liability caps |
| `ClauseVerifier` | Detect contradictions |
| `CitationVerifier` | Validate legal citations |
| `JurisdictionVerifier` | Check choice of law |
| `StatuteVerifier` | Check limitation periods |
| `LegalGuard` | All-in-one wrapper |

### TypeScript Examples

```typescript
import { 
  DeadlineVerifier, 
  JurisdictionVerifier, 
  StatuteVerifier,
  LegalGuard 
} from '@qwed-ai/legal';

// Verify deadline
const deadline = new DeadlineVerifier();
const result = await deadline.verify("2026-01-15", "30 days", "2026-02-14");
console.log(result.verified);  // true

// Check jurisdiction
const jurisdiction = new JurisdictionVerifier();
const jResult = await jurisdiction.verifyChoiceOfLaw(
  ["US", "UK"], "Delaware", "London"
);
console.log(jResult.conflicts);  // Array of conflicts

// All-in-one guard
const guard = new LegalGuard();
const deadline2 = await guard.deadline.verify(...);
const statute = await guard.statute.verify(...);
```

---

## 🌍 Supported Jurisdictions

### Statute of Limitations

| Jurisdiction | Breach of Contract | Negligence | Fraud |
|--------------|-------------------|------------|-------|
| California | 4 years | 2 years | 3 years |
| New York | 6 years | 3 years | 6 years |
| Texas | 4 years | 2 years | 4 years |
| Delaware | 3 years | 2 years | 3 years |
| UK/England | 6 years | 6 years | 6 years |
| Germany | 3 years | 3 years | 10 years |
| France | 5 years | 5 years | 5 years |
| Australia | 6 years | 6 years | 6 years |
| India | 3 years | 3 years | 3 years |

### DeadlineGuard Holiday Support

| Region | Countries/States |
|--------|-----------------|
| **United States** | All 50 states + DC |
| **European Union** | DE, FR, IT, ES, NL, BE, AT, PL |
| **Commonwealth** | UK, AU (all states), CA |
| **Asia** | IN (all states), SG, HK |


---

## 📊 Audit Log: Real Hallucinations Caught

| Contract Input | LLM Claim | QWED Verdict |
|----------------|-----------|--------------|
| "Net 30 Business Days from Dec 20" | Jan 19 | 🛑 **BLOCKED** (Actual: Feb 2, 2026) |
| "Liability Cap: 2x Fees ($50k)" | $200,000 | 🛑 **BLOCKED** (Actual: $100,000) |
| "Seller may terminate with 30 days notice" + "Neither party may terminate before 90 days" | "Clauses are consistent" | 🛑 **BLOCKED** (Conflict detected) |
| "Smith v. Jones, 999 FAKE 123" | Valid citation | 🛑 **BLOCKED** (Unknown reporter) |

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
