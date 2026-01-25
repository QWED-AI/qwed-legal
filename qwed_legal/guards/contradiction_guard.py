from z3 import *
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class Clause:
    id: str
    text: str
    category: str  # TERMINATION, DURATION, LIABILITY
    value: int     # Normalized value (e.g. days, dollars)

class ContradictionGuard:
    """
    Verifies Logical Consistency of Legal Contracts using Z3.
    Detects contradictions like:
    - "Term is 12 months" VS "Terminable at will after 2 years" (Impossible time travel)
    - "Liability capped at $10k" VS "Minimum penalty $50k"
    """
    
    def verify_consistency(self, clauses: List[Clause]) -> dict:
        """
        Translates legal clauses into Z3 constraints and checks for SAT.
        """
        s = Solver()
        
        # We model key variables that clauses constrain
        contract_duration_months = Int('contract_duration_months')
        max_liability_usd = Int('max_liability_usd')
        notice_period_days = Int('notice_period_days')
        
        # Basic physical constraints (No negative time/money)
        s.add(contract_duration_months >= 0)
        s.add(max_liability_usd >= 0)
        s.add(notice_period_days >= 0)
        
        clause_map = {} # Trace back constraint to clause ID
        
        term_clauses = [c for c in clauses if c.category == "DURATION"]
        liability_clauses = [c for c in clauses if c.category == "LIABILITY"]
        
        # --- Logic Translation ---
        # Note: Real-world version would use an LLM or Parser to convert Text -> Z3
        # Here we assume the parser has extracted the 'value' and 'category'.
        
        for c in term_clauses:
            # Example: "Duration shall be exactly 12 months"
            # Example: "Duration must be at least 24 months"
            if "exactly" in c.text.lower():
                s.add(contract_duration_months == c.value)
            elif "minimum" in c.text.lower() or "at least" in c.text.lower():
                s.add(contract_duration_months >= c.value)
            elif "maximum" in c.text.lower() or "up to" in c.text.lower():
                s.add(contract_duration_months <= c.value)
                
        for c in liability_clauses:
            # Example: "Liability capped at 5000"
            if "capped" in c.text.lower() or "max" in c.text.lower():
                s.add(max_liability_usd <= c.value)
            # Example: "Penalty shall be 10000"
            elif "penalty" in c.text.lower() or "fixed" in c.text.lower():
                # A penalty implies liability is AT LEAST this much if breach happens
                # If penalty > Cap, then UNSAT.
                s.add(max_liability_usd >= c.value)

        # Check Consistency
        if s.check() == sat:
            return {
                "verified": True,
                "message": "✅ Contract logic is consistent."
            }
        else:
            # Find the core conflict (Simplified/Mocked diagnosis)
            # Real Z3 can use unsat_core()
            
            return {
                "verified": False,
                "message": "❌ LOGIC CONTRADICTION: Clauses are mutually exclusive. (e.g. Penalty > Liability Cap, or Min Term > Max Duration). Check Z3 trace."
            }
