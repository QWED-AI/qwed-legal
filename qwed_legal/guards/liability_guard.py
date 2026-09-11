"""
LiabilityGuard: Verify liability cap calculations in contracts.

Catches percentage miscalculations, cap verification errors, and multi-tier liability issues.
"""

import warnings
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from qwed_legal.models import (
    VerificationStep,
    STEP_FACT_DERIVED,
    STEP_RULE_IDENTIFIED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_UNSUPPORTED,
)


@dataclass
class LiabilityResult:
    """Result of liability verification."""
    verified: bool
    contract_value: Optional[Decimal]
    cap_percentage: Optional[Decimal]
    claimed_cap: Optional[Decimal]
    computed_cap: Optional[Decimal]
    difference: Optional[Decimal]
    message: str
    verification_trace: list = field(default_factory=list)


@dataclass
class TieredLiabilityResult:
    """Result of tiered liability verification."""
    verified: bool
    tiers: List[dict]
    total_computed: Optional[Decimal]
    claimed_total: Optional[Decimal]
    message: str
    verification_trace: list = field(default_factory=list)


def _non_finite_result(inputs: dict) -> LiabilityResult:
    """Fail-closed result for non-finite (Infinity/NaN) inputs.

    Non-finite values cannot be quantized or compared deterministically;
    verifying with them either crashes (decimal.InvalidOperation) or
    fails closed only by NaN-comparison accident (issue #42).
    """
    return LiabilityResult(
        verified=False,
        contract_value=None,
        cap_percentage=None,
        claimed_cap=None,
        computed_cap=None,
        difference=None,
        message=(
            "⚠️ UNVERIFIABLE: Non-finite input value(s) "
            f"({', '.join(inputs)}) — Infinity and NaN cannot be "
            "quantized or compared deterministically."
        ),
        verification_trace=[
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Validated input values are finite decimals.",
                inputs={k: str(v) for k, v in inputs.items()},
                output="UNSUPPORTED: non-finite input (Infinity or NaN).",
                evidence_type=EVIDENCE_UNSUPPORTED,
            )
        ],
    )


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
            tolerance_percent: Deprecated compatibility argument. Liability
                verification is exact after currency rounding; tolerance is not
                used as a success criterion because approximate caps are not
                legal proof.
        """
        self.tolerance = Decimal(str(tolerance_percent)) / Decimal("100")
    
    def verify_cap(
        self,
        contract_value: float,
        cap_percentage: float,
        claimed_cap: float,
        tolerance_percent: Optional[float] = None,
    ) -> LiabilityResult:
        """
        Verify a simple liability cap calculation.
        
        Args:
            contract_value: Total value of the contract
            cap_percentage: Liability cap as percentage (e.g., 200 for 200%)
            claimed_cap: The cap amount claimed by the LLM
            tolerance_percent: Deprecated compatibility argument. Ignored for
                verification; liability caps must match exactly after currency
                rounding unless a separate contractual rounding rule is modeled.
        
        Returns:
            LiabilityResult with verification status
        """
        if tolerance_percent is not None:
            warnings.warn(
                "tolerance_percent is deprecated and ignored; liability caps "
                "must match exactly after currency rounding",
                DeprecationWarning,
                stacklevel=2,
            )

        cv = Decimal(str(contract_value))
        pct = Decimal(str(cap_percentage)) / Decimal("100")
        claimed = Decimal(str(claimed_cap))

        if not (cv.is_finite() and pct.is_finite() and claimed.is_finite()):
            return _non_finite_result({
                "contract_value": contract_value,
                "cap_percentage": cap_percentage,
                "claimed_cap": claimed_cap,
            })

        computed = (cv * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difference = abs(computed - claimed)
        
        verified = difference == Decimal("0")
        
        if verified:
            message = f"✅ VERIFIED: Liability cap of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Liability cap mismatch. "
                f"{cap_percentage}% of ${contract_value:,.2f} = ${computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}. "
                f"Difference: ${difference:,.2f}. "
                "Approximate tolerance is not accepted as legal proof."
            )
        
        return LiabilityResult(
            verified=verified,
            contract_value=cv,
            cap_percentage=Decimal(str(cap_percentage)),
            claimed_cap=claimed,
            computed_cap=computed,
            difference=difference,
            message=message,
            verification_trace=[
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description="Computed liability cap as percentage of contract value.",
                    inputs={
                        "contract_value": str(cv),
                        "cap_percentage": str(cap_percentage),
                    },
                    output=f"Computed cap: {computed}",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Compared claimed cap to computed cap (exact match required).",
                    inputs={"claimed_cap": str(claimed), "computed_cap": str(computed)},
                    output="CAP VERIFIED" if verified else "CAP MISMATCH",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
            ],
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

        converted = [
            (
                Decimal(str(tier["base"])),
                Decimal(str(tier["percentage"])) / Decimal("100"),
            )
            for tier in tiers
        ]
        claimed = Decimal(str(claimed_total))

        # Fail-closed: a non-finite tier value would crash quantize or
        # poison the running total (issue #42).
        if not claimed.is_finite() or any(
            not base.is_finite() or not pct.is_finite() for base, pct in converted
        ):
            inputs = {
                f"tiers[{i}].base": tier["base"]
                for i, (tier, (base, _)) in enumerate(zip(tiers, converted))
                if not base.is_finite()
            }
            inputs.update({
                f"tiers[{i}].percentage": tier["percentage"]
                for i, (tier, (_, pct)) in enumerate(zip(tiers, converted))
                if not pct.is_finite()
            })
            if not claimed.is_finite():
                inputs["claimed_total"] = claimed_total
            return TieredLiabilityResult(
                verified=False,
                tiers=[],
                total_computed=None,
                claimed_total=None,
                message=(
                    "⚠️ UNVERIFIABLE: Non-finite input value(s) "
                    f"({', '.join(inputs)}) — Infinity and NaN cannot be "
                    "quantized or compared deterministically."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Validated tier values are finite decimals.",
                        inputs={k: str(v) for k, v in inputs.items()},
                        output="UNSUPPORTED: non-finite input (Infinity or NaN).",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        for tier, (base, pct) in zip(tiers, converted):
            tier_liability = (base * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_computed += tier_liability
            computed_tiers.append({
                **tier,
                "computed_liability": float(tier_liability)
            })

        difference = abs(total_computed - claimed)
        
        verified = difference == Decimal("0")
        
        if verified:
            message = f"✅ VERIFIED: Total tiered liability of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Tiered liability mismatch. "
                f"Computed total: ${total_computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}. "
                f"Difference: ${difference:,.2f}. "
                "Approximate tolerance is not accepted as legal proof."
            )
        
        return TieredLiabilityResult(
            verified=verified,
            tiers=computed_tiers,
            total_computed=total_computed,
            claimed_total=claimed,
            message=message,
            verification_trace=[
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description="Computed total liability across all tiers.",
                    inputs={"tier_count": len(tiers)},
                    output=f"Computed total: {total_computed}",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Compared claimed total to computed total (exact match required).",
                    inputs={
                        "claimed_total": str(claimed),
                        "computed_total": str(total_computed),
                    },
                    output="TOTAL VERIFIED" if verified else "TOTAL MISMATCH",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
            ],
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

        if not (fee.is_finite() and mult.is_finite() and claimed.is_finite()):
            return _non_finite_result({
                "annual_fee": annual_fee,
                "multiplier": multiplier,
                "claimed_limit": claimed_limit,
            })

        computed = (fee * mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difference = abs(computed - claimed)
        
        verified = difference == Decimal("0")
        
        if verified:
            message = f"✅ VERIFIED: Indemnity limit of ${claimed:,.2f} is correct."
        else:
            message = (
                f"❌ ERROR: Indemnity limit mismatch. "
                f"{multiplier}x ${annual_fee:,.2f} = ${computed:,.2f}, "
                f"but LLM claimed ${claimed:,.2f}. "
                "Approximate tolerance is not accepted as legal proof."
            )
        
        return LiabilityResult(
            verified=verified,
            contract_value=fee,
            cap_percentage=mult * Decimal("100"),
            claimed_cap=claimed,
            computed_cap=computed,
            difference=difference,
            message=message,
            verification_trace=[
                VerificationStep(
                    step=STEP_FACT_DERIVED,
                    description="Computed indemnity limit as multiplier of annual fee.",
                    inputs={"annual_fee": str(fee), "multiplier": str(mult)},
                    output=f"Computed limit: {computed}",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Compared claimed limit to computed limit (exact match required).",
                    inputs={"claimed_limit": str(claimed), "computed_limit": str(computed)},
                    output="LIMIT VERIFIED" if verified else "LIMIT MISMATCH",
                    evidence_type=EVIDENCE_DETERMINISTIC,
                ),
            ],
        )
