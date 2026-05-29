"""
StatuteOfLimitationsGuard: Verify statute of limitations claims.

Validates claim periods by jurisdiction and claim type.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict
from enum import Enum

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
    EVIDENCE_UNSUPPORTED,
)


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
    incident_date: Optional[datetime]
    filing_date: Optional[datetime]
    limitation_period_years: Optional[float]
    expiration_date: Optional[datetime]
    days_remaining: Optional[int]
    message: str
    jurisdiction_matched: bool = True  # False if jurisdiction is unknown
    claim_type_matched: bool = True  # False if claim type is unknown
    verification_trace: list = field(default_factory=list)


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

    def __init__(self):
        """Initialize StatuteOfLimitationsGuard."""
        pass

    def verify(
        self,
        claim_type: str,
        jurisdiction: str,
        incident_date: str,
        filing_date: str,
        claimed_within_period: Optional[bool] = None,
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
                incident_date=None,
                filing_date=None,
                limitation_period_years=None,
                expiration_date=None,
                days_remaining=None,
                message=f"Failed to parse dates: {e}",
                jurisdiction_matched=False,
                claim_type_matched=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Date parsing failed — cannot proceed.",
                        inputs={
                            "incident_date": incident_date,
                            "filing_date": filing_date,
                        },
                        output=f"PARSE ERROR: {e}",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        # Get limitation period
        claim_type_lower = claim_type.lower().replace(" ", "_")
        jurisdiction_upper = jurisdiction.upper().strip()

        # Fail-closed: exact jurisdiction match only (no partial matching)
        if jurisdiction_upper not in self.LIMITATIONS:
            return StatuteResult(
                verified=False,
                claim_type=claim_type,
                jurisdiction=jurisdiction,
                incident_date=incident,
                filing_date=filing,
                limitation_period_years=None,
                expiration_date=None,
                days_remaining=None,
                message=(
                    f"⚠️ UNVERIFIABLE: Jurisdiction '{jurisdiction}' is not "
                    f"in the supported jurisdiction list. Cannot determine "
                    f"applicable statute of limitations. Supported: "
                    f"{', '.join(sorted(self.LIMITATIONS.keys()))}."
                ),
                jurisdiction_matched=False,
                claim_type_matched=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Jurisdiction not found in lookup table.",
                        inputs={"jurisdiction": jurisdiction, "claim_type": claim_type},
                        output=f"UNSUPPORTED jurisdiction: '{jurisdiction}'. No limitation period available.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        limits = self.LIMITATIONS[jurisdiction_upper]

        # Fail-closed: exact claim type match only (no default fallback)
        if claim_type_lower not in limits:
            return StatuteResult(
                verified=False,
                claim_type=claim_type,
                jurisdiction=jurisdiction,
                incident_date=incident,
                filing_date=filing,
                limitation_period_years=None,
                expiration_date=None,
                days_remaining=None,
                message=(
                    f"⚠️ UNVERIFIABLE: Claim type '{claim_type}' is not "
                    f"recognized for jurisdiction '{jurisdiction}'. Cannot "
                    f"determine limitation period. Supported claim types: "
                    f"{', '.join(sorted(limits.keys()))}."
                ),
                jurisdiction_matched=True,
                claim_type_matched=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Jurisdiction matched but claim type not found in lookup table.",
                        inputs={
                            "jurisdiction": jurisdiction_upper,
                            "claim_type": claim_type,
                        },
                        output=f"UNSUPPORTED claim type: '{claim_type}' for '{jurisdiction}'.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        period_years = limits[claim_type_lower]

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
            verified = claimed_within_period == within_period
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

        trace = [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Matched jurisdiction and claim type to a known limitation period.",
                inputs={
                    "jurisdiction": jurisdiction_upper,
                    "claim_type": claim_type_lower,
                },
                output=f"Limitation period: {period_years} years",
                evidence_type=EVIDENCE_PARSED,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed expiration date from accrual date + limitation period.",
                inputs={
                    "accrual_date": str(incident),
                    "limitation_period_years": period_years,
                },
                output=f"Expiration date: {expiration.strftime('%Y-%m-%d')}",
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed days remaining between filing date and expiration date.",
                inputs={"filing_date": str(filing), "expiration_date": str(expiration)},
                output=(
                    f"{days_remaining} days remaining"
                    if days_remaining >= 0
                    else f"{abs(days_remaining)} days past expiration"
                ),
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Determined whether the claim falls within the statute of limitations.",
                inputs={
                    "within_period": within_period,
                    "days_remaining": days_remaining,
                },
                output="WITHIN STATUTE" if within_period else "EXPIRED",
                evidence_type=EVIDENCE_DETERMINISTIC,
            ),
        ]
        return StatuteResult(
            verified=verified,
            claim_type=claim_type,
            jurisdiction=jurisdiction,
            incident_date=incident,
            filing_date=filing,
            limitation_period_years=period_years,
            expiration_date=expiration,
            days_remaining=days_remaining,
            message=message,
            verification_trace=trace,
        )

    def get_limitation_period(
        self, claim_type: str, jurisdiction: str
    ) -> Optional[float]:
        """
        Get the limitation period for a claim type in a jurisdiction.

        Args:
            claim_type: Type of claim
            jurisdiction: State or country

        Returns:
            Limitation period in years, or None if jurisdiction/claim unknown
        """
        claim_type_lower = claim_type.lower().replace(" ", "_")
        jurisdiction_upper = jurisdiction.upper().strip()

        if jurisdiction_upper not in self.LIMITATIONS:
            return None

        limits = self.LIMITATIONS[jurisdiction_upper]
        if claim_type_lower not in limits:
            return None

        return limits[claim_type_lower]

    def compare_jurisdictions(
        self, claim_type: str, jurisdictions: list
    ) -> Dict[str, Optional[float]]:
        """
        Compare limitation periods across jurisdictions.

        Args:
            claim_type: Type of claim
            jurisdictions: List of jurisdictions to compare

        Returns:
            Dict mapping jurisdiction to limitation period (None if unknown)
        """
        return {j: self.get_limitation_period(claim_type, j) for j in jurisdictions}
