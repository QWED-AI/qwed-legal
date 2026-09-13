"""
LiabilityGuard: Verify liability cap calculations in contracts.

Catches percentage miscalculations, cap verification errors, and multi-tier liability issues.
"""

import warnings
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from typing import List, Optional

from qwed_legal.diagnostics import LegalDiagnosticsMixin, LegalDiagnosticStatus
from qwed_legal.models import (
    VerificationStep,
    STEP_FACT_DERIVED,
    STEP_RULE_IDENTIFIED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_UNSUPPORTED,
)


@dataclass(frozen=True)
class LiabilityResult(LegalDiagnosticsMixin):
    """Result of liability verification."""
    verified: bool
    contract_value: Optional[Decimal]
    cap_percentage: Optional[Decimal]
    claimed_cap: Optional[Decimal]
    computed_cap: Optional[Decimal]
    difference: Optional[Decimal]
    message: str
    verification_trace: list = field(default_factory=list)

    def __post_init__(self):
        self._freeze_evidence_fields("verification_trace")

    def _diagnostic_status(self):
        # Structured classification: a None computed cap means the input
        # was unverifiable (non-finite/out-of-range); a computed cap with
        # a mismatch is a deterministic rejection. Message wording must
        # not drive machine state (PR #48 review, Greptile).
        if self.verified:
            return LegalDiagnosticStatus.VERIFIED
        if self.computed_cap is None:
            return LegalDiagnosticStatus.UNVERIFIABLE
        return LegalDiagnosticStatus.BLOCKED

@dataclass(frozen=True)
class TieredLiabilityResult(LegalDiagnosticsMixin):
    """Result of tiered liability verification."""
    verified: bool
    tiers: List[dict]
    total_computed: Optional[Decimal]
    claimed_total: Optional[Decimal]
    message: str
    verification_trace: list = field(default_factory=list)

    def __post_init__(self):
        self._freeze_evidence_fields("tiers", "verification_trace")

    def _diagnostic_status(self):
        if self.verified:
            return LegalDiagnosticStatus.VERIFIED
        if self.total_computed is None:
            return LegalDiagnosticStatus.UNVERIFIABLE
        return LegalDiagnosticStatus.BLOCKED


def _invalid_names(named_values: dict) -> List[str]:
    """Names of inputs that cannot convert to a finite Decimal.

    Malformed values (non-numeric strings raise at Decimal construction)
    and non-finite values (Infinity/NaN) are both non-verifiable — the
    conversion must never propagate an exception to the caller
    (PR #44 review).
    """
    invalid = []
    for name, value in named_values.items():
        try:
            finite = Decimal(str(value)).is_finite()
        except DecimalException:
            finite = False
        if not finite:
            invalid.append(name)
    return invalid


# Shared reason for finite-but-extreme magnitudes that exceed the decimal
# context (quantize precision / context range).
_RANGE_MESSAGE = "Input magnitude(s) exceed the supported decimal range."


def _unverifiable_result(reason: str, inputs: dict) -> LiabilityResult:
    """Fail-closed result for inputs that cannot be verified.

    Non-finite values (Infinity/NaN) and magnitudes beyond the decimal
    context cannot be quantized or compared deterministically; verifying
    with them either crashes or fails closed only by accident
    (issue #42, PR #44 review).
    """
    return LiabilityResult(
        verified=False,
        contract_value=None,
        cap_percentage=None,
        claimed_cap=None,
        computed_cap=None,
        difference=None,
        message=f"⚠️ UNVERIFIABLE: {reason}",
        verification_trace=[
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Validated input values are verifiable decimals.",
                inputs={k: str(v) for k, v in inputs.items()},
                output=f"UNSUPPORTED: {reason}",
                evidence_type=EVIDENCE_UNSUPPORTED,
            )
        ],
    )


def _unverifiable_tiered_result(reason: str, inputs: dict) -> TieredLiabilityResult:
    """Tiered variant of the fail-closed unverifiable result."""
    return TieredLiabilityResult(
        verified=False,
        tiers=[],
        total_computed=None,
        claimed_total=None,
        message=f"⚠️ UNVERIFIABLE: {reason}",
        verification_trace=[
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Validated tier values are verifiable decimals.",
                inputs={k: str(v) for k, v in inputs.items()},
                output=f"UNSUPPORTED: {reason}",
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

        named_inputs = {
            "contract_value": contract_value,
            "cap_percentage": cap_percentage,
            "claimed_cap": claimed_cap,
        }

        invalid = _invalid_names(named_inputs)
        if invalid:
            return _unverifiable_result(
                f"Input value(s) ({', '.join(invalid)}) cannot be "
                "verified — values must be finite decimal numbers "
                "(non-finite or malformed inputs cannot be quantized "
                "or compared deterministically).",
                named_inputs,
            )

        cv = Decimal(str(contract_value))
        pct = Decimal(str(cap_percentage)) / Decimal("100")
        claimed = Decimal(str(claimed_cap))

        try:
            computed = (cv * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            difference = abs(computed - claimed)
        except DecimalException:
            # Finite but extreme magnitudes can exceed the decimal context
            # (quantize precision / context range) — fail closed (PR #44).
            return _unverifiable_result(
                _RANGE_MESSAGE,
                named_inputs,
            )
        
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

        all_tier_inputs = {
            **{f"tiers[{i}]": tier for i, tier in enumerate(tiers)},
            "claimed_total": claimed_total,
        }

        # Convert RAW values only — no arithmetic yet. A signaling NaN
        # raises InvalidOperation on the /100 division, so finiteness
        # must be validated before any operation (PR #44 review).
        try:
            raw_tiers = [
                (Decimal(str(tier["base"])), Decimal(str(tier["percentage"])))
                for tier in tiers
            ]
            claimed = Decimal(str(claimed_total))
        except DecimalException:
            # Non-decimal input values (e.g., non-numeric strings) — fail
            # closed instead of crashing at construction.
            return _unverifiable_tiered_result(
                "Input value(s) are not valid decimal numbers.",
                all_tier_inputs,
            )

        # Fail-closed: a non-finite tier value would crash quantize or
        # poison the running total (issue #42).
        offending = {
            f"tiers[{i}].base": tier["base"]
            for i, (tier, (base, _)) in enumerate(zip(tiers, raw_tiers))
            if not base.is_finite()
        }
        offending.update({
            f"tiers[{i}].percentage": tier["percentage"]
            for i, (tier, (_, pct)) in enumerate(zip(tiers, raw_tiers))
            if not pct.is_finite()
        })
        if not claimed.is_finite():
            offending["claimed_total"] = claimed_total
        if offending:
            return _unverifiable_tiered_result(
                f"Non-finite input value(s) ({', '.join(offending)}) — "
                "Infinity and NaN cannot be quantized or compared "
                "deterministically.",
                all_tier_inputs,
            )

        try:
            converted = [
                (base, pct / Decimal("100")) for base, pct in raw_tiers
            ]
            for tier, (base, pct) in zip(tiers, converted):
                tier_liability = (base * pct).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total_computed += tier_liability
                computed_tiers.append({
                    **tier,
                    "computed_liability": float(tier_liability)
                })

            difference = abs(total_computed - claimed)
        except DecimalException:
            # Finite but extreme magnitudes can exceed the decimal context
            # (quantize precision / context range) — fail closed (PR #44).
            return _unverifiable_tiered_result(
                _RANGE_MESSAGE,
                all_tier_inputs,
            )
        
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
        named_inputs = {
            "annual_fee": annual_fee,
            "multiplier": multiplier,
            "claimed_limit": claimed_limit,
        }

        invalid = _invalid_names(named_inputs)
        if invalid:
            return _unverifiable_result(
                f"Input value(s) ({', '.join(invalid)}) cannot be "
                "verified — values must be finite decimal numbers "
                "(non-finite or malformed inputs cannot be quantized "
                "or compared deterministically).",
                named_inputs,
            )

        fee = Decimal(str(annual_fee))
        mult = Decimal(str(multiplier))
        claimed = Decimal(str(claimed_limit))

        try:
            computed = (fee * mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            difference = abs(computed - claimed)
        except DecimalException:
            # Finite but extreme magnitudes can exceed the decimal context
            # (quantize precision / context range) — fail closed (PR #44).
            return _unverifiable_result(
                _RANGE_MESSAGE,
                named_inputs,
            )
        
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
