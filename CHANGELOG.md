# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(pre-1.0: breaking changes are released as minor bumps).

## [Unreleased]

### Fixed
- `StatuteOfLimitationsGuard`: fails closed with `UNVERIFIABLE` when the filing date precedes the incident date. A factually impossible (time-travel) timeline no longer computes a positive `days_remaining` or verifies as within-period (#38).
- `DeadlineGuard`: term parsing now pairs each number with its immediately adjacent unit. Compound terms containing more than one time expression (e.g., "30 days and 2 months") fail closed as `UNVERIFIABLE` instead of silently combining the first number with the last matching unit branch (#39).
- `DeadlineGuard`: numbers not adjacent to a time unit (e.g., clause references like "section 4.2") no longer hijack the parsed quantity, and the business-days qualifier must be adjacent to the unit (a "business" elsewhere in the sentence no longer turns calendar days into business days).
- `DeadlineGuard`: numeric tokens must be complete — decimals ("2.5 years" no longer parses as 5 years), signed values ("-30 days"), and numbers embedded in words ("section30days") fail closed instead of matching a partial quantity.
- `DeadlineGuard`: terms containing an unmatched numeric token ("30 or 60 days", "30 days and 48 hours", a clause reference like "4.2") fail closed as ambiguous instead of silently ignoring the extra quantity.
- `DeadlineGuard`: business/working qualifiers on month and year units ("business months", "working years") fail closed instead of silently computing calendar periods.
- `StatuteOfLimitationsGuard`: date-order integrity compares full timestamps when the caller supplies time-of-day — a filing earlier in the day than the incident is an impossible timeline. Date-only inputs both parse to midnight, so same-day filing passes.
- `StatuteOfLimitationsGuard`: mixed timezone-aware and timezone-naive date inputs fail closed with `UNVERIFIABLE` instead of raising `TypeError`; the rejection message and trace record the full parsed timestamps.

### Build / Tooling
- Pinned the ruff lint gate to the stable default ruleset (`select = ["E4", "E7", "E9", "F"]` under `[tool.ruff.lint]`). Ruff's default rule selection expanded in newer releases, which flipped CI red on unchanged code.
- Pinned ruff to `0.16.1` in CI and via `required-version` in pyproject so the gate cannot drift with future ruff releases.

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
