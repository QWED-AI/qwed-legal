"""
Tests for extreme-input crash hardening (Issue #42, item 4).

Covers:
- LiabilityGuard: Infinity/NaN inputs fail closed instead of raising
  decimal.InvalidOperation or failing closed only by NaN-comparison accident
- DeadlineGuard: astronomical quantities fail closed instead of raising
  OverflowError; the business-day loop is bounded (no multi-second DoS)
"""

import time

from qwed_legal import DeadlineGuard, LiabilityGuard


class TestLiabilityGuardNonFiniteInputs:
    """Issue #42: non-finite values must return UNVERIFIABLE, never raise."""

    def setup_method(self):
        self.guard = LiabilityGuard()

    def test_infinite_contract_value_fails_closed(self):
        """contract_value=float('inf') raised decimal.InvalidOperation."""
        result = self.guard.verify_cap(float("inf"), 200, 10_000_000)
        assert result.verified is False
        assert result.computed_cap is None
        assert result.difference is None
        assert "UNVERIFIABLE" in result.message

    def test_nan_cap_percentage_fails_closed(self):
        """NaN inputs previously failed closed only by comparison accident."""
        result = self.guard.verify_cap(5_000_000, float("nan"), 10_000_000)
        assert result.verified is False
        assert result.computed_cap is None
        assert "UNVERIFIABLE" in result.message

    def test_negative_infinite_claimed_cap_fails_closed(self):
        result = self.guard.verify_cap(5_000_000, 200, float("-inf"))
        assert result.verified is False
        assert "UNVERIFIABLE" in result.message

    def test_indemnity_limit_non_finite_fails_closed(self):
        result = self.guard.verify_indemnity_limit(100_000, float("inf"), 300_000)
        assert result.verified is False
        assert result.computed_cap is None
        assert "UNVERIFIABLE" in result.message

    def test_tiered_non_finite_base_fails_closed(self):
        result = self.guard.verify_tiered_liability(
            [{"base": float("inf"), "percentage": 100}], 1_000_000
        )
        assert result.verified is False
        assert result.total_computed is None
        assert result.claimed_total is None
        assert "UNVERIFIABLE" in result.message

    def test_tiered_non_finite_claimed_total_fails_closed(self):
        result = self.guard.verify_tiered_liability(
            [{"base": 1_000_000, "percentage": 100}], float("nan")
        )
        assert result.verified is False
        assert result.total_computed is None

    def test_valid_inputs_still_compute(self):
        """Finite values must be unaffected by the validation."""
        result = self.guard.verify_cap(5_000_000, 200, 10_000_000)
        assert result.verified is True
        assert result.computed_cap == 10_000_000


class TestDeadlineGuardExtremeQuantities:
    """Issue #42: astronomical quantities must fail closed, not crash or hang."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_huge_calendar_days_fail_closed(self):
        """'999999999 days' raised OverflowError: date value out of range."""
        result = self.guard.verify("2026-01-15", "999999999 days", "2029-01-15")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert "UNVERIFIABLE" in result.message

    def test_huge_business_days_fail_closed_fast(self):
        """'99999999 business days' looped ~3s before raising — must fail
        closed in bounded time."""
        start = time.time()
        result = self.guard.verify("2026-01-15", "99999999 business days", "2029-01-15")
        elapsed = time.time() - start
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert elapsed < 1.0

    def test_quantity_above_cap_fails_closed(self):
        """Above _MAX_TERM_QUANTITY (~274 years) — outside any legal term."""
        result = self.guard.verify("2026-01-15", "100001 days", "2299-06-03")
        assert result.verified is False
        assert result.is_computable is False

    def test_quantity_at_cap_still_computes(self):
        """At the cap boundary the computation remains available."""
        result = self.guard.verify("2026-01-15", "100000 days", "2299-10-31")
        assert result.is_computable is True
        assert result.computed_deadline is not None

    def test_huge_years_fail_closed(self):
        """relativedelta(years=10**9) exceeds the representable range."""
        result = self.guard.verify("2026-01-15", "1000000000 years", "2029-01-15")
        assert result.verified is False
        assert result.is_computable is False

    def test_business_weeks_at_normalized_cap_fail_closed(self):
        """'100000 business weeks' normalizes to 500,000 business days —
        the cap must apply AFTER the business-week conversion, not just
        to the raw quantity (PR #44 review)."""
        start = time.time()
        result = self.guard.verify("2026-01-15", "100000 business weeks", "2299-01-01")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert time.time() - start < 0.5

    def test_business_weeks_at_boundary_still_compute(self):
        """'20000 business weeks' = exactly 100,000 business days — at
        the cap boundary the computation remains available."""
        result = self.guard.verify("2026-01-15", "20000 business weeks", "2299-01-01")
        assert result.is_computable is True
        assert result.computed_deadline is not None


class TestLiabilityGuardFiniteExtremes:
    """PR #44 review: finite values can still exceed the decimal context —
    quantize raises InvalidOperation on huge magnitudes."""

    def setup_method(self):
        self.guard = LiabilityGuard()

    def test_cap_extreme_finite_magnitude_fails_closed(self):
        """1e308 is finite but 2e308 cannot be quantized to cents."""
        result = self.guard.verify_cap(1e308, 200, 10_000_000)
        assert result.verified is False
        assert result.computed_cap is None
        assert "UNVERIFIABLE" in result.message
        assert "decimal range" in result.message

    def test_indemnity_extreme_finite_magnitude_fails_closed(self):
        result = self.guard.verify_indemnity_limit(1e308, 200, 300_000)
        assert result.verified is False
        assert result.computed_cap is None

    def test_tiered_extreme_finite_magnitude_fails_closed(self):
        result = self.guard.verify_tiered_liability(
            [{"base": 1e308, "percentage": 100}], 1_000_000
        )
        assert result.verified is False
        assert result.total_computed is None

    def test_signaling_nan_tier_percentage_fails_closed(self):
        """Decimal('sNaN') raises InvalidOperation on the /100 division —
        the division must happen AFTER finiteness validation
        (PR #44 review, CodeRabbit)."""
        result = self.guard.verify_tiered_liability(
            [{"base": 1_000_000, "percentage": "sNaN"}], 1_000_000
        )
        assert result.verified is False
        assert result.total_computed is None
        assert result.claimed_total is None
        assert "UNVERIFIABLE" in result.message

    def test_signaling_nan_tier_base_fails_closed(self):
        result = self.guard.verify_tiered_liability(
            [{"base": "sNaN", "percentage": 100}], 1_000_000
        )
        assert result.verified is False
        assert result.total_computed is None

    def test_non_decimal_tier_value_fails_closed(self):
        """Non-numeric strings crash Decimal() construction — must fail
        closed, never raise."""
        result = self.guard.verify_tiered_liability(
            [{"base": 1_000_000, "percentage": "abc"}], 1_000_000
        )
        assert result.verified is False
        assert result.total_computed is None
        assert "UNVERIFIABLE" in result.message

    def test_non_finite_message_names_only_offending_inputs(self):
        """The failure message must name exactly the non-finite inputs,
        not implicate all of them (PR #44 review, Sentry)."""
        result = self.guard.verify_cap(5_000_000, 200, float("nan"))
        assert "claimed_cap" in result.message
        assert "contract_value" not in result.message
        assert "cap_percentage" not in result.message

    def test_normal_values_unaffected(self):
        result = self.guard.verify_cap(5_000_000, 200, 10_000_000)
        assert result.verified is True
        assert result.computed_cap == 10_000_000
