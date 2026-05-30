"""
DeadlineGuard: Verify date calculations in legal contracts.

Handles business days, calendar days, leap years, and holiday exclusions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import re

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
import holidays

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
    EVIDENCE_UNSUPPORTED,
)


@dataclass
class DeadlineResult:
    """Result of deadline verification."""
    verified: bool
    signing_date: datetime
    claimed_deadline: datetime
    computed_deadline: Optional[datetime]
    term_parsed: str
    difference_days: Optional[int]
    message: str
    is_computable: bool = True  # False if term is ambiguous/unparseable
    verification_mode: str = "SYMBOLIC"  # Always SYMBOLIC for legal (SymPy/Z3)
    verification_trace: list = field(default_factory=list)


class DeadlineGuard:
    """
    Verify date calculations in legal contracts.
    
    Catches common LLM errors like:
    - Confusing business days vs calendar days
    - Leap year miscalculations
    - Weekend/holiday exclusion errors
    
    Example:
        >>> guard = DeadlineGuard()
        >>> result = guard.verify("2026-01-15", "30 business days", "2026-02-14")
        >>> print(result.verified)  # False - 30 business days != Feb 14
    """
    
    def __init__(self, country: str = "US", state: Optional[str] = None):
        """
        Initialize DeadlineGuard.
        
        Args:
            country: ISO country code for holidays (default: US)
            state: State/province code for regional holidays (optional)
        """
        self.country = country
        self.state = state
        try:
            self.holiday_calendar = holidays.country_holidays(country, subdiv=state)
        except Exception:
            self.holiday_calendar = holidays.US()
    
    def verify(
        self,
        signing_date: str,
        term: str,
        claimed_deadline: str,
        tolerance_days: int = 0
    ) -> DeadlineResult:
        """
        Verify a deadline calculation.
        
        Args:
            signing_date: The date the contract was signed (ISO format or natural language)
            term: The term description (e.g., "30 days", "30 business days", "2 weeks")
            claimed_deadline: The deadline claimed by the LLM
            tolerance_days: Allow +/- this many days for verification (default: 0)
        
        Returns:
            DeadlineResult with verification status and computed deadline
        """
        # Parse dates
        try:
            signing = parse_date(signing_date)
            claimed = parse_date(claimed_deadline)
        except Exception as e:
            return DeadlineResult(
                verified=False,
                signing_date=datetime.min,
                claimed_deadline=datetime.min,
                computed_deadline=None,
                term_parsed="ERROR",
                difference_days=None,
                message=f"Failed to parse dates: {e}",
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Date parsing failed — cannot proceed.",
                        inputs={
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output=f"UNSUPPORTED: parse error: {e}",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )
        
        # Parse term and calculate deadline
        computed = self._calculate_deadline(signing, term)
        
        # Fail-closed: if the term is ambiguous, do not verify
        if computed is None:
            return DeadlineResult(
                verified=False,
                signing_date=signing,
                claimed_deadline=claimed,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    f"⚠️ UNVERIFIABLE: Term '{term}' does not contain a "
                    f"provable time quantity and unit. Cannot compute a "
                    f"deterministic deadline. Ambiguous legal language "
                    f"(e.g., 'reasonable period', 'promptly') requires "
                    f"human legal interpretation."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Term parsed for a deterministic time quantity and unit.",
                        inputs={"term": term},
                        output=(
                            "UNSUPPORTED: ambiguous term — no provable "
                            "quantity/unit to compute a deadline."
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )
        
        # Check difference
        diff = abs((claimed - computed).days)
        verified = diff <= tolerance_days
        
        if verified:
            message = "✅ VERIFIED: Deadline calculation is correct."
        else:
            message = (
                f"❌ ERROR: Deadline mismatch. "
                f"Expected {computed.strftime('%Y-%m-%d')}, "
                f"but LLM claimed {claimed.strftime('%Y-%m-%d')}. "
                f"Difference: {diff} days."
            )
        
        trace = [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Parsed term into a deterministic time quantity and unit.",
                inputs={"term": term, "tolerance_days": tolerance_days},
                output=f"Parsed term: '{term}'",
                evidence_type=EVIDENCE_PARSED,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed deadline from signing date and parsed term.",
                inputs={"signing_date": str(signing), "term": term},
                output=f"Computed deadline: {computed.strftime('%Y-%m-%d')}",
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed difference between claimed and computed deadline.",
                inputs={
                    "claimed_deadline": str(claimed),
                    "computed_deadline": str(computed),
                    "tolerance_days": tolerance_days,
                },
                output=f"Difference: {diff} day(s)",
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Determined whether the claimed deadline matches within tolerance.",
                inputs={"difference_days": diff, "tolerance_days": tolerance_days},
                output="DEADLINE VERIFIED" if verified else "DEADLINE MISMATCH",
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
        ]
        
        return DeadlineResult(
            verified=verified,
            signing_date=signing,
            claimed_deadline=claimed,
            computed_deadline=computed,
            term_parsed=term,
            difference_days=diff,
            message=message,
            verification_trace=trace,
        )
    
    def _calculate_deadline(self, start_date: datetime, term: str) -> Optional[datetime]:
        """Calculate the actual deadline from a term description.
        
        Returns None if the term is ambiguous and cannot be parsed into
        a deterministic deadline (fail-closed).
        """
        term_lower = term.lower().strip()
        
        # Extract number
        numbers = re.findall(r'\d+', term_lower)
        if not numbers:
            # Fail-closed: no numeric quantity found — term is ambiguous
            return None
        
        num = int(numbers[0])
        
        # Determine unit and type (word-boundary matching to prevent
        # false positives like 'today' matching 'day')
        is_business_days = bool(re.search(r'\b(?:business|working|work)\b', term_lower))
        
        if re.search(r'\byears?\b', term_lower):
            return start_date + relativedelta(years=num)
        elif re.search(r'\bmonths?\b', term_lower):
            return start_date + relativedelta(months=num)
        elif re.search(r'\bweeks?\b', term_lower):
            if is_business_days:
                return self._add_business_days(start_date, num * 5)
            return start_date + timedelta(weeks=num)
        elif re.search(r'\b(?:days?|calendar\s+days?)\b', term_lower):
            if is_business_days:
                return self._add_business_days(start_date, num)
            return start_date + timedelta(days=num)
        else:
            # Fail-closed: number found but no recognizable time unit
            return None
    
    def _add_business_days(self, start_date: datetime, days: int) -> datetime:
        """Add business days to a date, excluding weekends and holidays."""
        current = start_date
        added = 0
        
        while added < days:
            current += timedelta(days=1)
            # Skip weekends (Saturday=5, Sunday=6)
            if current.weekday() >= 5:
                continue
            # Skip holidays
            if current in self.holiday_calendar:
                continue
            added += 1
        
        return current
    
    def calculate_business_days_between(
        self,
        start_date: str,
        end_date: str
    ) -> int:
        """
        Calculate the number of business days between two dates.
        
        Useful for verifying claims like "response required within 10 business days."
        """
        start = parse_date(start_date)
        end = parse_date(end_date)
        
        if end < start:
            start, end = end, start
        
        count = 0
        current = start
        while current < end:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in self.holiday_calendar:
                count += 1
        
        return count
