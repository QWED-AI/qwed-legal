# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(pre-1.0: breaking changes are released as minor bumps).

## [0.4.0] - 2026-05-30

### Verification Improvements
- Introduced a shared `VerificationStep` model and `verification_trace` on **every guard** — ordered, auditable decision records (not narrative explanations).
- Added `evidence_type` taxonomy: `DETERMINISTIC | PARSED | INFERRED | HEURISTIC | UNSUPPORTED`. `is_proven()` is true only for `DETERMINISTIC`.
- Added `VerificationStep.to_dict()` and `trace_to_dict()` for JSON-safe trace export (non-serializable inputs are stringified, never dropped).

### Security Hardening
- `JurisdictionGuard`: fail-closed on empty `parties_countries` in `verify_choice_of_law` and `check_convention_applicability` (fixed `all([])` fail-open).
- `JurisdictionGuard`: forum warnings now fail verification, consistent with choice-of-law.
- `DeadlineGuard`: business-day results fail closed when the requested holiday calendar cannot be built (no silent wrong-calendar fallback).
- `FairnessGuard`: rejects non-string and case-colliding swap keys; fail-closed on incomplete input.

### Trust-Boundary Changes
- `CitationGuard`: format match is `PARSED`; authority is always `UNSUPPORTED` (never proven). `verified` is always `False`.
- `IRACGuard`: structure is `INFERRED`; reasoning correctness is always `UNSUPPORTED`.
- `StatuteOfLimitationsGuard` / `ContradictionGuard`: documented as `MIXED` (deterministic core over parsed lookup / Z3), unmodeled inputs fail closed.

### Documentation
- README: new "Verification trace (auditability)" section with the evidence-type table and a `trace_to_dict` export example.
- README: corrected `CitationGuard` example to use `format_valid` / `status` / `verified=False`; added `ProvenanceGuard` to the guard coverage table; relabelled Statute/Contradiction as `MIXED`.

### SDK
- TypeScript SDK aligned to the Python contract: every result interface now exposes `verification_trace` (`VerificationStep[]`).
- Added `FairnessVerifier` reflecting the #18 fail-closed contract.
- `CitationResult` now exposes `format_valid` / `status` / `verified: false`.
- npm package version reconciled from `1.0.0` to `0.4.0` (parity with the Python package; `1.0.0` implied a stability/parity guarantee that did not exist).

### Breaking Changes
- `FairnessGuard.verify_decision_fairness` **no longer returns `verified=True`** (resolves #18). A consistent counterfactual outcome is `UNVERIFIABLE_FAIRNESS`; a differing outcome is a `HEURISTIC_BIAS_SIGNAL` for human review.
  - Migration: treat fairness output as a signal requiring human review, not as a pass/verified result.

### Internal
- Reconciled `pyproject.toml` version (`0.3.0` → `0.4.0`) with `qwed_legal.__version__`.

## [0.2.0] - 2026-01-23
- Previous public release.
