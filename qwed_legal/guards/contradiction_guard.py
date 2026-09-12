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
    EVIDENCE_INFERRED,
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
        # Step 2: Fact derived per supported clause — with value
        # provenance. A caller_asserted value means Z3 "proves"
        # consistency of a number the caller invented, not one parsed
        # from the text (issue #42).
        clause_steps, caller_asserted_values = self._build_clause_fact_steps(
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
            caller_asserted_values=caller_asserted_values,
        )

    # ── private helpers ────────────────────────────────────────────────────────

    # Constraint phrase rules, ordered per category. Each pattern binds a
    # recognized phrase to the numeric operand ADJACENT to it — the operand
    # is what gets encoded into Z3 AND what value_provenance compares
    # against. A number elsewhere in the text is not the term value
    # (issue #42, PR #45 review).
    _CONSTRAINT_RULES = {
        "DURATION": [
            (re.compile(r"\bexactly\D{0,20}(\d+)"), "eq"),
            (re.compile(r"\bminimum\D{0,20}(\d+)"), "ge"),
            (re.compile(r"\bat\s+least\D{0,20}(\d+)"), "ge"),
            (re.compile(r"\bmaximum\D{0,20}(\d+)"), "le"),
            (re.compile(r"\bup\s+to\D{0,20}(\d+)"), "le"),
        ],
        "LIABILITY": [
            (re.compile(r"\bcapped?\D{0,20}(\d+)"), "le"),
            (re.compile(r"\bmaximum\D{0,20}(\d+)"), "le"),
            (re.compile(r"\bmax\D{0,20}(\d+)"), "le"),
            (re.compile(r"\bpenalt(?:y|ies)\D{0,20}(\d+)"), "ge"),
            (re.compile(r"\bfixed\D{0,20}(\d+)"), "ge"),
            (re.compile(r"\bminimum\D{0,20}(\d+)"), "ge"),
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
                return op, int(match.group(1))
        return None

    @classmethod
    def _value_provenance(cls, clause: Clause) -> str:
        """Classify where a clause's encoded value came from.

        ``parsed_from_text`` only when the clause value IS the numeric
        operand bound to the recognized constraint phrase;
        ``caller_asserted`` otherwise — the Z3 model then encodes a
        number the caller supplied, not one evidenced by the text
        (issue #42, PR #45 review).
        """
        matched = cls._match_constraint(clause)
        if matched is not None and matched[1] == clause.value:
            return "parsed_from_text"
        return "caller_asserted"

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

        Returns (steps, caller_asserted_count). A caller_asserted value
        means the constraint encodes a number the caller supplied, not
        one parsed from the text — such steps are EVIDENCE_INFERRED
        (non-proof), never DETERMINISTIC (issue #42, PR #45 review).
        """
        steps = []
        caller_asserted = 0
        for c in encoded_supported:
            provenance = ContradictionGuard._value_provenance(c)
            if provenance == "caller_asserted":
                caller_asserted += 1
            steps.append(
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description=f"Encoded Z3 constraint for {c.category} clause.",
                    inputs={
                        "clause_text": c.text,
                        "clause_category": c.category,
                        "clause_value": c.value,
                        "value_provenance": provenance,
                    },
                    output=(
                        f"Z3 constraint added for '{c.text}' (value={c.value}, "
                        f"value_provenance={provenance})"
                    ),
                    evidence_type=(
                        EVIDENCE_DETERMINISTIC
                        if provenance == "parsed_from_text"
                        else EVIDENCE_INFERRED
                    ),
                )
            )
        return steps, caller_asserted

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
        caller_asserted_values: int = 0,
    ) -> dict:
        """Evaluate Z3 solver and build the final result dict."""
        has_unmodeled_supported = unmodeled_supported > 0
        # Caller-asserted values make the constraint set contain numbers
        # not evidenced by the text — a SAT result over them is NOT a
        # verified consistency proof (issue #42, PR #45 review).
        has_caller_asserted = caller_asserted_values > 0
        has_partial_modeling = (
            has_unsupported or has_unmodeled_supported or has_caller_asserted
        )

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
        if has_caller_asserted:
            coverage_note += (
                f" NOTE: {caller_asserted_values} encoded clause value(s) were "
                f"caller-asserted (not found in the clause text) — the consistency "
                f"result covers caller-supplied numbers, not text-evidenced ones "
                f"(see value_provenance in the trace)."
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

        # result == unsat → contradiction. A contradiction involving
        # caller-asserted values proves the INVENTED numbers conflict —
        # it says nothing about the text, so it is UNVERIFIABLE, never a
        # deterministic contradiction (PR #45 review, CodeRabbit).
        if has_caller_asserted:
            return {
                "verified": False,
                "status": "unverifiable",
                "message": (
                    f"UNVERIFIABLE: The encoded constraints are mutually "
                    f"exclusive, but {caller_asserted_values} clause value(s) "
                    f"were caller-asserted (not found in the clause text) — "
                    f"the conflict cannot be attributed to the contract text. "
                    f"Supply values that appear in the text.{coverage_note}"
                ),
                "unsupported": unsupported_categories,
                "verification_trace": (trace or [])
                + [
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Z3 evaluated: constraints conflict, but caller-asserted values participated.",
                        inputs={
                            "z3_result": "unsat",
                            "caller_asserted_values": caller_asserted_values,
                        },
                        output=(
                            "UNVERIFIABLE: UNSAT over caller-asserted values — "
                            "not attributable to the clause text."
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            }

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
