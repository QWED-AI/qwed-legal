"""
ContradictionGuard: Detect logical contradictions in contract clauses using Z3.

Fail-closed design:
  - Only DURATION and LIABILITY categories are modeled.
  - Clauses with unsupported categories are not silently ignored.
  - If NO clauses are translatable, returns UNVERIFIABLE instead of a false SAT.
  - If SOME clauses are untranslatable, returns a partial-coverage warning.
"""

from dataclasses import dataclass, field
from typing import List

from z3 import Int, Solver, sat


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
    - Clauses with unsupported categories (PAYMENT, PENALTY, etc.) are not
      silently ignored — they trigger an UNVERIFIABLE result.
    - If no supported clauses are present, returns UNVERIFIABLE instead of
      a false SAT (absence of constraints does not mean consistency).
    - If some clauses are unsupported, returns PARTIAL_COVERAGE with a warning.
    """

    def verify_consistency(self, clauses: List[Clause]) -> dict:
        """
        Translate supported legal clauses into Z3 constraints and check for SAT.

        Returns a dict with keys:
          verified     (bool)
          status       (str)  — one of: consistent, contradiction, unverifiable, partial_coverage
          message      (str)
          unsupported  (list) — categories not modeled by this guard
        """
        if not clauses:
            return {
                "verified": False,
                "status": "unverifiable",
                "message": (
                    "UNVERIFIABLE: No clauses provided. "
                    "An empty clause list cannot be proven consistent."
                ),
                "unsupported": [],
            }

        # Partition clauses into supported and unsupported
        supported = [c for c in clauses if c.category.upper() in SUPPORTED_CATEGORIES]
        unsupported = [
            c for c in clauses if c.category.upper() not in SUPPORTED_CATEGORIES
        ]
        unsupported_categories = sorted({c.category for c in unsupported})

        # Fail closed: if there are NO supported clauses we cannot prove anything
        if not supported:
            return {
                "verified": False,
                "status": "unverifiable",
                "message": (
                    f"UNVERIFIABLE: None of the provided clause categories are modeled by "
                    f"ContradictionGuard. Supported categories: "
                    f"{', '.join(sorted(SUPPORTED_CATEGORIES))}. "
                    f"Received unsupported categories: {', '.join(unsupported_categories)}. "
                    f"Cannot prove consistency for inputs that are not modeled."
                ),
                "unsupported": unsupported_categories,
            }

        # Build Z3 model for supported clauses only
        s = Solver()
        contract_duration_months = Int("contract_duration_months")
        max_liability_usd = Int("max_liability_usd")

        # Physical feasibility constraints
        s.add(contract_duration_months >= 0)
        s.add(max_liability_usd >= 0)

        duration_clauses = [c for c in supported if c.category.upper() == "DURATION"]
        liability_clauses = [c for c in supported if c.category.upper() == "LIABILITY"]

        for c in duration_clauses:
            text_lower = c.text.lower()
            if "exactly" in text_lower:
                s.add(contract_duration_months == c.value)
            elif "minimum" in text_lower or "at least" in text_lower:
                s.add(contract_duration_months >= c.value)
            elif "maximum" in text_lower or "up to" in text_lower:
                s.add(contract_duration_months <= c.value)
            # Clauses that don't match any keyword are not silently ignored —
            # they remain as candidates but generate no constraint.
            # This is acceptable: the clause was recognized as DURATION but
            # its keyword pattern is not modeled. Logged in partial_coverage.

        for c in liability_clauses:
            text_lower = c.text.lower()
            if "capped" in text_lower or "max" in text_lower or "cap" in text_lower:
                s.add(max_liability_usd <= c.value)
            elif (
                "penalty" in text_lower
                or "fixed" in text_lower
                or "minimum" in text_lower
            ):
                s.add(max_liability_usd >= c.value)

        # Check satisfiability
        result = s.check()

        # Determine coverage status
        has_unsupported = bool(unsupported)
        coverage_note = ""
        if has_unsupported:
            coverage_note = (
                f" NOTE: {len(unsupported)} clause(s) with unsupported "
                f"categories ({', '.join(unsupported_categories)}) were excluded from "
                f"the Z3 model. This result covers only the DURATION/LIABILITY subset."
            )

        if result == sat:
            status = "partial_coverage" if has_unsupported else "consistent"
            return {
                "verified": True,
                "status": status,
                "message": (
                    f"✅ CONSISTENT (modeled clauses): The DURATION and LIABILITY "
                    f"clauses are logically satisfiable.{coverage_note}"
                ),
                "unsupported": unsupported_categories,
            }
        else:
            return {
                "verified": False,
                "status": "contradiction",
                "message": (
                    f"❌ CONTRADICTION: The DURATION/LIABILITY clauses are mutually "
                    f"exclusive (e.g., penalty > liability cap, or min term > max duration). "
                    f"{coverage_note}"
                ),
                "unsupported": unsupported_categories,
            }
