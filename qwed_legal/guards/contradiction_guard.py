"""
ContradictionGuard: Detect logical contradictions in contract clauses using Z3.

Fail-closed design:
  - Only DURATION and LIABILITY categories are modeled.
  - Unsupported categories are never silently ignored — UNVERIFIABLE is returned.
  - Supported clauses with unmodeled keywords (no constraint added) are tracked
    and cause partial_coverage — never verified=True for partial inputs.
  - Z3 unknown result → UNVERIFIABLE (not a false contradiction).
"""

from dataclasses import dataclass, field
from typing import List

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

        unmodeled_supported = 0
        encoded_supported = []

        duration_clauses = [c for c in supported if c.category.upper() == "DURATION"]
        for clause in duration_clauses:
            add_result = self._add_duration_constraint(s, clause, contract_duration_months)
            if add_result == 0:
                encoded_supported.append(clause)
            else:
                unmodeled_supported += 1

        liability_clauses = [c for c in supported if c.category.upper() == "LIABILITY"]
        for clause in liability_clauses:
            add_result = self._add_liability_constraint(s, clause, max_liability_usd)
            if add_result == 0:
                encoded_supported.append(clause)
            else:
                unmodeled_supported += 1

        # Build trace steps
        trace = []
        # Step 1: Rule identified
        supported_cats = sorted({c.category for c in supported})
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
        # Step 2: Fact derived per supported clause
        for c in encoded_supported:
            trace.append(
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description=f"Encoded Z3 constraint for {c.category} clause.",
                    inputs={
                        "clause_text": c.text,
                        "clause_category": c.category,
                        "clause_value": c.value,
                    },
                    output=f"Z3 constraint added for '{c.text}' (value={c.value})",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                )
            )
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
            trace=trace,
        )

    # ── private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _partition_clauses(clauses: List[Clause]):
        """Split clauses into supported and unsupported categories."""
        supported = [c for c in clauses if c.category.upper() in SUPPORTED_CATEGORIES]
        unsupported = [
            c for c in clauses if c.category.upper() not in SUPPORTED_CATEGORIES
        ]
        return supported, unsupported

    @staticmethod
    def _add_duration_constraint(s: Solver, clause: Clause, var: object) -> int:
        """
        Add a Z3 constraint for a DURATION clause.
        Returns 1 if the clause keyword is not modeled (unmodeled), 0 otherwise.
        """
        text = clause.text.lower()
        if "exactly" in text:
            s.add(var == clause.value)
        elif "minimum" in text or "at least" in text:
            s.add(var >= clause.value)
        elif "maximum" in text or "up to" in text:
            s.add(var <= clause.value)
        else:
            return 1  # clause recognized as DURATION but keyword not modeled
        return 0

    @staticmethod
    def _add_liability_constraint(s: Solver, clause: Clause, var: object) -> int:
        """
        Add a Z3 constraint for a LIABILITY clause.
        Returns 1 if the clause keyword is not modeled (unmodeled), 0 otherwise.
        """
        text = clause.text.lower()
        if "capped" in text or "max" in text or "cap" in text:
            s.add(var <= clause.value)
        elif "penalty" in text or "fixed" in text or "minimum" in text:
            s.add(var >= clause.value)
        else:
            return 1  # clause recognized as LIABILITY but keyword not modeled
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
        evidence = (
            EVIDENCE_DETERMINISTIC if not has_partial_modeling else EVIDENCE_UNSUPPORTED
        )
        return VerificationStep(
            step=STEP_CONCLUSION,
            description="Z3 solver evaluated: clauses are satisfiable.",
            inputs={"z3_result": "sat", "partial_coverage": has_partial_modeling},
            output=output,
            evidence_type=evidence,
        )

    @staticmethod
    def _z3_message(verified: bool, coverage_note: str) -> str:
        """Build human-readable SAT message aligned to coverage status."""
        return (
            f"{'✅ CONSISTENT' if verified else '⚠️  PARTIAL COVERAGE'} "
            f"(modeled clauses): The DURATION and LIABILITY clauses "
            f"{'are logically satisfiable' if verified else 'were not fully verified because modeling is incomplete'}"
            f".{coverage_note}"
        )

    @staticmethod
    def _build_result(
        s: Solver,
        unsupported_categories: list,
        has_unsupported: bool,
        unmodeled_supported: int,
        trace: list = None,
    ) -> dict:
        """Evaluate Z3 solver and build the final result dict."""
        has_unmodeled_supported = unmodeled_supported > 0
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

        result = s.check()

        if result == sat:
            status = "partial_coverage" if has_partial_modeling else "consistent"
            # partial_coverage is NOT verified=True — modeling was incomplete
            verified = status == "consistent"
            return {
                "verified": verified,
                "status": status,
                "message": ContradictionGuard._z3_message(verified, coverage_note),
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

        # result == unsat → contradiction
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
