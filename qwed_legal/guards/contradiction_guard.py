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
            self._add_duration_constraint,
        )
        liability_clauses = [c for c in supported if c.category.upper() == "LIABILITY"]
        encoded_liability, unmodeled_liability = self._encode_clauses(
            s, liability_clauses, max_liability_usd,
            self._add_liability_constraint,
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

    # Shared operand grammar: a complete unsigned integer token. Signs
    # ("-30"), decimals ("1.5"), and formatted numbers ("1,500") are
    # rejected outright — the clause stays unmodeled rather than encoding
    # a silently altered value (PR #45 review, CodeRabbit).
    _OPERAND = r"(?<![-+])(\d+(?:[.,]\d+)*)"

    # Constraint phrase rules, ordered per category. Each pattern binds a
    # recognized phrase to the numeric operand ADJACENT to it — the operand
    # is what gets encoded into Z3 (issue #42, PR #45 review).
    _CONSTRAINT_RULES = {
        "DURATION": [
            (re.compile(r"\bexactly\D{0,20}" + _OPERAND), "eq"),
            (re.compile(r"\bminimum\D{0,20}" + _OPERAND), "ge"),
            (re.compile(r"\bat\s+least\D{0,20}" + _OPERAND), "ge"),
            (re.compile(r"\bmaximum\D{0,20}" + _OPERAND), "le"),
            (re.compile(r"\bup\s+to\D{0,20}" + _OPERAND), "le"),
        ],
        "LIABILITY": [
            (re.compile(r"\bcapped?\D{0,20}" + _OPERAND), "le"),
            (re.compile(r"\bmaximum\D{0,20}" + _OPERAND), "le"),
            (re.compile(r"\bmax\D{0,20}" + _OPERAND), "le"),
            (re.compile(r"\bpenalt(?:y|ies)\D{0,20}" + _OPERAND), "ge"),
            (re.compile(r"\bfixed\D{0,20}" + _OPERAND), "ge"),
            (re.compile(r"\bminimum\D{0,20}" + _OPERAND), "ge"),
        ],
    }

    @classmethod
    def _match_constraint(cls, clause: Clause) -> "Optional[tuple]":
        """Match the recognized constraint phrase and its numeric operand.

        Returns (op, operand) or None when no supported phrase with an
        adjacent number is present — such clauses stay unmodeled rather
        than being encoded from an unevidenced quantity.
        """
        rules = cls._CONSTRAINT_RULES.get(clause.category.upper())
        if not rules:
            return None
        text = clause.text.lower()
        for pattern, op in rules:
            match = pattern.search(text)
            if match:
                token = match.group(1)
                if not token.isdigit():
                    # Decimal or formatted numbers are unsupported
                    # operands — fail closed rather than encoding a
                    # silently altered value ("1.5" → 1, "1,500" → 1).
                    return None
                return op, int(token)
        return None

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

        The solver encodes ONLY the text-derived operand of the matched
        constraint phrase — never the caller's declared value. The
        declaration is recorded separately with an agreement flag: a
        differing declaration is disclosed, never silently encoded and
        never a solver input (issue #42, PR #45 review).
        Returns (steps, disagreement_count).
        """
        steps = []
        disagreements = 0
        for c in encoded_supported:
            matched = ContradictionGuard._match_constraint(c)
            operand = matched[1]
            agrees = c.value == operand
            if not agrees:
                disagreements += 1
            steps.append(
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description=f"Encoded Z3 constraint for {c.category} clause.",
                    inputs={
                        "clause_text": c.text,
                        "clause_category": c.category,
                        "encoded_operand": operand,
                        "caller_value": c.value,
                        "caller_value_agrees": agrees,
                    },
                    output=(
                        f"Z3 constraint added for '{c.text}' "
                        f"(operand={operand} from text; caller declared {c.value})"
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
    def _add_duration_constraint(cls, s: Solver, clause: Clause, var: object) -> int:
        """
        Add a Z3 constraint for a DURATION clause.
        Returns 1 if the clause phrase is not modeled (unmodeled), 0 otherwise.
        """
        matched = cls._match_constraint(clause)
        if matched is None:
            return 1  # clause recognized as DURATION but phrase/operand not modeled
        op, operand = matched
        if op == "eq":
            s.add(var == operand)
        elif op == "ge":
            s.add(var >= operand)
        else:
            s.add(var <= operand)
        return 0

    @classmethod
    def _add_liability_constraint(cls, s: Solver, clause: Clause, var: object) -> int:
        """
        Add a Z3 constraint for a LIABILITY clause.
        Returns 1 if the clause phrase is not modeled (unmodeled), 0 otherwise.
        """
        matched = cls._match_constraint(clause)
        if matched is None:
            return 1  # clause recognized as LIABILITY but phrase/operand not modeled
        op, operand = matched
        if op == "le":
            s.add(var <= operand)
        else:
            s.add(var >= operand)
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
