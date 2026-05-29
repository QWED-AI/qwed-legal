"""
QWED-Legal shared verification models.

VerificationStep is the atomic unit of a verification_trace — a structured,
auditable record of every decision made during a guard's verification run.

Key distinction:
  - verification_trace is NOT a narrative explanation.
  - Each step has an evidence_type that explicitly classifies HOW the output
    was derived: DETERMINISTIC, PARSED, INFERRED, HEURISTIC, or UNSUPPORTED.
  - A step with evidence_type=PARSED is NOT proof. It means "we read/matched
    this from structure" — authority or correctness is not claimed.
  - Only DETERMINISTIC steps represent actual mathematical/logical proof.
"""

from dataclasses import dataclass
from typing import Any, Dict

# ── Step type constants ────────────────────────────────────────────────────────
STEP_RULE_IDENTIFIED = "RULE_IDENTIFIED"
"""A legal rule, lookup result, or scope boundary was identified."""

STEP_FACT_DERIVED = "FACT_DERIVED"
"""An intermediate fact was computed or derived from inputs."""

STEP_AMBIGUITY_NOTED = "AMBIGUITY_NOTED"
"""An ambiguity, gap, or partial-modeling limitation was detected."""

STEP_CONCLUSION = "CONCLUSION"
"""The final conclusion of this guard's verification run."""

# ── Evidence type constants ────────────────────────────────────────────────────
EVIDENCE_DETERMINISTIC = "DETERMINISTIC"
"""
Output is provable by math or formal logic with no ambiguity.
Examples: Z3 SAT/UNSAT, date arithmetic, integer comparison.
This is the only evidence type that constitutes actual proof.
"""

EVIDENCE_PARSED = "PARSED"
"""
Output was read or matched from structure (regex, lookup table, JSON field).
NOT a proof — structure match does not verify authority or correctness.
Example: statute lookup table match, regex reporter match.
"""

EVIDENCE_INFERRED = "INFERRED"
"""
Output was derived via pattern matching or keyword analysis.
Not proven — an inference that may be wrong for edge cases.
Example: keyword-overlap coherence check in IRACGuard.
"""

EVIDENCE_HEURISTIC = "HEURISTIC"
"""
Output was produced by an approximate or statistical method.
Not deterministic — result may vary with input framing.
Example: counterfactual comparison in FairnessGuard.
"""

EVIDENCE_UNSUPPORTED = "UNSUPPORTED"
"""
The guard cannot model this input at all.
No conclusion can be drawn — fail-closed.
Example: unknown jurisdiction, unrecognized claim type.
"""


@dataclass
class VerificationStep:
    """
    A single auditable step in a guard's verification_trace.

    Fields:
        step           — step type constant (STEP_RULE_IDENTIFIED etc.)
        description    — human-readable explanation of what happened at this step
        inputs         — dict of facts/values used to reach this step's output
        output         — the conclusion reached at this step
        evidence_type  — how the output was derived (DETERMINISTIC/PARSED/etc.)

    Invariant: evidence_type=DETERMINISTIC is the only type that constitutes
    actual mathematical/logical proof. All other types must NOT be treated as
    verification proof by downstream consumers.
    """

    step: str
    description: str
    inputs: Dict[str, Any]
    output: str
    evidence_type: str

    def is_proven(self) -> bool:
        """
        True only for DETERMINISTIC steps.
        Convenience helper — does not substitute for checking evidence_type.
        """
        return self.evidence_type == EVIDENCE_DETERMINISTIC
