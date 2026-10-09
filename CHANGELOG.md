# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(pre-1.0: breaking changes are released as minor bumps).

## [0.5.1] - Unreleased

Security patch release. Upgrading is recommended for all users of `DeadlineGuard`
(Python API, npm SDK, and GitHub Action). A security advisory will be published
alongside this release.

### Security — DeadlineGuard deadline anchoring
- `DeadlineGuard` now computes a deadline from the signing date **only** when the term is bare-relative (`"30 days"`) or affirmatively anchored to signing/execution (`"30 days from signing"`, `"15 days after execution"`). Every other term fails closed with `UNVERIFIABLE` and an `UNSUPPORTED` trace step, instead of being certified `VERIFIED` against a reference the guard cannot date.
- Directional terms (`"30 days before signing"`, `"prior to"`, `"ahead of"`, `"preceding"`) previously computed forward from the signing date and could certify the opposite direction. They now fail closed.
- Event anchors outside the earlier event-noun list (e.g. `"after closing"`, `"after completion"`, `"within 30 days of request"`) and long adjective gaps before a listed noun are now rejected. This replaces the open-ended noun denylist with an allowlist of signing-anchored phrasings, completing the follow-up to #54.
- The new check runs before date arithmetic, so rejected business-day terms never touch the holiday calendar.
- The npm `DeadlineVerifier` now refuses to run (rejects) when the importable Python `qwed-legal` is older than 0.5.1, so an npm-only upgrade cannot silently keep the old deadline engine.

### Behaviour change
- Terms that previously returned `VERIFIED` because they were silently measured from the signing date — but are actually anchored to another event or measured backward — now return `UNVERIFIABLE`. To keep a deterministic result, supply a term measured forward from the signing date. For a forward term anchored to another event, first confirm the event's date and direction, then provide that date as `signing_date` and rewrite the term to a supported bare-relative form such as `"30 days"`. Changing the date alone does not make the original event-anchored term supported.

### Tests
- Added regression coverage for directional and unlisted-event terms, plus the supported terms that must continue to verify. Full suite: 665 passed.

## [0.5.0] - 2026-10-07

### Added — DiagnosticResult contract (issue #40, Option A per #37)
- New `qwed_legal.diagnostics` module: `LegalDiagnosticResult` (frozen 3-layer result: `agent_message` / `developer_fields` / `proof_ref`), `LegalDiagnosticStatus` (VERIFIED / UNVERIFIABLE / BLOCKED), an RFC 8785 (JCS) canonicalizer, `compute_proof_ref`, and `resolve_proof_ref`.
- `VerificationStep` is now a **frozen** dataclass — evidence steps cannot be mutated after construction (audit P1-L3: the DETERMINISTIC→HEURISTIC flip is structurally impossible).
- All guard result dataclasses are **frozen** and inherit the `LegalDiagnosticsMixin`: every result exposes `to_diagnostic(claim_inputs=...)`, which builds the RFC 8785 proof evidence over (claim inputs, full verification_trace, result snapshot) and maps the guard outcome onto the ecosystem tri-state.
- Authority contract (structurally enforced): VERIFIED requires `proof_ref`; UNVERIFIABLE/BLOCKED reject it. Status mapping: verified claim matches → VERIFIED; computed-only / ambiguous / self-declared / heuristic-pass / citation-authority → UNVERIFIABLE; mismatch / contradiction / tamper / format-invalid → BLOCKED. Self-declared provenance attestations are never authoritative (#42/#45).
- `resolve_proof_ref(proof_ref, evidence)` lets any consumer detect post-issuance tampering (trace mutation, claim alteration, evidence-type flips) by recomputing the canonical hash.
- Deep-freeze hardening (PR #48 review): `VerificationStep.inputs` is exposed through a mutation-disabled mapping, result evidence containers (traces, conflicts, tiers, parsed components) are frozen at construction, `LegalDiagnosticResult.developer_fields` is deep-frozen, and `proof_ref` format (`sha256:` + 64 hex) is validated at construction.
- Status mappings refined per review: jurisdiction results are never VERIFIED (PARSED/INFERRED evidence only); liability diagnostics classify from structured fields (computed cap present/absent), not message wording; deadline fallback-calendar results map to UNVERIFIABLE; clause `verify_using_z3` emits explicit `z3_satisfiable` / `z3_unsat` statuses mapping to VERIFIED / BLOCKED.
- Canonicalizer hardening: integers outside the IEEE 754 safe range and lone surrogates fail closed; set evidence is sorted deterministically; non-primitive values are type-tagged so distinct evidence types never collide.
- `fairness_to_diagnostic` adapter lives in `diagnostics.py` (FairnessGuard module left untouched — its pre-existing scanner findings must not be dragged into a release-blocking state); the fairness payload is JSON-serialized.
- `ContradictionGuard.to_diagnostic` retains the exact claim/result structures in `developer_fields` so `resolve_proof_ref` reconstructs the hash from the diagnostic alone.
- Deep-freeze completeness (PR #48 review R3): `_deep_freeze` recurses into tuples, sets, and frozensets (sets sorted deterministically before freezing), `_plain` serializes the frozen containers back, `_json_safe` rejects non-string mapping keys instead of coercing them, and `VerificationStep` inputs are deep-frozen at any nesting depth.
- Z3 clause diagnostics bind the actual constraint expressions (`str()` per constraint) in the SAT trace, so two different satisfiable sets with the same count never produce identical proof evidence.
- Jurisdiction diagnostics: a detected conflict is BLOCKED even though its evidence is INFERRED; unsupported/unanalyzable inputs stay UNVERIFIABLE.
- The diagnostics mixin never maps `verified=True` with an empty agent message to VERIFIED (Layer 1 is mandatory), and supplies a fallback message otherwise.
- Jurisdiction refinement (PR #48 review R4): a detected conflict BLOCKS even when an unsupported-input warning is also present — the two are independent signals. A conflicts entry backed only by UNSUPPORTED trace evidence (empty-party placeholders) stays UNVERIFIABLE; only conflicts backed by actual analysis evidence (INFERRED/DETERMINISTIC) block.
- `_FrozenDict` blocks in-place union (`|=`); `models._json_safe` rejects non-string mapping keys (step inputs and proof evidence) instead of coercing with `str(k)`, which collapsed distinct keys.


### Fixed
- `LiabilityGuard`: non-finite inputs (Infinity/NaN) to `verify_cap`, `verify_indemnity_limit`, and `verify_tiered_liability` fail closed with `UNVERIFIABLE` instead of raising `decimal.InvalidOperation` or failing closed only by NaN-comparison accident; affected numeric result fields are now `null` in the failure result (#42).
- `ClauseGuard`: clause lists over 200 items and single clauses over 4096 characters fail closed as invalid input, and conflict accumulation caps at 100 pairs with truncation disclosed — pairwise work and retained output no longer scale quadratically with caller-controlled size (#75). Citation case-prefix regexes dropped the nested-quantifier group that backtracked cubically on digit-free input; canonical verdicts unchanged (#79). Digit runs over 18 characters fail closed before `int()` coercion across clause, deadline and contradiction guards (CPython caps conversion at 4300 digits) (#80).
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
- GitHub Action entrypoint: every executed block is gated on the diagnostic ladder (VERIFIED admits) instead of convenience booleans — unknown modes and runs that execute zero verifications fail closed (exit 1, `verified=false`); single-clause inputs report `insufficient_input`; citation blocks never attest (citation authority is unconfirmable by design); only deterministic proofs keep the action green (deadline/liability exact matches; z3 clause proofs attest at the helper level via the Python guard API — this Action's JSON clause path cannot produce one, see `action.yml`; heuristic clause passes no longer attest). Typo'd modes, citation-mode runs, and heuristic-clause runs that previously passed will now fail — branch on `results.clause.status` / `results.citation.valid` explicitly if limited coverage is acceptable. `action.yml` documents the per-mode attestation policy (#67, #68).

### Hygiene (issue #41)
- `CitationGuard`: the US_CODE statute pattern accepts an omitted section symbol ("12 U.S.C. 2605") — real-world drafting often drops the §; formatted cites without it were false-negatived. Literal "+" separators are not citation syntax and remain rejected.
- `ClauseGuard`: day extraction gains linked and proximity association tiers — day counts separated from their context word by a linker word ("notice within 10 days") or sitting nearby are now extracted; the closest expression wins and an ambiguous gap-tie stays unresolved. Directional patterns unchanged (singular "day" preserved).
- `statute_guard.py`: corrected the UK fraud comment — the lookup value is 6 years (Limitation Act 1980); the old "No limit" comment contradicted the table.
- Dockerfile: base image digest-pinned without a redundant tag (`python@sha256:7bec7dd…`), the package README is copied into the build context (required by the declared pyproject readme), and `HEALTHCHECK NONE` is declared (one-shot action container — no long-running service to monitor). Non-root USER intentionally omitted: GitHub Docker container actions must run as the default user to access GITHUB_OUTPUT/GITHUB_WORKSPACE.
- `CitationGuard`: the section identifier must start with a digit — "12 U.S.C. provides that..." is prose, not a citation — and U.S.C. requires its separating whitespace (a bare "12 U.S.C.§..." form is rejected), while multi-section Bluebook runs ("§§ 1983") stay valid (PR #47 review).
- `ClauseGuard`: multiple linked durations with different values ("breach notice within 10 days; termination notice within 120 days") are ambiguous and stay unresolved instead of picking the first in document order (PR #47 review).

### Ecosystem Alignment
- Synced the PyPI package description with the repository identity ("Deterministic rejection layer for computational legal claims...").
- Added `.qwed.yml` (QWED Security scanner configuration, matching the qwed-finance convention) and the QWED Security Marketplace badge to the README badge row (#36).

### Build / Tooling
- Pinned the ruff lint gate to the stable default ruleset (`select = ["E4", "E7", "E9", "F"]` under `[tool.ruff.lint]`). Ruff's default rule selection expanded in newer releases, which flipped CI red on unchanged code.
- Pinned ruff to `0.16.1` in CI and via `required-version` in pyproject so the gate cannot drift with future ruff releases.
- CI: new `npm-test` job builds the wrapper from source and runs the dependency-free `node:test` suite (#93).

### Fixed — fail-closed batch (#70, #83–85, #87–88)
- `ClauseGuard`: empty inputs fail closed instead of verifying vacuously (#70).
- `LiabilityGuard`: `verify_tiered_liability` refuses empty tier lists before summation — no operands means no proof (#83).
- `ProvenanceGuard` / `JurisdictionGuard`: explicit emptiness at the provenance gate and convention parties — blank entries are `INCOMPLETE`/`UNVERIFIABLE`, not silent passes (#84).
- `JurisdictionGuard`: three-way `contract_type` classification for CISG — goods contracts (separator/case variants, bare `"sale"` excluded) warn; declared non-goods (`"services"`, …) do not; missing/blank/unknown values get a partial-coverage warning and are never verified. The US/non-US party pair alone no longer triggers the warning (#85).
- GitHub Action: runs that execute zero verifications (missing inputs, typo'd modes) fail closed; aggregation is attest-only — only deterministic proofs keep the step green (#87).
- Diagnostics: `LegalDiagnosticResult.verified()` raises unless the evidence trace contains a `DETERMINISTIC` step — traceless or transport-stripped `"consistent"` verdicts demote to `UNVERIFIABLE` (#88).

### Fixed — statute/date batch (#90–92)
- `DeadlineGuard` / `StatuteOfLimitationsGuard`: order-ambiguous numeric dates (`"03/04/2026"`) fail closed with `AMBIGUITY_NOTED` instead of certifying the month-first reading; ISO and named-month dates unaffected. Raw strings preserved in the trace (#55, #58 → PR #90).
- `DeadlineGuard` / `StatuteOfLimitationsGuard`: partial dates (`"March 2024"`, `"Friday"`) fail closed instead of completing from the wall clock — verdicts no longer vary by run day; yearless `"February 29"` and all weekday names covered; parsed datetimes recorded as `None` so clock-filled values never leak into results (#57, #59 → PR #91).
- `DeadlineGuard`: event-anchored terms (`"within 15 days after receipt of written notice"`) fail closed — only preposition-governed event nouns count, with signing-anchored, conditional (`"conditioned upon acceptance"`), and descriptive (`"notice of termination"`) carve-outs; comparison runs at date granularity (no more floor-to-exact); timezone-aware inputs compare in the deadline's frame; mixed aware/naive inputs fail closed (#54, #56 → PR #92).

### Added — npm SDK (#86 → PR #93)
- `verifyChoiceOfLaw` accepts an optional 4th parameter `contractType?: string` (passed as a `contract_type=` keyword — position 4 is `forum_selection`), so SDK callers can declare known classifications instead of always landing unclassified. Omitted behaves exactly as before.
- `JurisdictionResult` gains optional `contractType` (echo) and `contractClassification` (`goods` | `declared_non_goods` | `unclassified`, read off the trace) so callers need not parse messages.
- First npm wrapper tests (`npm/test/`, dependency-free `node:test`): the services/goods/omitted matrix, quote/backslash/NUL payload escaping, null-handling, plus an `npm-test` CI job. `contractType` serializes as a JSON literal so control characters (including NUL) cannot break the generated Python program.

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
