"""
LiabilityGuard: Verify liability cap calculations in contracts.

Catches percentage miscalculations, cap verification errors, and multi-tier liability issues.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List


@dataclass
class LiabilityResult:
    """Result of liability verification."""
    verified: bool
    contract_value: Decimal
    cap_percentage: Decimal
    claimed_cap: Decimal
    computed_cap: Decimal
    difference: Decimal
    message: str


@dataclass
class TieredLiabilityResult:
    """Result of tiered liability verification."""
    verified: bool
    tiers: List[dict]
    total_computed: Decimal
    claimed_total: Decimal
    message: str


class LiabilityGuard:
    """
    Verify liability cap calculations in legal contracts.
    
    Catches common LLM errors like:
    - Percentage calculation mistakes
    - Cap amount verification errors
    - Multi-tier liability miscalculations
    
    Example:
        >>> guard = LiabilityGuard()
        >>> result = guard.verify_cap(5_000_000, 200, 15_000_000)
        >>> print(result.verified)  # False - 200% of 5M = 10M, not 15M
    """
    
    def __init__(self, tolerance_percent: float = 0.01):
        """
        Initialize LiabilityGuard.
        
        Args:
            tolerance_percent: Tolerance for floating-point errors (default: 0.01%)
        """
        self.tolerance = Decimal(str(tolerance_percent)) / Decimal("100")
    
    def verify_cap(
        self,
        contract_value: float,
        cap_percentage: float,
        claimed_cap: float
    ) -> LiabilityResult:
        """
        Verify a simple liability cap calculation.
        
        Args:
            contract_value: Total value of the contract
            cap_percentage: Liability cap as percentage (e.g., 200 for 200%)
            claimed_cap: The cap amount claimed by the LLM
        
        Returns:
            LiabilityResult with verification status
        """
        cv = Decimal(str(contract_value))
        pct = Decimal(str(cap_percentage)) / Decimal("100")
        claimed = Decimal(str(claimed_cap))
        
        computed = (cv * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difference = abs(computed - claimed)
        tolerance_amount = computed * self.tolerance
        
        verified = difference <= tolerance_amount
        
        if verified:
            message = f"✅ VERIFIED: Liability cap of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Liability cap mismatch. "
                f"{cap_percentage}% of ${contract_value:,.2f} = ${computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}. "
                f"Difference: ${difference:,.2f}"
            )
        
        return LiabilityResult(
            verified=verified,
            contract_value=cv,
            cap_percentage=Decimal(str(cap_percentage)),
            claimed_cap=claimed,
            computed_cap=computed,
            difference=difference,
            message=message
        )
    
    def verify_tiered_liability(
        self,
        tiers: List[dict],
        claimed_total: float
    ) -> TieredLiabilityResult:
        """
        Verify multi-tier liability calculations.
        
        Args:
            tiers: List of dicts with 'base' and 'percentage' keys
                   e.g., [{"base": 1000000, "percentage": 100}, {"base": 500000, "percentage": 50}]
            claimed_total: Total liability cap claimed by LLM
        
        Returns:
            TieredLiabilityResult with verification status
        """
        total_computed = Decimal("0")
        computed_tiers = []
        
        for tier in tiers:
            base = Decimal(str(tier["base"]))
            pct = Decimal(str(tier["percentage"])) / Decimal("100")
            tier_liability = (base * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_computed += tier_liability
            computed_tiers.append({
                **tier,
                "computed_liability": float(tier_liability)
            })
        
        claimed = Decimal(str(claimed_total))
        difference = abs(total_computed - claimed)
        tolerance_amount = total_computed * self.tolerance if total_computed > 0 else Decimal("1")
        
        verified = difference <= tolerance_amount
        
        if verified:
            message = f"✅ VERIFIED: Total tiered liability of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Tiered liability mismatch. "
                f"Computed total: ${total_computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}. "
                f"Difference: ${difference:,.2f}"
            )
        
        return TieredLiabilityResult(
            verified=verified,
            tiers=computed_tiers,
            total_computed=total_computed,
            claimed_total=claimed,
            message=message
        )
    
    def verify_indemnity_limit(
        self,
        annual_fee: float,
        multiplier: float,
        claimed_limit: float
    ) -> LiabilityResult:
        """
        Verify indemnity limit calculations (common pattern: X times annual fee).
        
        Example: "Indemnity limited to 3x annual fee"
        
        Args:
            annual_fee: The annual service fee
            multiplier: The multiplier (e.g., 3 for "3x")
            claimed_limit: The limit claimed by LLM
        
        Returns:
            LiabilityResult with verification status
        """
        fee = Decimal(str(annual_fee))
        mult = Decimal(str(multiplier))
        claimed = Decimal(str(claimed_limit))
        
        computed = (fee * mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difference = abs(computed - claimed)
        tolerance_amount = computed * self.tolerance
        
        verified = difference <= tolerance_amount
        
        if verified:
            message = f"✅ VERIFIED: Indemnity limit of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Indemnity limit mismatch. "
                f"{multiplier}x ${annual_fee:,.2f} = ${computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}."
            )
        
        return LiabilityResult(
            verified=verified,
            contract_value=fee,
            cap_percentage=mult * Decimal("100"),
            claimed_cap=claimed,
            computed_cap=computed,
            difference=difference,
            message=message
        )
