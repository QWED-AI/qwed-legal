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


class TestDeadlineGuardCompoundTerms:
    """Issue #39: compound terms must fail closed, not mispair number x unit."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_days_and_months_is_unverifiable(self):
        """'30 days and 2 months' — the exact #39 repro that produced a
        30-month deadline from the first number x last unit."""
        result = self.guard.verify(
            "2026-01-15", "30 days and 2 months from execution hereof", "2028-07-15"
        )
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert result.difference_days is None
        assert "UNVERIFIABLE" in result.message

    def test_business_days_and_weeks_is_unverifiable(self):
        """'10 business days and 4 weeks' — number 10 previously applied
        with business-day logic regardless of the weeks clause."""
        result = self.guard.verify("2026-01-15", "10 business days and 4 weeks", "2026-02-20")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_weeks_and_months_is_unverifiable(self):
        """'3 weeks or 1 month' — two expressions, ambiguous combination."""
        result = self.guard.verify("2026-01-15", "3 weeks or 1 month", "2026-02-05")
        assert result.verified is False
        assert result.is_computable is False

    def test_single_expression_still_computes(self):
        """One number-unit pair must keep computing normally."""
        result = self.guard.verify("2026-01-01", "30 days", "2026-01-31")
        assert result.verified is True
        assert result.is_computable is True
        assert result.computed_deadline is not None

    def test_unmatched_quantity_clause_reference_fails_closed(self):
        """A numeric token that is not the paired quantity — a clause
        reference like 4.2 — makes the term ambiguous. The pre-#39
        parser computed 4 days from the FIRST number; the positional
        parser must fail closed, not silently pick one interpretation."""
        result = self.guard.verify(
            "2026-01-01", "under section 4.2, notice is due within 30 days", "2026-01-31"
        )
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_alternative_quantities_fail_closed(self):
        """'30 or 60 days' — two quantities, one unit. The old parser
        silently applied the last number; must fail closed (Greptile P1)."""
        result = self.guard.verify("2026-01-15", "30 or 60 days", "2026-02-14")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_unsupported_unit_with_matched_quantity_fails_closed(self):
        """'30 days and 48 hours' — '30 days' matches but 48 is an
        unmatched quantity; must fail closed rather than silently ignore
        the hours clause (Greptile P1)."""
        result = self.guard.verify("2026-01-15", "30 days and 48 hours", "2026-02-14")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_decimal_quantity_fails_closed(self):
        """'2.5 years' — the quantity regex must not match the suffix
        digit '5' as a 5-year deadline; fractional quantities are not
        supported and must fail closed."""
        result = self.guard.verify("2026-01-15", "2.5 years", "2028-07-15")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_signed_quantity_fails_closed(self):
        """'-30 days' — signed quantities are not supported; must fail
        closed rather than drop the sign."""
        result = self.guard.verify("2026-01-15", "-30 days", "2026-02-14")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_embedded_number_fails_closed(self):
        """'section30days' — a number embedded in a word must not be
        read as a quantity/unit pair."""
        result = self.guard.verify("2026-01-15", "section30days", "2026-02-14")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_business_months_fails_closed(self):
        """'business months' has no deterministic calendar meaning —
        must fail closed instead of silently computing calendar months."""
        result = self.guard.verify("2026-01-15", "10 business months", "2026-11-15")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_working_years_fails_closed(self):
        """'working years' has no deterministic calendar meaning —
        must fail closed instead of silently computing calendar years."""
        result = self.guard.verify("2026-01-15", "2 working years", "2028-01-15")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None

    def test_business_qualifier_must_be_adjacent(self):
        """'business' elsewhere in the sentence must not turn calendar
        days into business days (previously matched anywhere in term)."""
        result = self.guard.verify(
            "2026-01-01", "30 days after the business closes the account", "2026-01-31"
        )
        assert result.verified is True
        assert result.is_computable is True
        assert result.computed_deadline.date().isoformat() == "2026-01-31"

    def test_compound_rejection_carries_trace_step(self):
        """The rejection must be recorded as an UNSUPPORTED trace step."""
        result = self.guard.verify("2026-01-15", "30 days and 2 months", "2028-07-15")
        assert len(result.verification_trace) == 1
        step = result.verification_trace[0]
        assert step.evidence_type == "UNSUPPORTED"
        assert "multiple conflicting time expressions" in step.output
