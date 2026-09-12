"""
ClauseGuard: Detect contradictory clauses in contracts using limited heuristics.

Supports optional typed Z3 constraints for power users who model legal meaning
explicitly outside this guard.
"""

from dataclasses import dataclass, field
import re
from typing import Any, List, Optional, Tuple

from z3 import BoolRef, Solver, sat, unknown, unsat

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_AMBIGUITY_NOTED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_INFERRED,
    EVIDENCE_UNSUPPORTED,
)


@dataclass
class ClauseResult:
    """Result of clause consistency check."""

    consistent: bool
    conflicts: List[Tuple[int, int, str]]  # (clause_idx1, clause_idx2, reason)
    message: str
    status: str = "consistent"
    # status values:
    #   "consistent"                  — heuristic checks found no conflicts
    #   "contradiction"               — at least one conflict detected
    #   "heuristic_pass_limited"      — no propositions extracted; guard has no coverage
    #                                   consistent=False but NOT a detected contradiction
    verification_trace: list = field(default_factory=list)


class ClauseGuard:
    """
    Detect contradictory clauses in legal contracts using limited heuristics.

    Catches some common LLM errors like:
    - Contradictory termination clauses
    - Conflicting obligation timelines
    - Mutually exclusive conditions

    Example:
        >>> guard = ClauseGuard()
        >>> result = guard.check_consistency([
        ...     "Seller may terminate with 30 days notice",
        ...     "Neither party may terminate before 90 days",
        ... ])
        >>> print(result.consistent)  # False - clauses conflict
    """

    # Max chars between a context word and its day-expression for the
    # proximity fallback in _extract_days (issue #41).
    _CONTEXT_WINDOW = 40

    def __init__(self):
        """Initialize ClauseGuard."""

    def check_consistency(self, clauses: List[str]) -> ClauseResult:
        """
        Check if a list of contract clauses are logically consistent.

        Args:
            clauses: List of clause text strings

        Returns:
            ClauseResult with consistency status and any detected conflicts
        """
        if len(clauses) < 2:
            return ClauseResult(
                consistent=True,
                conflicts=[],
                message="Single clause - no conflicts possible.",
                verification_trace=[
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Fewer than two clauses provided — no pair to compare.",
                        inputs={"clause_count": len(clauses)},
                        output="NO CONFLICT POSSIBLE (single clause)",
                        evidence_type=EVIDENCE_INFERRED,
                    )
                ],
            )

        # Extract logical propositions from clauses
        propositions = self._extract_propositions(clauses)

        # Check for conflicts using supported heuristics
        conflicts = self._find_conflicts(propositions)

        # Count how many propositions had any extractable content.
        # If none of the clauses triggered a recognizable proposition, the
        # heuristic had no coverage — returning "VERIFIED" would be misleading.
        covered = sum(
            1
            for p in propositions
            if p["can_terminate"]
            or p["termination_notice_days"] is not None
            or p["min_term_days"] is not None
            or p["is_exclusive"]
        )
        ambiguous = [p for p in propositions if p["ambiguous_termination_reference"]]
        has_ambiguous = len(ambiguous) > 0

        rule_step = VerificationStep(
            step=STEP_RULE_IDENTIFIED,
            description="Extracted heuristic propositions from clause text.",
            inputs={"clause_count": len(clauses), "covered_propositions": covered},
            output=(
                "Heuristic patterns: termination, notice period, min-term, exclusivity."
            ),
            evidence_type=EVIDENCE_INFERRED,
        )

        if not conflicts:
            if covered == 0 or has_ambiguous:
                caveat = (
                    "No heuristic propositions were extracted from the provided clauses."
                    if covered == 0
                    else (
                        "Some clauses contain recognised heuristic propositions, but "
                        "one or more clauses mention termination-related language "
                        "ambiguously rather than as an operative termination right "
                        "or restriction."
                    )
                )
                return ClauseResult(
                    consistent=False,
                    conflicts=[],
                    status="heuristic_pass_limited",
                    message=(
                        f"HEURISTIC_PASS (LIMITED COVERAGE): {caveat} ClauseGuard only "
                        "recognises termination, notice period, min-term, and exclusivity "
                        "patterns. The clauses may be consistent, but this guard cannot "
                        "confirm it — downstream consumers must not treat this as "
                        "verified consistency."
                    ),
                    verification_trace=[
                        rule_step,
                        VerificationStep(
                            step=STEP_AMBIGUITY_NOTED,
                            description="Coverage is limited or ambiguous — cannot confirm consistency.",
                            inputs={"covered": covered, "has_ambiguous": has_ambiguous},
                            output="UNSUPPORTED: limited heuristic coverage, not verified.",
                            evidence_type=EVIDENCE_UNSUPPORTED,
                        ),
                    ],
                )
            return ClauseResult(
                consistent=True,
                conflicts=[],
                status="consistent",
                message=(
                    "HEURISTIC_PASS: Supported clause checks (termination, notice, "
                    "min-term, exclusivity) found no conflicts. This is a heuristic "
                    "result — not deterministic legal verification."
                ),
                verification_trace=[
                    rule_step,
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="No conflicts found by supported heuristic checks.",
                        inputs={"conflict_count": 0},
                        output="NO CONFLICT DETECTED (heuristic, not proof)",
                        evidence_type=EVIDENCE_INFERRED,
                    ),
                ],
            )

        conflict_msgs = []
        for idx1, idx2, reason in conflicts:
            conflict_msgs.append(
                f"  - Clause {idx1 + 1} vs Clause {idx2 + 1}: {reason}"
            )

        return ClauseResult(
            consistent=False,
            conflicts=conflicts,
            status="contradiction",
            message=(
                f"WARNING: {len(conflicts)} potential conflict(s) detected:\n"
                + "\n".join(conflict_msgs)
            ),
            verification_trace=[
                rule_step,
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Heuristic checks detected potential conflict(s).",
                    inputs={"conflict_count": len(conflicts)},
                    output=f"POTENTIAL CONFLICT(S): {len(conflicts)} (heuristic, not proof)",
                    evidence_type=EVIDENCE_INFERRED,
                ),
            ],
        )

    def _extract_propositions(self, clauses: List[str]) -> List[dict]:
        """Extract supported heuristic propositions from clause text."""
        propositions = []

        for clause in clauses:
            lower = clause.lower()
            can_terminate = self._has_operative_termination(lower)
            prop = {
                "text": clause,
                "can_terminate": can_terminate,
                "ambiguous_termination_reference": (
                    self._mentions_termination(lower) and not can_terminate
                ),
                "termination_notice_days": self._extract_days(lower, "notice"),
                "min_term_days": self._extract_days(lower, "before"),
                "is_exclusive": "exclusive" in lower or "only" in lower,
                "is_prohibition": any(
                    w in lower for w in ["may not", "cannot", "neither", "shall not"]
                ),
                "is_permission": any(w in lower for w in ["may ", "can ", "allowed"]),
                "parties": self._extract_parties(lower),
            }
            propositions.append(prop)

        return propositions

    def _find_conflicts(self, propositions: List[dict]) -> List[Tuple[int, int, str]]:
        """Find logical conflicts between clauses."""
        conflicts = []

        for i, prop1 in enumerate(propositions):
            for j, prop2 in enumerate(propositions):
                if j <= i:
                    continue

                conflict = self._check_termination_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))
                    continue

                conflict = self._check_permission_prohibition_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))
                    continue

                conflict = self._check_exclusivity_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))

        return conflicts

    def _check_termination_conflict(self, prop1: dict, prop2: dict) -> Optional[str]:
        """Check for conflicting termination clauses."""
        if prop1.get("can_terminate") and prop2.get("min_term_days"):
            notice = prop1.get("termination_notice_days", 0)
            min_term = prop2.get("min_term_days", 0)
            if notice and min_term and notice < min_term:
                return (
                    f"Termination notice ({notice} days) conflicts with "
                    f"minimum term ({min_term} days)"
                )

        if prop2.get("can_terminate") and prop1.get("min_term_days"):
            notice = prop2.get("termination_notice_days", 0)
            min_term = prop1.get("min_term_days", 0)
            if notice and min_term and notice < min_term:
                return (
                    f"Termination notice ({notice} days) conflicts with "
                    f"minimum term ({min_term} days)"
                )

        return None

    def _check_permission_prohibition_conflict(
        self, prop1: dict, prop2: dict
    ) -> Optional[str]:
        """Check for permission vs prohibition conflicts."""
        if prop1.get("is_permission") and prop2.get("is_prohibition"):
            if prop1.get("can_terminate") and "terminate" in prop2["text"].lower():
                return (
                    "Permission to terminate conflicts with prohibition on termination"
                )

        if prop2.get("is_permission") and prop1.get("is_prohibition"):
            if prop2.get("can_terminate") and "terminate" in prop1["text"].lower():
                return (
                    "Permission to terminate conflicts with prohibition on termination"
                )

        return None

    def _check_exclusivity_conflict(self, prop1: dict, prop2: dict) -> Optional[str]:
        """Check for exclusivity conflicts."""
        if prop1.get("is_exclusive") and prop2.get("is_exclusive"):
            parties1 = prop1.get("parties", set())
            parties2 = prop2.get("parties", set())
            if parties1 & parties2:
                return "Multiple exclusive rights granted to same party"

        return None

    def _mentions_termination(self, text: str) -> bool:
        """Return True when text contains termination-related vocabulary."""
        terms = ["terminate", "termination", "cancel", "end the agreement"]
        return any(t in text for t in terms)

    def _has_operative_termination(self, text: str) -> bool:
        """
        Check whether text states an operative termination right or restriction.

        Raw keyword presence is not enough. For example, "may review the
        termination process" mentions termination, but does not grant a right to
        terminate. We only extract a termination proposition when modal/legal
        language is tied directly to an operative verb such as terminate/cancel.
        """
        operative_patterns = [
            r"\b(?:may|can|shall|must)\s+(?:not\s+)?(?:terminate|cancel)\b",
            r"\bneither\s+party\s+may\s+(?:terminate|cancel)\b",
            r"\b(?:allowed|entitled)\s+to\s+(?:terminate|cancel)\b",
            r"\bright\s+to\s+(?:terminate|cancel)\b",
            r"\b(?:may|can|shall|must)\s+(?:not\s+)?end\s+the\s+agreement\b",
        ]
        return any(re.search(pattern, text) for pattern in operative_patterns)

    def _extract_days(self, text: str, context: str) -> Optional[int]:
        """Extract number of days from text near a context word.

        Association strength, strongest first: directional patterns (day
        count directly attached to the context word, singular or plural),
        a linked pattern (context + linker word + duration, e.g. "notice
        within 30 days"), then a proximity fallback: the day-expression
        CLOSEST to the context word within _CONTEXT_WINDOW characters.
        ClauseGuard is a heuristic guard — broader extraction is
        coverage, not proof (issue #41).
        """
        if context not in text:
            return None

        day_expr = r"(\d+)\s*(?:calendar\s+|business\s+)?days?"
        for pattern in (
            rf"{day_expr}\s*{context}",
            rf"{context}\s*{day_expr}",
        ):
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))

        # Linked: a linker word binds the duration to the context even
        # when other durations sit nearby ("10 days cure; notice within
        # 30 days" must resolve to 30 — PR #47 review, Greptile). Multiple
        # linked durations with different values are ambiguous and stay
        # unresolved rather than picking the first in document order
        # (PR #47 review, Greptile R2-executed).
        linked_re = re.compile(
            rf"{context}\s*(?:within|of|from|after|no\s+later\s+than|following)\s*{day_expr}"
        )
        linked_values = {int(m.group(1)) for m in linked_re.finditer(text)}
        if linked_values:
            return linked_values.pop() if len(linked_values) == 1 else None

        return self._nearest_days(text, context, day_expr)

    def _nearest_days(self, text: str, context: str, day_expr: str) -> Optional[int]:
        """Proximity fallback: rank day-expression candidates by the gap
        between the context word and the expression (inclusive of
        _CONTEXT_WINDOW); a tie at the minimum gap between different
        values is ambiguous and stays unresolved."""
        context_re = re.compile(rf"\b{re.escape(context)}\b")
        candidates = []
        for ctx_match in context_re.finditer(text):
            for day_match in re.finditer(day_expr, text):
                if ctx_match.end() <= day_match.start():
                    gap = day_match.start() - ctx_match.end()
                elif day_match.end() <= ctx_match.start():
                    gap = ctx_match.start() - day_match.end()
                else:
                    # Overlapping spans: direct attachment already handled
                    # by the directional patterns above.
                    continue
                if gap <= self._CONTEXT_WINDOW:
                    candidates.append((gap, int(day_match.group(1))))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        best_values = {value for gap, value in candidates if gap == candidates[0][0]}
        if len(best_values) == 1:
            return best_values.pop()
        return None  # ambiguous association

    def _extract_parties(self, text: str) -> set:
        """Extract party names from clause."""
        parties = set()
        for party in [
            "seller",
            "buyer",
            "vendor",
            "customer",
            "licensee",
            "licensor",
            "party",
            "parties",
            "company",
            "contractor",
        ]:
            if party in text:
                parties.add(party)
        return parties

    def verify_using_z3(self, constraints: List[Any]) -> ClauseResult:
        """
        Advanced: Verify already-modeled Z3 constraints.

        This method does not parse free-form legal text. Callers must provide
        explicit Z3 expressions that already encode the legal meaning they want
        checked.

        Args:
            constraints: List of Z3 expressions

        Returns:
            ClauseResult indicating if constraints are satisfiable
        """
        if not constraints:
            return ClauseResult(
                consistent=False,
                conflicts=[],
                message=(
                    "UNVERIFIABLE: verify_using_z3 requires explicit Z3 "
                    "constraint expressions. Empty input cannot be proven."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="No Z3 constraints provided.",
                        inputs={"constraint_count": 0},
                        output="UNSUPPORTED: empty constraint input.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        invalid_positions = [
            index + 1
            for index, constraint in enumerate(constraints)
            if not isinstance(constraint, BoolRef)
        ]
        if invalid_positions:
            positions = ", ".join(str(position) for position in invalid_positions)
            return ClauseResult(
                consistent=False,
                conflicts=[],
                message=(
                    "UNVERIFIABLE: verify_using_z3 only accepts explicit Z3 "
                    "Boolean expressions. Unsupported constraint(s) at "
                    f"position(s): {positions}."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="One or more inputs are not Z3 Boolean expressions.",
                        inputs={"invalid_positions": invalid_positions},
                        output="UNSUPPORTED: non-Boolean constraint input.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        solver = Solver()
        solver.add(*constraints)
        result = solver.check()

        if result == sat:
            return ClauseResult(
                consistent=True,
                conflicts=[],
                message="VERIFIED: Provided Z3 constraints are satisfiable.",
                verification_trace=[
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Z3 evaluated explicit constraints as satisfiable.",
                        inputs={"z3_result": "sat", "constraint_count": len(constraints)},
                        output="SATISFIABLE: no contradiction among provided constraints.",
                        evidence_type=EVIDENCE_DETERMINISTIC,
                    )
                ],
            )

        if result == unsat:
            return ClauseResult(
                consistent=False,
                conflicts=[],
                message=(
                    "CONTRADICTION: Provided Z3 constraints are "
                    "unsatisfiable (contradiction exists)."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Z3 evaluated explicit constraints as unsatisfiable.",
                        inputs={"z3_result": "unsat", "constraint_count": len(constraints)},
                        output="CONTRADICTION: no assignment satisfies all constraints.",
                        evidence_type=EVIDENCE_DETERMINISTIC,
                    )
                ],
            )

        if result == unknown:
            return ClauseResult(
                consistent=False,
                conflicts=[],
                message="UNVERIFIABLE: Z3 returned unknown for the provided constraints.",
                verification_trace=[
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Z3 returned unknown — cannot determine satisfiability.",
                        inputs={"z3_result": "unknown"},
                        output="UNSUPPORTED: Z3 could not determine satisfiability.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        return ClauseResult(
            consistent=False,
            conflicts=[],
            message="UNVERIFIABLE: Z3 returned an unsupported satisfiability state.",
            verification_trace=[
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Z3 returned an unsupported satisfiability state.",
                    inputs={"z3_result": str(result)},
                    output="UNSUPPORTED: unexpected Z3 state.",
                    evidence_type=EVIDENCE_UNSUPPORTED,
                )
            ],
        )
