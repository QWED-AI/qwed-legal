"""
Tests for DeadlineGuard fail-closed enforcement (Issue #15).

Covers:
- Ambiguous terms without numeric quantities return UNVERIFIABLE
- Terms with numbers but no time unit return UNVERIFIABLE
- Valid terms with explicit quantities still work
- is_computable flag is correctly set
"""

from qwed_legal import DeadlineGuard


class TestDeadlineGuardFailClosed:
    """Issue #15: DeadlineGuard must not invent deadlines from ambiguous text."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    # ── Ambiguous terms (no number, no unit) ──────────────────────

    def test_reasonable_period_is_unverifiable(self):
        """'within a reasonable period' has no numeric quantity — must fail closed."""
        result = self.guard.verify("2026-01-01", "within a reasonable period", "2026-01-31")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert result.difference_days is None
        assert "UNVERIFIABLE" in result.message

    def test_promptly_after_notice_is_unverifiable(self):
        """'promptly after notice' is legally ambiguous — must fail closed."""
        result = self.guard.verify("2026-01-01", "promptly after notice", "2026-01-15")
        assert result.verified is False
        assert result.is_computable is False
        assert "UNVERIFIABLE" in result.message

    def test_as_soon_as_practicable_is_unverifiable(self):
        """'as soon as practicable' — no deterministic deadline possible."""
        result = self.guard.verify("2026-01-01", "as soon as practicable", "2026-02-01")
        assert result.verified is False
        assert result.is_computable is False

    def test_without_undue_delay_is_unverifiable(self):
        """'without undue delay' — subjective legal language, not computable."""
        result = self.guard.verify("2026-01-01", "without undue delay", "2026-01-10")
        assert result.verified is False
        assert result.is_computable is False

    def test_forthwith_is_unverifiable(self):
        """'forthwith' — archaic legal term with no fixed meaning."""
        result = self.guard.verify("2026-01-01", "forthwith", "2026-01-02")
        assert result.verified is False
        assert result.is_computable is False

    # ── Number found but no recognizable time unit ────────────────

    def test_number_without_unit_is_unverifiable(self):
        """'30' alone (no unit like 'days') — ambiguous, must fail closed."""
        result = self.guard.verify("2026-01-01", "30", "2026-01-31")
        assert result.verified is False
        assert result.is_computable is False
        assert "UNVERIFIABLE" in result.message

    def test_number_with_nonsense_unit_is_unverifiable(self):
        """'15 intervals' — 'intervals' is not a recognized time unit."""
        result = self.guard.verify("2026-01-01", "15 intervals", "2026-01-16")
        assert result.verified is False
        assert result.is_computable is False

    # ── Valid terms still work correctly ───────────────────────────

    def test_explicit_days_still_works(self):
        """'30 days' — explicit number + unit, must still verify."""
        result = self.guard.verify("2026-01-01", "30 days", "2026-01-31")
        assert result.verified is True
        assert result.is_computable is True
        assert result.computed_deadline is not None

    def test_explicit_business_days_still_works(self):
        """'10 business days' — explicit, must still compute."""
        result = self.guard.verify("2026-01-01", "10 business days", "2026-01-16")
        assert result.is_computable is True
        assert result.computed_deadline is not None

    def test_explicit_weeks_still_works(self):
        """'2 weeks' — explicit, must still verify."""
        result = self.guard.verify("2026-01-01", "2 weeks", "2026-01-15")
        assert result.verified is True
        assert result.is_computable is True

    def test_explicit_months_still_works(self):
        """'3 months' — explicit, must still verify."""
        result = self.guard.verify("2026-01-01", "3 months", "2026-04-01")
        assert result.verified is True
        assert result.is_computable is True

    def test_explicit_years_still_works(self):
        """'1 year' — explicit, must still verify."""
        result = self.guard.verify("2026-01-01", "1 year", "2027-01-01")
        assert result.verified is True
        assert result.is_computable is True

    def test_calendar_days_explicit(self):
        """'14 calendar days' — explicit variant, must work."""
        result = self.guard.verify("2026-01-01", "14 calendar days", "2026-01-15")
        assert result.verified is True
        assert result.is_computable is True

    # ── Date parsing errors also fail closed ──────────────────────

    def test_invalid_date_fails_closed(self):
        """Unparseable date must return is_computable=False."""
        result = self.guard.verify("not-a-date", "30 days", "2026-01-31")
        assert result.verified is False
        assert result.is_computable is False
