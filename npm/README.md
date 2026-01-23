# @qwed-ai/legal

TypeScript wrapper for **QWED-Legal** - Verification guards for legal contracts.

[![npm version](https://img.shields.io/npm/v/@qwed-ai/legal?color=red)](https://www.npmjs.com/package/@qwed-ai/legal)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

## Installation

```bash
npm install @qwed-ai/legal
```

**Prerequisites:** Python 3.10+ with `qwed-legal` installed:
```bash
pip install qwed-legal
```

## Quick Start

```typescript
import { DeadlineVerifier, JurisdictionVerifier, StatuteVerifier } from '@qwed-ai/legal';

// Verify contract deadlines
const deadline = new DeadlineVerifier();
const result = await deadline.verify("2026-01-15", "30 business days", "2026-02-27");
console.log(result.verified);  // true/false

// Check jurisdiction conflicts
const jurisdiction = new JurisdictionVerifier();
const jurisdictionResult = await jurisdiction.verifyChoiceOfLaw(
    ["US", "UK"],
    "Delaware",
    "London"
);
console.log(jurisdictionResult.conflicts);  // Array of conflicts

// Verify statute of limitations
const statute = new StatuteVerifier();
const statuteResult = await statute.verify(
    "breach_of_contract",
    "California",
    "2022-01-15",
    "2026-06-01"
);
console.log(statuteResult.verified);  // true - within 4 year limit
```

## Available Verifiers

| Verifier | Description |
|----------|-------------|
| `DeadlineVerifier` | Verify date calculations (business days, calendar days, holidays) |
| `LiabilityVerifier` | Verify liability cap calculations |
| `ClauseVerifier` | Detect contradictory clauses |
| `CitationVerifier` | Validate Bluebook legal citations |
| `JurisdictionVerifier` | Verify choice of law and forum selection |
| `StatuteVerifier` | Check statute of limitations periods |
| `LegalGuard` | All-in-one wrapper for all verifiers |

## All-in-One Guard

```typescript
import { LegalGuard } from '@qwed-ai/legal';

const guard = new LegalGuard();

// Access all verifiers
const deadline = await guard.deadline.verify(...);
const jurisdiction = await guard.jurisdiction.verifyChoiceOfLaw(...);
const statute = await guard.statute.verify(...);
```

## License

Apache 2.0 - Part of the [QWED Ecosystem](https://github.com/QWED-AI)
