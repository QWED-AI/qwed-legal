"""
QWED-Legal: Verification Guards for Legal Contracts

Deterministic verification layer for AI-generated legal document analysis.
Catches date calculation errors, contradictory clauses, and liability miscalculations.
"""

from qwed_legal.guards.deadline_guard import DeadlineGuard
from qwed_legal.guards.liability_guard import LiabilityGuard
from qwed_legal.guards.clause_guard import ClauseGuard
from qwed_legal.guards.citation_guard import CitationGuard
from qwed_legal.guards.jurisdiction_guard import JurisdictionGuard
from qwed_legal.guards.statute_guard import StatuteOfLimitationsGuard
from qwed_legal.guards.irac_guard import IRACGuard
from qwed_legal.guards.fairness_guard import FairnessGuard
from qwed_legal.guards.contradiction_guard import ContradictionGuard, Clause
from qwed_legal.rag.sac_processor import SACProcessor

__version__ = "0.3.0"
__all__ = [
    "DeadlineGuard",
    "LiabilityGuard",
    "ClauseGuard",
    "CitationGuard",
    "JurisdictionGuard",
    "StatuteOfLimitationsGuard",
    "IRACGuard",
    "FairnessGuard",
    "ContradictionGuard",
    "Clause",
    "SACProcessor",
    "LegalGuard",
]


class LegalGuard:
    """
    All-in-one legal verification guard.

    Combines all guards for comprehensive contract verification.

    Example:
        >>> from qwed_legal import LegalGuard
        >>> guard = LegalGuard()
        >>> result = guard.verify_deadline("2026-01-15", "30 business days", "2026-02-14")
    """

    def __init__(self):
        self.deadline = DeadlineGuard()
        self.liability = LiabilityGuard()
        self.clause = ClauseGuard()
        self.citation = CitationGuard()
        self.jurisdiction = JurisdictionGuard()
        self.statute = StatuteOfLimitationsGuard()
        self.irac = IRACGuard()
        self.contradiction = ContradictionGuard()

    def verify_deadline(self, signing_date: str, term: str, claimed_deadline: str):
        """Verify a deadline calculation."""
        return self.deadline.verify(signing_date, term, claimed_deadline)

    def verify_liability_cap(self, contract_value: float, cap_percentage: float, claimed_cap: float):
        """Verify a liability cap calculation."""
        return self.liability.verify_cap(contract_value, cap_percentage, claimed_cap)

    def check_clause_consistency(self, clauses: list[str]):
        """Check clauses for logical contradictions."""
        return self.clause.check_consistency(clauses)

    def verify_citation(self, citation: str):
        """Verify a legal citation."""
        return self.citation.verify(citation)

    def verify_jurisdiction(self, parties_countries: list[str], governing_law: str, forum: str = None):
        """Verify choice of law and forum selection."""
        return self.jurisdiction.verify_choice_of_law(parties_countries, governing_law, forum)

    def verify_statute_of_limitations(self, claim_type: str, jurisdiction: str, incident_date: str, filing_date: str):
        """Verify if claim is within statute of limitations."""
        return self.statute.verify(claim_type, jurisdiction, incident_date, filing_date)

    def verify_irac_structure(self, llm_output: str):
        """Verify that legal reasoning follows IRAC structure."""
        return self.irac.verify_structure(llm_output)

    def verify_contradiction(self, clauses: list):
        """Check clauses for logical contradictions using Z3."""
        return self.contradiction.verify_consistency(clauses)

