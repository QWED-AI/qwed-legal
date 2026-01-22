"""
DeadlineGuard: Verify date calculations in legal contracts.

Handles business days, calendar days, leap years, and holiday exclusions.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import re

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
import holidays


@dataclass
class DeadlineResult:
    """Result of deadline verification."""
    verified: bool
    signing_date: datetime
    claimed_deadline: datetime
    computed_deadline: datetime
    term_parsed: str
    difference_days: int
    message: str


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
                computed_deadline=datetime.min,
                term_parsed="ERROR",
                difference_days=0,
                message=f"Failed to parse dates: {e}"
            )
        
        # Parse term and calculate deadline
        computed = self._calculate_deadline(signing, term)
        
        # Check difference
        diff = abs((claimed - computed).days)
        verified = diff <= tolerance_days
        
        if verified:
            message = f"✅ VERIFIED: Deadline calculation is correct."
        else:
            message = (
                f"❌ ERROR: Deadline mismatch. "
                f"Expected {computed.strftime('%Y-%m-%d')}, "
                f"but LLM claimed {claimed.strftime('%Y-%m-%d')}. "
                f"Difference: {diff} days."
            )
        
        return DeadlineResult(
            verified=verified,
            signing_date=signing,
            claimed_deadline=claimed,
            computed_deadline=computed,
            term_parsed=term,
            difference_days=diff,
            message=message
        )
    
    def _calculate_deadline(self, start_date: datetime, term: str) -> datetime:
        """Calculate the actual deadline from a term description."""
        term_lower = term.lower().strip()
        
        # Extract number
        numbers = re.findall(r'\d+', term_lower)
        if not numbers:
            # Default to 30 if no number found
            num = 30
        else:
            num = int(numbers[0])
        
        # Determine unit and type
        is_business_days = any(kw in term_lower for kw in ['business', 'working', 'work'])
        
        if 'year' in term_lower:
            return start_date + relativedelta(years=num)
        elif 'month' in term_lower:
            return start_date + relativedelta(months=num)
        elif 'week' in term_lower:
            if is_business_days:
                return self._add_business_days(start_date, num * 5)
            return start_date + timedelta(weeks=num)
        else:  # days
            if is_business_days:
                return self._add_business_days(start_date, num)
            return start_date + timedelta(days=num)
    
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
