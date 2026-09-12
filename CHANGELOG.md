# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(pre-1.0: breaking changes are released as minor bumps).

## [Unreleased]

### Fixed
- `LiabilityGuard`: non-finite inputs (Infinity/NaN) to `verify_cap`, `verify_indemnity_limit`, and `verify_tiered_liability` fail closed with `UNVERIFIABLE` instead of raising `decimal.InvalidOperation` or failing closed only by NaN-comparison accident; affected numeric result fields are now `null` in the failure result (#42).
- `DeadlineGuard`: quantities beyond the supported range (cap: 100,000 — no legal term spans ~274 years) fail closed with `UNVERIFIABLE` instead of raising `OverflowError`; date-range overflow converts to fail-closed; the business-day loop is bounded so astronomical quantities can no longer stall the loop (#42).
- `StatuteOfLimitationsGuard`: fails closed with `UNVERIFIABLE` when the filing date precedes the incident date. A factually impossible (time-travel) timeline no longer computes a positive `days_remaining` or verifies as within-period (#38).
- `DeadlineGuard`: term parsing now pairs each number with its immediately adjacent unit. Compound terms containing more than one time expression (e.g., "30 days and 2 months") fail closed as `UNVERIFIABLE` instead of silently combining the first number with the last matching unit branch (#39).
- `DeadlineGuard`: numbers not adjacent to a time unit (e.g., clause references like "section 4.2") no longer hijack the parsed quantity, and the business-days qualifier must be adjacent to the unit (a "business" elsewhere in the sentence no longer turns calendar days into business days).
- `DeadlineGuard`: numeric tokens must be complete — decimals ("2.5 years" no longer parses as 5 years), signed values ("-30 days"), and numbers embedded in words ("section30days") fail closed instead of matching a partial quantity.
- `DeadlineGuard`: terms containing an unmatched numeric token ("30 or 60 days", "30 days and 48 hours", a clause reference like "4.2") fail closed as ambiguous instead of silently ignoring the extra quantity.
- `DeadlineGuard`: business/working qualifiers on month and year units ("business months", "working years") fail closed instead of silently computing calendar periods.
- `LiabilityGuard`: finite-but-extreme magnitudes (beyond the decimal context) fail closed with `UNVERIFIABLE` instead of raising during quantize; the non-finite failure message names exactly the offending inputs.
- `DeadlineGuard`: the quantity cap now applies to the normalized business-day count, so business-week terms cannot multiply past the cap ("100000 business weeks" = 500,000 business days fails closed instead of looping).
- npm SDK: non-finite liability inputs are rejected client-side (Infinity/NaN interpolated into Python previously raised `NameError`); nullable liability fields serialize as `null` instead of crashing on `float(None)`; the statute `status` is read tolerantly for older Python engines (`null` when absent) and `verifyStatute` accepts an optional `claimedWithinPeriod` argument; the GitHub Action entrypoint serializes null-able liability fields as `null`.
- `StatuteOfLimitationsGuard`: date-order integrity compares full timestamps when the caller supplies time-of-day — a filing earlier in the day than the incident is an impossible timeline. Date-only inputs both parse to midnight, so same-day filing passes.
- `StatuteOfLimitationsGuard`: mixed timezone-aware and timezone-naive date inputs fail closed with `UNVERIFIABLE` instead of raising `TypeError`; the rejection message and trace record the full parsed timestamps.

### Changed (behavior)
- `ProvenanceGuard`: results now carry `assurance: "SELF_DECLARED"` and the human-review check is renamed `human_review_declared` — every provenance field (including `human_reviewed` and `reviewer_id`) is caller-supplied, so a passing result attests internal consistency of the declaration, not external assurance. External assurance requires out-of-band reviewer signatures (#42).
- `ContradictionGuard`: the Z3 model encodes ONLY the text-derived operand of the recognized constraint phrase — the caller's declared value is never a solver input. Each trace step records `encoded_operand`, `caller_value`, and `caller_value_agrees`, and the result message discloses disagreement counts, so a declaration contradicting the text is visible without changing the solver's text-attributable conclusion (#42, PR #45 review).
- `ContradictionGuard`: the operand grammar is ASCII-only via a scoped inline flag (`(?a:...)`), satisfying the concise-`\d` lint while keeping Unicode numerals out of the model; every recognized phrase occurrence must resolve to a valid operand — a phrase followed by a non-ASCII numeral, a sign, or a malformed token fails closed the whole clause, while recognized words in prose (no operand follows) are ignored (#42, PR #45 review).
- `ContradictionGuard`: constraint phrases bind to their numeric operand — a number elsewhere in the clause text (e.g. a notice period in a term clause) is not the term value; keyword phrases without an adjacent number stay unmodeled; signed, decimal, and formatted operands ("-30", "1.5", "1,500") fail closed instead of being silently altered (#42, PR #45 review).
- `SACProcessor`: nested marker fragments that reassemble past the bounded removal passes refuse the fingerprint entirely (deterministic-hash fallback), closing a sanitizer bypass (PR #45 review, Greptile-executed); the raw-response cap applies before the blank check (PR #45 review).
- `ProvenanceGuard`: `human_reviewed` must be exactly `True` (truthy non-Boolean values fail); the legacy `human_review` check token is emitted alongside `human_review_declared` during a deprecation window for caller compatibility (PR #45 review).
- `SACProcessor`: raw LLM responses are capped before sanitization (bounded work, CWE-400) and an all-marker response falls back to the deterministic hash instead of embedding an empty fingerprint (PR #45 review).
- `ContradictionGuard`: keyword matching is word-boundary — substring matches ("cap" inside "capability") no longer mis-encode constraints; unmodeled keywords fall through to partial coverage as designed (#42).
- `SACProcessor`: the LLM-generated fingerprint is labeled `[AI-GENERATED SUMMARY — UNTRUSTED CONTENT]`, the deterministic document hash is always carried alongside (even when a caller-supplied `document_id` exists), and the summary is sanitized (single-line, control characters and forged `CHUNK CONTENT`/`DOCUMENT CONTEXT` markers stripped) so a compromised summarizer cannot poison corpus-wide retrieval structure (#42).
- `StatuteOfLimitationsGuard` results now carry a `status` field: `CLAIM_VERIFIED` / `CLAIM_INCORRECT` when a `claimed_within_period` answer was supplied, `COMPUTED_ONLY` in computation-only mode, and `UNVERIFIABLE` for input-class rejections. `verified` is now reserved for claim comparison — in computation-only mode it is `False` by contract (previously it doubled as the within-period legal fact, making an expired-but-correctly-evaluated claim indistinguishable from a verification failure) (#42). The TypeScript SDK's `StatuteResult` echoes the new field.

### Hygiene (issue #41)
- `CitationGuard`: the US_CODE statute pattern accepts an omitted section symbol ("12 U.S.C. 2605") — real-world drafting often drops the §; formatted cites without it were false-negatived.
- `ClauseGuard`: day extraction gains a proximity fallback — day counts separated from their context word by intervening words ("give notice within 10 days of discovery") are now extracted; directional patterns unchanged.
- `statute_guard.py`: corrected the UK fraud comment — the 6-year value follows Limitation Act 1980 s.5 with s.32 discovery deferral; the old "No limit" comment contradicted the table.
- Dockerfile: base image digest-pinned (`python:3.14.6-slim@sha256:7bec7dd…`) and runs as a non-root user.

### Ecosystem Alignment
- Synced the PyPI package description with the repository identity ("Deterministic rejection layer for computational legal claims...").
- Added `.qwed.yml` (QWED Security scanner configuration, matching the qwed-finance convention) and the QWED Security Marketplace badge to the README badge row (#36).

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
