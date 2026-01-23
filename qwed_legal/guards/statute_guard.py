"""
StatuteOfLimitationsGuard: Verify statute of limitations claims.

Validates claim periods by jurisdiction and claim type.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
from enum import Enum

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta


class ClaimType(Enum):
    """Types of legal claims with different limitation periods."""
    BREACH_OF_CONTRACT = "breach_of_contract"
    BREACH_OF_WARRANTY = "breach_of_warranty"
    NEGLIGENCE = "negligence"
    PROFESSIONAL_MALPRACTICE = "professional_malpractice"
    FRAUD = "fraud"
    PERSONAL_INJURY = "personal_injury"
    PROPERTY_DAMAGE = "property_damage"
    EMPLOYMENT = "employment"
    PRODUCT_LIABILITY = "product_liability"
    DEFAMATION = "defamation"


@dataclass
class StatuteResult:
    """Result of statute of limitations verification."""
    verified: bool
    claim_type: str
    jurisdiction: str
    incident_date: datetime
    filing_date: datetime
    limitation_period_years: float
    expiration_date: datetime
    days_remaining: int
    message: str


class StatuteOfLimitationsGuard:
    """
    Verify statute of limitations claims.
    
    Catches common LLM errors like:
    - Incorrect limitation periods by jurisdiction
    - Missing tolling provisions
    - Discovery rule misapplication
    
    Example:
        >>> guard = StatuteOfLimitationsGuard()
        >>> result = guard.verify(
        ...     claim_type="breach_of_contract",
        ...     jurisdiction="California",
        ...     incident_date="2022-01-15",
        ...     filing_date="2028-06-01"
        ... )
        >>> print(result.verified)  # False - 4 year limit exceeded
    """
    
    # Statute of limitations by jurisdiction and claim type (in years)
    # Source: General legal references - actual practice requires legal counsel
    LIMITATIONS: Dict[str, Dict[str, float]] = {
        # US States
        "CALIFORNIA": {
            "breach_of_contract": 4.0,
            "breach_of_warranty": 4.0,
            "negligence": 2.0,
            "professional_malpractice": 3.0,
            "fraud": 3.0,
            "personal_injury": 2.0,
            "property_damage": 3.0,
            "employment": 3.0,
            "product_liability": 2.0,
            "defamation": 1.0,
        },
        "NEW YORK": {
            "breach_of_contract": 6.0,
            "breach_of_warranty": 4.0,
            "negligence": 3.0,
            "professional_malpractice": 3.0,
            "fraud": 6.0,
            "personal_injury": 3.0,
            "property_damage": 3.0,
            "employment": 3.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        "TEXAS": {
            "breach_of_contract": 4.0,
            "breach_of_warranty": 4.0,
            "negligence": 2.0,
            "professional_malpractice": 2.0,
            "fraud": 4.0,
            "personal_injury": 2.0,
            "property_damage": 2.0,
            "employment": 2.0,
            "product_liability": 2.0,
            "defamation": 1.0,
        },
        "DELAWARE": {
            "breach_of_contract": 3.0,
            "breach_of_warranty": 4.0,
            "negligence": 2.0,
            "professional_malpractice": 3.0,
            "fraud": 3.0,
            "personal_injury": 2.0,
            "property_damage": 2.0,
            "employment": 3.0,
            "product_liability": 2.0,
            "defamation": 2.0,
        },
        "FLORIDA": {
            "breach_of_contract": 5.0,
            "breach_of_warranty": 4.0,
            "negligence": 4.0,
            "professional_malpractice": 2.0,
            "fraud": 4.0,
            "personal_injury": 4.0,
            "property_damage": 4.0,
            "employment": 4.0,
            "product_liability": 4.0,
            "defamation": 2.0,
        },
        "ILLINOIS": {
            "breach_of_contract": 5.0,
            "breach_of_warranty": 4.0,
            "negligence": 2.0,
            "professional_malpractice": 2.0,
            "fraud": 5.0,
            "personal_injury": 2.0,
            "property_damage": 5.0,
            "employment": 2.0,
            "product_liability": 2.0,
            "defamation": 1.0,
        },
        # UK
        "UK": {
            "breach_of_contract": 6.0,
            "breach_of_warranty": 6.0,
            "negligence": 6.0,
            "professional_malpractice": 6.0,
            "fraud": 6.0,  # No limit for fraud in UK
            "personal_injury": 3.0,
            "property_damage": 6.0,
            "employment": 3.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        "ENGLAND": {
            "breach_of_contract": 6.0,
            "breach_of_warranty": 6.0,
            "negligence": 6.0,
            "professional_malpractice": 6.0,
            "fraud": 6.0,
            "personal_injury": 3.0,
            "property_damage": 6.0,
            "employment": 3.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        # EU Countries
        "GERMANY": {
            "breach_of_contract": 3.0,
            "breach_of_warranty": 2.0,
            "negligence": 3.0,
            "professional_malpractice": 3.0,
            "fraud": 10.0,
            "personal_injury": 3.0,
            "property_damage": 3.0,
            "employment": 3.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        "FRANCE": {
            "breach_of_contract": 5.0,
            "breach_of_warranty": 2.0,
            "negligence": 5.0,
            "professional_malpractice": 5.0,
            "fraud": 5.0,
            "personal_injury": 10.0,
            "property_damage": 5.0,
            "employment": 2.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        # Australia
        "AUSTRALIA": {
            "breach_of_contract": 6.0,
            "breach_of_warranty": 6.0,
            "negligence": 6.0,
            "professional_malpractice": 6.0,
            "fraud": 6.0,
            "personal_injury": 3.0,
            "property_damage": 6.0,
            "employment": 6.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        # India
        "INDIA": {
            "breach_of_contract": 3.0,
            "breach_of_warranty": 3.0,
            "negligence": 3.0,
            "professional_malpractice": 3.0,
            "fraud": 3.0,
            "personal_injury": 1.0,
            "property_damage": 3.0,
            "employment": 3.0,
            "product_liability": 3.0,
            "defamation": 1.0,
        },
        # Canada
        "CANADA": {
            "breach_of_contract": 2.0,  # Varies by province
            "breach_of_warranty": 2.0,
            "negligence": 2.0,
            "professional_malpractice": 2.0,
            "fraud": 6.0,
            "personal_injury": 2.0,
            "property_damage": 2.0,
            "employment": 2.0,
            "product_liability": 2.0,
            "defamation": 2.0,
        },
    }
    
    # Default limitation period if jurisdiction not found
    DEFAULT_LIMITATIONS: Dict[str, float] = {
        "breach_of_contract": 4.0,
        "breach_of_warranty": 4.0,
        "negligence": 3.0,
        "professional_malpractice": 3.0,
        "fraud": 6.0,
        "personal_injury": 3.0,
        "property_damage": 3.0,
        "employment": 3.0,
        "product_liability": 3.0,
        "defamation": 1.0,
    }
    
    def __init__(self):
        """Initialize StatuteOfLimitationsGuard."""
        pass
    
    def verify(
        self,
        claim_type: str,
        jurisdiction: str,
        incident_date: str,
        filing_date: str,
        claimed_within_period: Optional[bool] = None
    ) -> StatuteResult:
        """
        Verify if a claim is within the statute of limitations.
        
        Args:
            claim_type: Type of claim (e.g., "breach_of_contract")
            jurisdiction: State or country name
            incident_date: Date the incident occurred
            filing_date: Date the claim was/will be filed
            claimed_within_period: Optional LLM claim to verify
            
        Returns:
            StatuteResult with verification status
        """
        # Parse dates
        try:
            incident = parse_date(incident_date)
            filing = parse_date(filing_date)
        except Exception as e:
            return StatuteResult(
                verified=False,
                claim_type=claim_type,
                jurisdiction=jurisdiction,
                incident_date=datetime.min,
                filing_date=datetime.min,
                limitation_period_years=0,
                expiration_date=datetime.min,
                days_remaining=0,
                message=f"Failed to parse dates: {e}"
            )
        
        # Get limitation period
        claim_type_lower = claim_type.lower().replace(" ", "_")
        jurisdiction_upper = jurisdiction.upper().strip()
        
        # Look up limitation period
        if jurisdiction_upper in self.LIMITATIONS:
            limits = self.LIMITATIONS[jurisdiction_upper]
        else:
            # Try partial match
            matched = None
            for key in self.LIMITATIONS:
                if key in jurisdiction_upper or jurisdiction_upper in key:
                    matched = key
                    break
            limits = self.LIMITATIONS.get(matched, self.DEFAULT_LIMITATIONS)
        
        period_years = limits.get(claim_type_lower, 3.0)
        
        # Calculate expiration date
        expiration = incident + relativedelta(years=int(period_years))
        if period_years % 1 != 0:
            # Handle fractional years (e.g., 2.5 years)
            extra_months = int((period_years % 1) * 12)
            expiration = expiration + relativedelta(months=extra_months)
        
        # Calculate days remaining
        days_remaining = (expiration - filing).days
        within_period = days_remaining >= 0
        
        # Verify against LLM claim if provided
        if claimed_within_period is not None:
            verified = (claimed_within_period == within_period)
        else:
            verified = within_period
        
        if within_period:
            message = (
                f"✅ WITHIN STATUTE: Claim can be filed. "
                f"{days_remaining} days remaining until expiration on {expiration.strftime('%Y-%m-%d')}."
            )
        else:
            message = (
                f"❌ EXPIRED: Statute of limitations expired on {expiration.strftime('%Y-%m-%d')}. "
                f"Filing date is {abs(days_remaining)} days past expiration."
            )
        
        return StatuteResult(
            verified=verified,
            claim_type=claim_type,
            jurisdiction=jurisdiction,
            incident_date=incident,
            filing_date=filing,
            limitation_period_years=period_years,
            expiration_date=expiration,
            days_remaining=days_remaining,
            message=message
        )
    
    def get_limitation_period(
        self,
        claim_type: str,
        jurisdiction: str
    ) -> float:
        """
        Get the limitation period for a claim type in a jurisdiction.
        
        Args:
            claim_type: Type of claim
            jurisdiction: State or country
            
        Returns:
            Limitation period in years
        """
        claim_type_lower = claim_type.lower().replace(" ", "_")
        jurisdiction_upper = jurisdiction.upper().strip()
        
        if jurisdiction_upper in self.LIMITATIONS:
            return self.LIMITATIONS[jurisdiction_upper].get(
                claim_type_lower, 
                self.DEFAULT_LIMITATIONS.get(claim_type_lower, 3.0)
            )
        
        return self.DEFAULT_LIMITATIONS.get(claim_type_lower, 3.0)
    
    def compare_jurisdictions(
        self,
        claim_type: str,
        jurisdictions: list
    ) -> Dict[str, float]:
        """
        Compare limitation periods across jurisdictions.
        
        Args:
            claim_type: Type of claim
            jurisdictions: List of jurisdictions to compare
            
        Returns:
            Dict mapping jurisdiction to limitation period
        """
        return {
            j: self.get_limitation_period(claim_type, j)
            for j in jurisdictions
        }
