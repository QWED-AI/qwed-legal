"""
JurisdictionGuard: Verify jurisdiction-related claims in legal contracts.

Validates choice of law, forum selection, and cross-border jurisdiction conflicts.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from enum import Enum


class JurisdictionType(Enum):
    """Types of jurisdiction clauses."""
    EXCLUSIVE = "exclusive"
    NON_EXCLUSIVE = "non_exclusive"
    HYBRID = "hybrid"


@dataclass
class JurisdictionResult:
    """Result of jurisdiction verification."""
    verified: bool
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    governing_law: Optional[str] = None
    forum: Optional[str] = None
    message: str = ""


class JurisdictionGuard:
    """
    Verify jurisdiction-related claims in legal contracts.
    
    Catches common LLM errors like:
    - Mismatched governing law and forum selection
    - Invalid jurisdiction combinations
    - Cross-border regulation conflicts
    
    Example:
        >>> guard = JurisdictionGuard()
        >>> result = guard.verify_choice_of_law(
        ...     parties_countries=["US", "UK"],
        ...     governing_law="Delaware",
        ...     forum="London"
        ... )
        >>> print(result.conflicts)  # Potential mismatch warning
    """
    
    # Common law jurisdictions
    COMMON_LAW_JURISDICTIONS: Set[str] = {
        "US", "UK", "GB", "CA", "AU", "NZ", "IE", "SG", "HK", "IN"
    }
    
    # Civil law jurisdictions
    CIVIL_LAW_JURISDICTIONS: Set[str] = {
        "DE", "FR", "IT", "ES", "NL", "BE", "AT", "CH", "JP", "KR", "BR", "MX"
    }
    
    # US state abbreviations for forum selection
    US_STATES: Set[str] = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
    }
    
    # Popular corporate law states
    CORPORATE_LAW_STATES: Set[str] = {"DE", "NV", "WY", "NY", "CA"}
    
    # Recognized international conventions
    INTERNATIONAL_CONVENTIONS: Dict[str, Set[str]] = {
        "CISG": {  # UN Convention on International Sale of Goods
            "US", "DE", "FR", "IT", "ES", "NL", "AT", "CH", "CN", "JP", "AU", "CA"
        },
        "HAGUE_CHOICE": {  # Hague Choice of Court Convention
            "EU", "UK", "SG", "MX", "ME", "UA"
        },
        "NEW_YORK_CONVENTION": {  # Recognition of Arbitral Awards
            "US", "UK", "DE", "FR", "CN", "JP", "IN", "AU", "BR", "CA"
        }
    }
    
    def __init__(self):
        """Initialize JurisdictionGuard."""
        pass
    
    def verify_choice_of_law(
        self,
        parties_countries: List[str],
        governing_law: str,
        forum: Optional[str] = None,
        jurisdiction_type: JurisdictionType = JurisdictionType.EXCLUSIVE
    ) -> JurisdictionResult:
        """
        Verify choice of law and forum selection clause.
        
        Args:
            parties_countries: List of country codes for contract parties
            governing_law: The stated governing law (country or state)
            forum: The stated forum/venue (optional)
            jurisdiction_type: Type of jurisdiction clause
            
        Returns:
            JurisdictionResult with verification status and any conflicts
        """
        conflicts = []
        warnings = []
        
        # Normalize inputs
        governing_law_upper = governing_law.upper().strip()
        parties_upper = [p.upper().strip() for p in parties_countries]
        forum_upper = forum.upper().strip() if forum else None
        
        # Check 1: Is governing law a recognized jurisdiction?
        if not self._is_valid_jurisdiction(governing_law_upper):
            conflicts.append(
                f"Unrecognized governing law jurisdiction: '{governing_law}'"
            )
        
        # Check 2: Cross-border legal system conflicts
        party_legal_systems = set()
        for country in parties_upper:
            if country in self.COMMON_LAW_JURISDICTIONS:
                party_legal_systems.add("COMMON_LAW")
            elif country in self.CIVIL_LAW_JURISDICTIONS:
                party_legal_systems.add("CIVIL_LAW")
        
        gov_law_system = None
        if governing_law_upper in self.COMMON_LAW_JURISDICTIONS or governing_law_upper in self.US_STATES:
            gov_law_system = "COMMON_LAW"
        elif governing_law_upper in self.CIVIL_LAW_JURISDICTIONS:
            gov_law_system = "CIVIL_LAW"
        
        if len(party_legal_systems) > 1:
            warnings.append(
                "Cross-border contract with parties from different legal systems "
                "(Common Law and Civil Law). Consider CISG applicability."
            )
        
        # Check 3: Forum vs governing law mismatch
        if forum_upper and governing_law_upper:
            if self._is_us_state(governing_law_upper) and not self._is_us_jurisdiction(forum_upper):
                conflicts.append(
                    f"Governing law '{governing_law}' (US state) but forum '{forum}' is non-US. "
                    "This may create enforcement issues."
                )
            elif self._is_us_state(forum_upper) and not (
                self._is_us_jurisdiction(governing_law_upper) or governing_law_upper in ["US", "NY", "CA", "DE"]
            ):
                conflicts.append(
                    f"Forum '{forum}' (US state) but governing law '{governing_law}' is non-US. "
                    "Consider alignment for enforceability."
                )
        
        # Check 4: CISG applicability warning
        us_party = any(c in ["US"] or c in self.US_STATES for c in parties_upper)
        foreign_party = any(c not in ["US"] and c not in self.US_STATES for c in parties_upper)
        if us_party and foreign_party:
            warnings.append(
                "International sale of goods may be subject to CISG unless expressly excluded."
            )
        
        # Check 5: Neutral jurisdiction suggestion
        if len(parties_upper) >= 2 and governing_law_upper in parties_upper:
            warnings.append(
                f"Governing law '{governing_law}' favors one party's home jurisdiction. "
                "Consider a neutral jurisdiction for balance."
            )
        
        verified = len(conflicts) == 0
        
        if verified:
            message = "✅ VERIFIED: Jurisdiction clause appears consistent."
        else:
            message = f"❌ CONFLICTS DETECTED: {len(conflicts)} issue(s) found."
        
        return JurisdictionResult(
            verified=verified,
            conflicts=conflicts,
            warnings=warnings,
            governing_law=governing_law,
            forum=forum,
            message=message
        )
    
    def verify_forum_selection(
        self,
        forum: str,
        contract_value: Optional[float] = None,
        parties_countries: Optional[List[str]] = None
    ) -> JurisdictionResult:
        """
        Verify forum selection clause validity.
        
        Args:
            forum: The stated forum/venue
            contract_value: Optional contract value for threshold checks
            parties_countries: List of party countries
            
        Returns:
            JurisdictionResult with verification status
        """
        conflicts = []
        warnings = []
        forum_upper = forum.upper().strip()
        
        # Validate forum
        if not self._is_valid_jurisdiction(forum_upper):
            conflicts.append(f"Unrecognized forum: '{forum}'")
        
        # Check for common federal court thresholds
        if contract_value and forum_upper in self.US_STATES:
            if contract_value < 75000:
                warnings.append(
                    f"Contract value ${contract_value:,.0f} may not meet diversity "
                    "jurisdiction threshold ($75,000) for US federal court."
                )
        
        verified = len(conflicts) == 0
        message = "✅ VERIFIED: Forum selection is valid." if verified else f"❌ {conflicts[0]}"
        
        return JurisdictionResult(
            verified=verified,
            conflicts=conflicts,
            warnings=warnings,
            forum=forum,
            message=message
        )
    
    def check_convention_applicability(
        self,
        parties_countries: List[str],
        convention: str
    ) -> JurisdictionResult:
        """
        Check if an international convention applies.
        
        Args:
            parties_countries: List of party country codes
            convention: Convention name (CISG, HAGUE_CHOICE, NEW_YORK_CONVENTION)
            
        Returns:
            JurisdictionResult with applicability status
        """
        convention_upper = convention.upper().replace(" ", "_")
        parties_upper = [p.upper().strip() for p in parties_countries]
        
        if convention_upper not in self.INTERNATIONAL_CONVENTIONS:
            return JurisdictionResult(
                verified=False,
                conflicts=[f"Unknown convention: '{convention}'"],
                message=f"❌ Unknown convention: '{convention}'"
            )
        
        member_countries = self.INTERNATIONAL_CONVENTIONS[convention_upper]
        all_members = all(c in member_countries for c in parties_upper)
        some_members = any(c in member_countries for c in parties_upper)
        
        if all_members:
            return JurisdictionResult(
                verified=True,
                message=f"✅ {convention} applies - all parties are from member states.",
                warnings=[]
            )
        elif some_members:
            non_members = [c for c in parties_upper if c not in member_countries]
            return JurisdictionResult(
                verified=False,
                warnings=[f"Not all parties are {convention} members: {non_members}"],
                message=f"⚠️ {convention} may not apply to all parties."
            )
        else:
            return JurisdictionResult(
                verified=False,
                conflicts=[f"No parties are {convention} member states."],
                message=f"❌ {convention} does not apply."
            )
    
    def _is_valid_jurisdiction(self, jurisdiction: str) -> bool:
        """Check if a jurisdiction is recognized."""
        return (
            jurisdiction in self.COMMON_LAW_JURISDICTIONS or
            jurisdiction in self.CIVIL_LAW_JURISDICTIONS or
            jurisdiction in self.US_STATES or
            jurisdiction in {"EU", "UK", "ENGLAND", "SCOTLAND", "WALES"}
        )
    
    def _is_us_state(self, jurisdiction: str) -> bool:
        """Check if jurisdiction is a US state."""
        return jurisdiction in self.US_STATES
    
    def _is_us_jurisdiction(self, jurisdiction: str) -> bool:
        """Check if jurisdiction is US-related."""
        return jurisdiction in self.US_STATES or jurisdiction == "US"
