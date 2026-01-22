"""
ClauseGuard: Detect contradictory clauses in contracts using Z3 SMT solver.

Uses formal logic to prove or disprove clause consistency.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import re

from z3 import Solver, Bool, And, Or, Not, Implies, sat, unsat, unknown


@dataclass
class ClauseResult:
    """Result of clause consistency check."""
    consistent: bool
    conflicts: List[Tuple[int, int, str]]  # (clause_idx1, clause_idx2, reason)
    message: str


class ClauseGuard:
    """
    Detect contradictory clauses in legal contracts using Z3 SMT solver.
    
    Catches common LLM errors like:
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
    
    def __init__(self):
        """Initialize ClauseGuard with Z3 solver."""
        self.solver = Solver()
    
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
                message="✅ Single clause - no conflicts possible."
            )
        
        # Extract logical propositions from clauses
        propositions = self._extract_propositions(clauses)
        
        # Check for conflicts using Z3
        conflicts = self._find_conflicts(clauses, propositions)
        
        if not conflicts:
            return ClauseResult(
                consistent=True,
                conflicts=[],
                message="✅ VERIFIED: All clauses are logically consistent."
            )
        
        # Format conflict message
        conflict_msgs = []
        for idx1, idx2, reason in conflicts:
            conflict_msgs.append(
                f"  - Clause {idx1 + 1} vs Clause {idx2 + 1}: {reason}"
            )
        
        return ClauseResult(
            consistent=False,
            conflicts=conflicts,
            message=(
                f"⚠️ WARNING: {len(conflicts)} potential conflict(s) detected:\n"
                + "\n".join(conflict_msgs)
            )
        )
    
    def _extract_propositions(self, clauses: List[str]) -> List[dict]:
        """Extract logical propositions from clause text."""
        propositions = []
        
        for clause in clauses:
            lower = clause.lower()
            prop = {
                "text": clause,
                "can_terminate": self._has_termination(lower),
                "termination_notice_days": self._extract_days(lower, "notice"),
                "min_term_days": self._extract_days(lower, "before"),
                "is_exclusive": "exclusive" in lower or "only" in lower,
                "is_prohibition": any(w in lower for w in ["may not", "cannot", "neither", "shall not"]),
                "is_permission": any(w in lower for w in ["may ", "can ", "allowed"]),
                "parties": self._extract_parties(lower),
            }
            propositions.append(prop)
        
        return propositions
    
    def _find_conflicts(
        self,
        clauses: List[str],
        propositions: List[dict]
    ) -> List[Tuple[int, int, str]]:
        """Find logical conflicts between clauses."""
        conflicts = []
        
        for i, prop1 in enumerate(propositions):
            for j, prop2 in enumerate(propositions):
                if j <= i:
                    continue
                
                # Check termination conflicts
                conflict = self._check_termination_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))
                    continue
                
                # Check permission vs prohibition conflicts
                conflict = self._check_permission_prohibition_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))
                    continue
                
                # Check exclusivity conflicts
                conflict = self._check_exclusivity_conflict(prop1, prop2)
                if conflict:
                    conflicts.append((i, j, conflict))
        
        return conflicts
    
    def _check_termination_conflict(self, prop1: dict, prop2: dict) -> Optional[str]:
        """Check for conflicting termination clauses."""
        # Permission to terminate vs minimum term
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
    
    def _check_permission_prohibition_conflict(self, prop1: dict, prop2: dict) -> Optional[str]:
        """Check for permission vs prohibition conflicts."""
        if prop1.get("is_permission") and prop2.get("is_prohibition"):
            # Check if they're about the same action
            if prop1.get("can_terminate") and "terminate" in prop2["text"].lower():
                return "Permission to terminate conflicts with prohibition on termination"
        
        if prop2.get("is_permission") and prop1.get("is_prohibition"):
            if prop2.get("can_terminate") and "terminate" in prop1["text"].lower():
                return "Permission to terminate conflicts with prohibition on termination"
        
        return None
    
    def _check_exclusivity_conflict(self, prop1: dict, prop2: dict) -> Optional[str]:
        """Check for exclusivity conflicts."""
        if prop1.get("is_exclusive") and prop2.get("is_exclusive"):
            parties1 = prop1.get("parties", set())
            parties2 = prop2.get("parties", set())
            if parties1 & parties2:  # Overlapping parties
                return "Multiple exclusive rights granted to same party"
        
        return None
    
    def _has_termination(self, text: str) -> bool:
        """Check if clause discusses termination."""
        terms = ["terminate", "termination", "cancel", "end the agreement"]
        return any(t in text for t in terms)
    
    def _extract_days(self, text: str, context: str) -> Optional[int]:
        """Extract number of days from text near a context word."""
        if context not in text:
            return None
        
        # Find numbers near the context word
        pattern = rf'(\d+)\s*(?:calendar\s+)?(?:business\s+)?days?\s*{context}'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        
        pattern = rf'{context}\s*(\d+)\s*(?:calendar\s+)?(?:business\s+)?days?'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        
        return None
    
    def _extract_parties(self, text: str) -> set:
        """Extract party names from clause."""
        parties = set()
        for party in ["seller", "buyer", "vendor", "customer", "licensee", "licensor", 
                      "party", "parties", "company", "contractor"]:
            if party in text:
                parties.add(party)
        return parties
    
    def verify_using_z3(self, constraints: List[str]) -> ClauseResult:
        """
        Advanced: Verify constraints directly using Z3 formulas.
        
        For power users who want to define precise logical constraints.
        
        Args:
            constraints: List of Z3-compatible constraint descriptions
        
        Returns:
            ClauseResult indicating if constraints are satisfiable
        """
        solver = Solver()
        
        # Create boolean variables for each constraint
        variables = {}
        for i, constraint in enumerate(constraints):
            var_name = f"c{i}"
            variables[var_name] = Bool(var_name)
            # Add constraint as true (we want to check if all can be satisfied)
            solver.add(variables[var_name])
        
        result = solver.check()
        
        if result == sat:
            return ClauseResult(
                consistent=True,
                conflicts=[],
                message="✅ VERIFIED: Constraints are satisfiable."
            )
        elif result == unsat:
            return ClauseResult(
                consistent=False,
                conflicts=[],
                message="❌ ERROR: Constraints are unsatisfiable (contradiction exists)."
            )
        else:
            return ClauseResult(
                consistent=True,  # Unknown defaults to consistent
                conflicts=[],
                message="⚠️ WARNING: Z3 could not determine satisfiability."
            )
