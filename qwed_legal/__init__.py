"""
QWED-Legal: Verification Guards for Legal Contracts

Deterministic verification layer for AI-generated legal document analysis.
Catches date calculation errors, contradictory clauses, and liability miscalculations.
"""

from qwed_legal.guards.deadline_guard import DeadlineGuard
from qwed_legal.guards.liability_guard import LiabilityGuard
from qwed_legal.guards.clause_guard import ClauseGuard

__version__ = "0.1.0"
__all__ = [
    "DeadlineGuard",
    "LiabilityGuard", 
    "ClauseGuard",
    "LegalGuard",
]


class LegalGuard:
    """
    All-in-one legal verification guard.
    
    Combines DeadlineGuard, LiabilityGuard, and ClauseGuard for comprehensive
    contract verification.
    
    Example:
        >>> from qwed_legal import LegalGuard
        >>> guard = LegalGuard()
        >>> result = guard.verify_deadline("2026-01-15", "30 business days", "2026-02-14")
    """
    
    def __init__(self):
        self.deadline = DeadlineGuard()
        self.liability = LiabilityGuard()
        self.clause = ClauseGuard()
    
    def verify_deadline(self, signing_date: str, term: str, claimed_deadline: str):
        """Verify a deadline calculation."""
        return self.deadline.verify(signing_date, term, claimed_deadline)
    
    def verify_liability_cap(self, contract_value: float, cap_percentage: float, claimed_cap: float):
        """Verify a liability cap calculation."""
        return self.liability.verify_cap(contract_value, cap_percentage, claimed_cap)
    
    def check_clause_consistency(self, clauses: list[str]):
        """Check clauses for logical contradictions."""
        return self.clause.check_consistency(clauses)
