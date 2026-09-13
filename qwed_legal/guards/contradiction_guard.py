"""
ContradictionGuard: Detect logical contradictions in contract clauses using Z3.

Fail-closed design:
  - Only DURATION and LIABILITY categories are modeled.
  - Unsupported categories are never silently ignored — UNVERIFIABLE is returned.
  - Supported clauses with unmodeled keywords (no constraint added) are tracked
    and cause partial_coverage — never verified=True for partial inputs.
  - Z3 unknown result → UNVERIFIABLE (not a false contradiction).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional
from z3 import Int, Solver, sat, unknown

from qwed_legal.diagnostics import LegalDiagnosticResult
from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_AMBIGUITY_NOTED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
    EVIDENCE_UNSUPPORTED,
)


@dataclass
class Clause:
    """A single contract clause with a category and numeric value."""

    text: str
    category: str  # DURATION, LIABILITY — supported. All others: UNVERIFIABLE.
    value: int
    id: str = field(default="")  # optional identifier


# Categories that ContradictionGuard can translate into Z3 constraints.
SUPPORTED_CATEGORIES = frozenset({"DURATION", "LIABILITY"})


class ContradictionGuard:
    """
    Detects logical contradictions in contract clauses using Z3.

    Supported categories: DURATION, LIABILITY.

    Fail-closed:
    - Unsupported categories → UNVERIFIABLE (never silently ignored).
    - No supported clauses present → UNVERIFIABLE.
    - Supported clauses whose keywords are not modeled → partial_coverage,
      verified=False (constraint could not be encoded).
    - Z3 unknown → UNVERIFIABLE (not a false contradiction).
    """

    @classmethod
    def to_diagnostic(
        cls,
        result: dict,
        clauses: "Optional[List[Clause]]" = None,
    ) -> LegalDiagnosticResult:
        """Convert a verify_consistency() result dict to the 3-layer
        LegalDiagnosticResult (issue #40).

        Status mapping: consistent → VERIFIED (Z3 SAT over text-derived
        operands is deterministic proof); contradiction → BLOCKED;
        unverifiable / partial_coverage → UNVERIFIABLE. Pass the original
        ``clauses`` so the proof evidence binds the claim inputs.
        """
        status = result.get("status", "unverifiable")
        trace = result.get("verification_trace", [])
        trace_dicts = [
            step.to_dict() if hasattr(step, "to_dict") else step
            for step in trace
        ]
        claim_texts = [c.text for c in (clauses or [])]
        if not claim_texts:
            claim_texts = [
                step.get("inputs", {}).get("clause_text")
                for step in trace_dicts
                if isinstance(step, dict)
                and step.get("step") == "FACT_DERIVED"
            ]
            claim_texts = [t for t in claim_texts if t]
        # Retain the exact claim/result structures in developer_fields so
        # resolve_proof_ref() can reconstruct the hash from the
        # LegalDiagnosticResult alone (PR #48 review, CodeRabbit).
        claim_inputs = {"clauses": claim_texts}
        result_snapshot = {"status": status}
        developer_fields = {
            "claim_inputs": claim_inputs,
            "verification_trace": trace_dicts,
            "result": result_snapshot,
            "unsupported": result.get("unsupported", []),
            "contradiction_status": status,
        }
        evidence = {
            "claim_inputs": claim_inputs,
            "trace": trace_dicts,
            "result": result_snapshot,
        }
        if status == "consistent":
            return LegalDiagnosticResult.verified(
                agent_message=result.get("message", "Clauses are consistent."),
                developer_fields=developer_fields,
                evidence=evidence,
            )
        if status == "contradiction":
            return LegalDiagnosticResult.blocked(
                agent_message=result.get("message", "Clauses are contradictory."),
                developer_fields=developer_fields,
            )
        return LegalDiagnosticResult.unverifiable(
            agent_message=result.get("message", "Consistency could not be determined."),
            developer_fields=developer_fields,
        )

    def verify_consistency(self, clauses: List[Clause]) -> dict:
        """
        Translate supported legal clauses into Z3 constraints and check SAT.

        Returns a dict with keys:
          verified     (bool)
          status       (str) — consistent | contradiction | unverifiable | partial_coverage
          message      (str)
          unsupported  (list[str]) — categories not modeled by this guard
        """
        if not clauses:
            return self._unverifiable_result(
                message=(
                    "UNVERIFIABLE: No clauses provided. "
                    "An empty clause list cannot be proven consistent."
                ),
                unsupported=[],
                trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="No clauses provided to verify.",
                        inputs={"clauses": []},
                        output="UNSUPPORTED: empty input cannot be proven consistent.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        supported, unsupported = self._partition_clauses(clauses)
        unsupported_categories = sorted({c.category for c in unsupported})

        if not supported:
            return self._unverifiable_result(
                message=(
                    f"UNVERIFIABLE: None of the provided clause categories are modeled "
                    f"by ContradictionGuard. Supported: "
                    f"{', '.join(sorted(SUPPORTED_CATEGORIES))}. "
                    f"Received unsupported: {', '.join(unsupported_categories)}. "
                    f"Cannot prove consistency for inputs that are not modeled."
                ),
                unsupported=unsupported_categories,
                trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Clause categories partitioned: none are supported by this guard.",
                        inputs={"categories_received": unsupported_categories},
                        output=f"UNSUPPORTED: all categories unmodeled — {', '.join(unsupported_categories)}.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        s = Solver()
        contract_duration_months = Int("contract_duration_months")
        max_liability_usd = Int("max_liability_usd")
        s.add(contract_duration_months >= 0)
        s.add(max_liability_usd >= 0)

        duration_clauses = [c for c in supported if c.category.upper() == "DURATION"]
        encoded_duration, unmodeled_duration = self._encode_clauses(
            s, duration_clauses, contract_duration_months,
            self._add_clause_constraints,
        )
        liability_clauses = [c for c in supported if c.category.upper() == "LIABILITY"]
        encoded_liability, unmodeled_liability = self._encode_clauses(
            s, liability_clauses, max_liability_usd,
            self._add_clause_constraints,
        )
        encoded_supported = encoded_duration + encoded_liability
        unmodeled_supported = unmodeled_duration + unmodeled_liability

        # Build trace steps
        trace = []
        # Step 1: Rule identified
        supported_cats = sorted({c.category for c in supported})
        categories_text = " and ".join(supported_cats)
        trace.append(
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Partitioned clauses into supported and unsupported categories.",
                inputs={"categories_all": sorted({c.category for c in clauses})},
                output=(
                    f"Supported: {', '.join(supported_cats)}"
                    + (
                        f". Unsupported: {', '.join(unsupported_categories)}"
                        if unsupported_categories
                        else ""
                    )
                ),
                evidence_type=EVIDENCE_PARSED,
            )
        )
        # Step 2: Fact derived per supported clause. The solver encodes
        # ONLY text-derived operands; the caller's declared value is
        # recorded with an agreement flag and never enters the model
        # (issue #42, PR #45 review).
        clause_steps, disagreed_values = self._build_clause_fact_steps(
            encoded_supported
        )
        trace.extend(clause_steps)
        # Step 3: Ambiguity noted if partial coverage
        if unsupported_categories or unmodeled_supported > 0:
            trace.append(
                VerificationStep(
                    step=STEP_AMBIGUITY_NOTED,
                    description="Partial coverage detected — not all clauses could be modeled.",
                    inputs={
                        "unsupported_categories": unsupported_categories,
                        "unmodeled_count": unmodeled_supported,
                    },
                    output="PARTIAL_COVERAGE: verification result reflects incomplete modeling.",
                    evidence_type=EVIDENCE_UNSUPPORTED,
                )
            )

        return self._build_result(
            s=s,
            unsupported_categories=unsupported_categories,
            has_unsupported=bool(unsupported),
            unmodeled_supported=unmodeled_supported,
            categories_text=categories_text,
            trace=trace,
            disagreed_values=disagreed_values,
        )

    # ── private helpers ────────────────────────────────────────────────────────

    # Constraint phrase rules, ordered per category, as complete literal
    # patterns (no runtime concatenation — PR #45 review, ReDoS lint).
    # Each rule carries a VALID pattern (terminal-bounded phrase, a
    # separator that must not contain signs/digits/decimal points — so
    # "exactly - 30" cannot strip its sign, Greptile-executed — and a
    # complete ASCII unsigned integer token with terminal word boundary)
    # and a DETECTOR pattern (phrase + separator, no operand requirement)
    # used to count recognized occurrences.
    _CONSTRAINT_RULES = {
        "DURATION": [
            ("eq",
             re.compile(r"\bexactly\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bexactly\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("ge",
             re.compile(r"\bminimum\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bminimum\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("ge",
             re.compile(r"\bat\s+least\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bat\s+least\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("le",
             re.compile(r"\bmaximum\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bmaximum\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("le",
             re.compile(r"\bup\s+to\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bup\s+to\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
        ],
        "LIABILITY": [
            ("le",
             re.compile(r"\bcapped?\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bcapped?\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("le",
             re.compile(r"\bmaximum\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bmaximum\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("le",
             re.compile(r"\bmax\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bmax\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("ge",
             re.compile(r"\bpenalt(?:y|ies)\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bpenalt(?:y|ies)\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("ge",
             re.compile(r"\bfixed\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bfixed\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
            ("ge",
             re.compile(r"\bminimum\b[^+\-\d.]{0,20}(?<![-+])(?a:(\d+(?:[.,]\d+)*))(?!\w)"),
             re.compile(r"\bminimum\b[^+\-\d.]{0,20}(?=[+\-\d.])"),
             ),
        ],
    }

    @classmethod
    def _collect_constraints(cls, clause: Clause) -> "Optional[list]":
        """Collect the (op, operand) constraints a clause's text evidences.

        Returns a list of (op, operand) pairs — one per OCCURRENCE of
        every recognized phrase with a valid unsigned-integer operand —
        or None when the clause is unmodelable. EVERY recognized phrase
        occurrence must resolve to a valid ASCII integer operand: a
        malformed token ("1.5"), a sign ("- 30"), a decimal
        ("1,500"/"1.5"), or a NON-ASCII numeral ("٣٠") after a recognized
        phrase leaves that constraint uninterpretable, and interpreting
        only the resolvable subset would present a partial model as
        complete and can hide a conflict (PR #45 review, Greptile-
        executed R6/R8).
        """
        rules = cls._CONSTRAINT_RULES.get(clause.category.upper())
        if not rules:
            return None
        text = clause.text.lower()
        constraints = []
        for op, valid_pattern, detector_pattern in rules:
            # Detector counts recognized phrase occurrences; the valid
            # pattern resolves those with a well-formed operand. Any gap
            # means an uninterpretable constraint — fail closed the whole
            # clause rather than silently omitting it.
            occurrences = len(detector_pattern.findall(text))
            operands = [
                int(token)
                for token in valid_pattern.findall(text)
                if token.isdigit()
            ]
            if len(operands) != occurrences:
                return None
            constraints.extend((op, operand) for operand in operands)
        return constraints or None

    @staticmethod
    def _encode_clauses(s: Solver, clauses: List[Clause], var: object, constraint_fn) -> "tuple[List[Clause], int]":
        """Encode clauses with the category constraint function.

        Returns (encoded_clauses, unmodeled_count).
        """
        encoded: List[Clause] = []
        unmodeled = 0
        for clause in clauses:
            if constraint_fn(s, clause, var) == 0:
                encoded.append(clause)
            else:
                unmodeled += 1
        return encoded, unmodeled

    @staticmethod
    def _build_clause_fact_steps(encoded_supported: List[Clause]) -> "tuple[list, int]":
        """Build FACT_DERIVED trace steps for encoded clauses.

        The solver encodes ONLY the text-derived operands of recognized
        constraint phrases — never the caller's declared value. The
        declaration is recorded separately with an agreement flag: a
        differing declaration is disclosed, never silently encoded and
        never a solver input (issue #42, PR #45 review).
        Returns (steps, disagreement_count).
        """
        steps = []
        disagreements = 0
        for c in encoded_supported:
            constraints = ContradictionGuard._collect_constraints(c)
            agrees = any(operand == c.value for _, operand in constraints)
            if not agrees:
                disagreements += 1
            steps.append(
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description=f"Encoded Z3 constraint for {c.category} clause.",
                    inputs={
                        # Legacy contract field: the encoded operands are
                        # always text-derived under the operand-binding
                        # design, so the legacy value is constant — kept
                        # during a deprecation window for consumers that
                        # branch on it (PR #45 review, Greptile).
                        "value_provenance": "parsed_from_text",
                        "clause_text": c.text,
                        "clause_category": c.category,
                        "encoded_constraints": [
                            {"op": op, "operand": operand} for op, operand in constraints
                        ],
                        "caller_value": c.value,
                        "caller_value_agrees": agrees,
                    },
                    output=(
                        f"Z3 constraints added for '{c.text}' "
                        f"({', '.join(f'{op} {operand}' for op, operand in constraints)} from text; "
                        f"caller declared {c.value})"
                    ),
                    evidence_type=EVIDENCE_DETERMINISTIC,
                )
            )
        return steps, disagreements

    @staticmethod
    def _partition_clauses(clauses: List[Clause]):
        """Split clauses into supported and unsupported categories."""
        supported = [c for c in clauses if c.category.upper() in SUPPORTED_CATEGORIES]
        unsupported = [
            c for c in clauses if c.category.upper() not in SUPPORTED_CATEGORIES
        ]
        return supported, unsupported

    @classmethod
    def _add_clause_constraints(cls, s: Solver, clause: Clause, var: object) -> int:
        """
        Add the Z3 constraints evidenced by a supported clause (all
        recognized phrases with valid operands).

        Returns 1 if the clause is unmodeled (no valid phrase/operand, or
        any malformed recognized phrase), 0 otherwise.
        """
        constraints = cls._collect_constraints(clause)
        if not constraints:
            return 1
        for op, operand in constraints:
            if op == "eq":
                s.add(var == operand)
            elif op == "ge":
                s.add(var >= operand)
            else:
                s.add(var <= operand)
        return 0

    @staticmethod
    def _unverifiable_result(
        message: str, unsupported: list, trace: list = None
    ) -> dict:
        return {
            "verified": False,
            "status": "unverifiable",
            "message": message,
            "unsupported": unsupported,
            "verification_trace": trace or [],
        }

    @staticmethod
    def _sat_trace_step(has_partial_modeling: bool) -> VerificationStep:
        """Build conclusion trace step for a SAT solver outcome."""
        output = (
            "CONSISTENT: Z3 confirms no contradictions among modeled clauses."
            if not has_partial_modeling
            else "PARTIAL_COVERAGE: satisfiable among modeled clauses only."
        )
        return VerificationStep(
            step=STEP_CONCLUSION,
            description="Z3 solver evaluated: clauses are satisfiable.",
            inputs={"z3_result": "sat", "partial_coverage": has_partial_modeling},
            output=output,
            evidence_type=EVIDENCE_DETERMINISTIC,
        )

    @staticmethod
    def _z3_message(verified: bool, coverage_note: str, categories_text: str) -> str:
        """Build human-readable SAT message aligned to coverage status."""
        return (
            f"{'✅ CONSISTENT' if verified else '⚠️  PARTIAL COVERAGE'} "
            f"(modeled clauses): The {categories_text} clauses "
            f"{'are logically satisfiable' if verified else 'were not fully verified because modeling is incomplete'}"
            f".{coverage_note}"
        )

    @staticmethod
    def _build_result(
        s: Solver,
        unsupported_categories: list,
        has_unsupported: bool,
        unmodeled_supported: int,
        categories_text: str,
        trace: list = None,
        disagreed_values: int = 0,
    ) -> dict:
        """Evaluate Z3 solver and build the final result dict."""
        has_unmodeled_supported = unmodeled_supported > 0
        # The solver encodes ONLY text-derived operands (see
        # _build_clause_fact_steps) — the caller's declared value never
        # enters the model, so solver conclusions are purely
        # text-attributable. Disagreements are disclosed, not downgrade
        # triggers (PR #45 review: an unused caller declaration must not
        # suppress a text contradiction).
        has_partial_modeling = has_unsupported or has_unmodeled_supported

        coverage_note = ""
        if has_unsupported:
            coverage_note = (
                f" NOTE: clause(s) with unsupported categories "
                f"({', '.join(unsupported_categories)}) were excluded from the Z3 model."
            )
        if has_unmodeled_supported:
            coverage_note += (
                f" NOTE: {unmodeled_supported} supported-category clause(s) had "
                f"unrecognized keyword patterns and could not be encoded."
            )
        if disagreed_values:
            coverage_note += (
                f" NOTE: {disagreed_values} clause(s) have caller-declared "
                f"value(s) that disagree with the text-derived operand — the "
                f"declaration was NOT encoded; see the trace "
                f"(caller_value_agrees) for details."
            )

        result = s.check()

        if result == sat:
            status = "partial_coverage" if has_partial_modeling else "consistent"
            # partial_coverage is NOT verified=True — modeling was incomplete
            verified = status == "consistent"
            return {
                "verified": verified,
                "status": status,
                "message": ContradictionGuard._z3_message(
                    verified, coverage_note, categories_text
                ),
                "unsupported": unsupported_categories,
                "verification_trace": (trace or [])
                + [ContradictionGuard._sat_trace_step(has_partial_modeling)],
            }

        if result == unknown:
            return {
                "verified": False,
                "status": "unverifiable",
                "message": (
                    f"UNVERIFIABLE: Z3 returned unknown for the provided constraints "
                    f"(e.g. timeout or excessive complexity). "
                    f"Cannot determine consistency.{coverage_note}"
                ),
                "unsupported": unsupported_categories,
                "verification_trace": (trace or [])
                + [
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Z3 returned unknown — constraints too complex or timeout.",
                        inputs={"z3_result": "unknown"},
                        output="UNVERIFIABLE: Z3 could not determine satisfiability.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            }

        # result == unsat → contradiction. Every encoded constraint is
        # text-derived, so the conflict IS attributable to the text.
        return {
            "verified": False,
            "status": "contradiction",
            "message": (
                f"❌ CONTRADICTION: The DURATION/LIABILITY clauses are mutually "
                f"exclusive (e.g., penalty > liability cap, or min term > max "
                f"duration).{coverage_note}"
            ),
            "unsupported": unsupported_categories,
            "verification_trace": (trace or [])
            + [
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Z3 evaluated: clauses are mutually contradictory.",
                    inputs={"z3_result": "unsat"},
                    output="CONTRADICTION: no assignment satisfies all constraints.",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                )
            ],
        }
