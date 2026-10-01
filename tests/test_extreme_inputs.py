"""
Tests for extreme-input crash hardening (Issue #42, item 4).

Covers:
- LiabilityGuard: Infinity/NaN inputs fail closed instead of raising
  decimal.InvalidOperation or failing closed only by NaN-comparison accident
- DeadlineGuard: astronomical quantities fail closed instead of raising
  OverflowError; the business-day loop is bounded (no multi-second DoS)
"""

import time

import pytest

from qwed_legal import DeadlineGuard, LiabilityGuard
from qwed_legal.diagnostics import LegalDiagnosticStatus
from qwed_legal.guards.citation_guard import CitationGuard
from qwed_legal.guards.clause_guard import ClauseGuard
from qwed_legal.guards.contradiction_guard import Clause, ContradictionGuard


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

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"contract_value": "abc"},
            {"cap_percentage": "abc"},
            {"claimed_cap": "abc"},
        ],
        ids=["contract_value", "cap_percentage", "claimed_cap"],
    )
    def test_cap_non_decimal_scalar_fails_closed(self, kwargs):
        """verify_cap must fail closed on non-numeric scalar inputs —
        _invalid_names runs before any exception handler
        (PR #44 review, Sentry/CodeRabbit)."""
        values = {
            "contract_value": 5_000_000,
            "cap_percentage": 200,
            "claimed_cap": 10_000_000,
        }
        values.update(kwargs)
        result = self.guard.verify_cap(**values)
        assert result.verified is False
        assert result.computed_cap is None
        assert "UNVERIFIABLE" in result.message

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"annual_fee": "abc"},
            {"multiplier": "abc"},
            {"claimed_limit": "abc"},
        ],
        ids=["annual_fee", "multiplier", "claimed_limit"],
    )
    def test_indemnity_non_decimal_scalar_fails_closed(self, kwargs):
        """All six scalar inputs across the two scalar paths must fail
        closed on non-numeric values."""
        values = {
            "annual_fee": 100_000,
            "multiplier": 3,
            "claimed_limit": 300_000,
        }
        values.update(kwargs)
        result = self.guard.verify_indemnity_limit(**values)
        assert result.verified is False
        assert result.computed_cap is None
        assert "UNVERIFIABLE" in result.message

    def test_non_finite_message_names_only_offending_inputs(self):
        """The failure message must name exactly the non-finite inputs,
        not implicate all of them (PR #44 review, Sentry)."""
        result = self.guard.verify_cap(5_000_000, 200, float("nan"))
        assert "claimed_cap" in result.message
        assert "contract_value" not in result.message
        assert "cap_percentage" not in result.message

    def test_tiered_empty_list_fails_closed(self):
        """Issue #76: an empty tier list has no operands to sum — ([], 0)
        previously minted verified=True (vacuous 0 == 0 match). Must be
        UNVERIFIABLE for every zero-valued claimed_total spelling, with
        no proof_ref at the diagnostic layer (the authority bit)."""
        for claimed in (0, 0.0, "0", "0.00"):
            result = self.guard.verify_tiered_liability([], claimed)
            assert result.verified is False
            assert result.total_computed is None
            assert "UNVERIFIABLE" in result.message
            diagnostic = result.to_diagnostic({"claimed_total": claimed})
            assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
            assert diagnostic.proof_ref is None

    def test_tiered_empty_list_nonzero_claim_is_unverifiable(self):
        """Empty tiers prove nothing about any total: with zero operands
        there is no computed sum, so even a nonzero claim is UNVERIFIABLE
        rather than BLOCKED. This is a deliberate change from the old
        vacuous 0.00-vs-claim mismatch — $0.00 was never computed, so
        asserting it as a finding would be false precision. Authority
        outcome is unchanged (no proof_ref either way)."""
        result = self.guard.verify_tiered_liability([], 1000)
        assert result.verified is False
        assert result.total_computed is None
        assert "UNVERIFIABLE" in result.message
        diagnostic = result.to_diagnostic({"claimed_total": 1000})
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert diagnostic.proof_ref is None

    def test_tiered_single_tier_still_verifies(self):
        """The empty-list refusal must not break the normal path: one
        real operand that matches still verifies."""
        result = self.guard.verify_tiered_liability(
            [{"base": 1_000_000, "percentage": 100}], 1_000_000
        )
        assert result.verified is True

    def test_normal_values_unaffected(self):
        result = self.guard.verify_cap(5_000_000, 200, 10_000_000)
        assert result.verified is True
        assert result.computed_cap == 10_000_000


class TestClauseCardinalityBounds:
    """Issue #75: pairwise work and retained output scale as n^2 — bound
    cardinality, per-item length and accumulation, all fail-closed."""

    def setup_method(self):
        self.guard = ClauseGuard()

    def test_huge_array_rejected_fast(self):
        clauses = ["Seller may terminate with 30 days notice"] * 5000
        start = time.perf_counter()
        result = self.guard.check_consistency(clauses)
        elapsed = time.perf_counter() - start
        assert result.consistent is False
        assert result.status == "invalid_input"
        assert elapsed < 1.0

    def test_boundary_201_rejected_200_evaluated(self):
        pair = [
            "Seller may terminate with 10 days notice",
            "Neither party may terminate before 30 days",
        ]
        over = (pair * 101)[:201]
        assert self.guard.check_consistency(over).status == "invalid_input"
        at = (pair * 100)[:200]
        result = self.guard.check_consistency(at)
        assert result.status == "contradiction"

    def test_conflicts_capped_with_disclosure(self):
        pair = [
            "Seller may terminate with 10 days notice",
            "Neither party may terminate before 30 days",
        ]
        clauses = (pair * 80)[:160]
        result = self.guard.check_consistency(clauses)
        assert result.status == "contradiction"
        assert len(result.conflicts) == ClauseGuard._MAX_CONFLICTS
        assert "truncated" in result.message

    def test_single_overlong_clause_rejected(self):
        result = self.guard.check_consistency(["x" * 4097])
        assert result.consistent is False
        assert result.status == "invalid_input"

    def test_single_max_length_clause_uses_short_circuit(self):
        """A 4096-char single clause passes the length gate and reaches
        the pre-existing insufficient-input path (not invalid_input)."""
        result = self.guard.check_consistency(["x" * 4096])
        assert result.consistent is False
        assert result.status == "insufficient_input"


class TestCitationRegexBounds:
    """Issue #79: the case-prefix group backtracked cubically on
    digit-free ' v. '-floods. The prefix is gone; positional enforcement
    covers it in linear time."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_adversarial_flood_is_fast(self):
        start = time.perf_counter()
        result = self.guard.verify("a v. " * 160 + "x")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0
        assert result.verified is False

    def test_canonical_citations_unaffected(self):
        assert self.guard.verify("Brown v. Board, 347 U.S. 483").format_valid is True
        result = self.guard.verify("Smith v. Jones, 123 F.3d 456")
        assert result.format_valid is True


class TestLongDigitRunsFailClosed:
    """Issue #80: CPython caps int() conversion at 4300 digits — bound
    the run before coercion at all five sites, fail closed."""

    def test_deadline_long_run_fails_closed(self):
        result = DeadlineGuard().verify("2026-01-01", "9" * 4301 + " days", "2026-02-01")
        assert result.verified is False

    def test_clause_long_runs_fail_closed(self):
        guard = ClauseGuard()
        result = guard.check_consistency(
            [
                "Seller may terminate with 30 days notice",
                "notice " + "9" * 4301 + " days",
            ]
        )
        assert result.consistent is False
        # The 4314-char clause trips the length gate first: exact status
        # pins which layer refused it.
        assert result.status == "invalid_input"

    def test_overlong_digit_run_beside_valid_is_skipped(self):
        """CodeRabbit review: an over-long run next to a valid value must
        not poison the valid extraction — the uninterpretable token is
        skipped and the clean association stands (same verdict as the
        input with the over-long token removed)."""
        guard = ClauseGuard()
        assert (
            guard._extract_days(
                "notice within " + "9" * 4301 + " days and notice within 30 days",
                "notice",
            )
            == 30
        )
        assert (
            guard._extract_days("notice " + "9" * 4301 + " days", "notice") is None
        )

    def test_contradiction_long_run_fails_closed(self):
        guard = ContradictionGuard()
        result = guard.verify_consistency(
            [Clause(text="exactly " + "9" * 4301, category="DURATION", value=1)]
        )
        assert result["verified"] is False
        assert result["status"] == "partial_coverage"

    def test_normal_numbers_unaffected(self):
        result = DeadlineGuard().verify("2026-01-01", "30 days", "2026-01-31")
        assert result.verified is True
