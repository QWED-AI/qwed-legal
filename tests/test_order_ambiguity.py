"""Order-ambiguity fail-closed enforcement (issues #55, #58).

Numeric dates like "03/04/2026" verify under month-first and refute under
day-first with no signal. Both guards share one dual-parse helper
(qwed_legal.dates.detect_order_ambiguity) and must refuse to certify either
reading, emitting AMBIGUITY_NOTED with the raw strings preserved.
"""

from qwed_legal import DeadlineGuard, StatuteOfLimitationsGuard
from qwed_legal.dates import detect_order_ambiguity
from qwed_legal.diagnostics import LegalDiagnosticStatus
from qwed_legal.models import STEP_AMBIGUITY_NOTED


class TestDetectOrderAmbiguity:
    """Shared helper unit tests."""

    def test_ambiguous_slash_dates_detected(self):
        assert detect_order_ambiguity("03/04/2026") is True
        assert detect_order_ambiguity("04/03/2026") is True
        assert detect_order_ambiguity("02/01/2024") is True

    def test_impossible_month_is_not_ambiguous(self):
        # 13 cannot be a month — only the day-first reading parses.
        assert detect_order_ambiguity("13/04/2026") is False

    def test_iso_year_leading_is_excluded(self):
        assert detect_order_ambiguity("2026-04-03") is False
        assert detect_order_ambiguity("2026/04/03") is False

    def test_named_months_are_not_ambiguous(self):
        assert detect_order_ambiguity("March 4, 2026") is False
        assert detect_order_ambiguity("4 March 2026") is False

    def test_unparseable_and_empty_are_not_ambiguous(self):
        # Unparseable inputs fail closed downstream at parse time, not here.
        assert detect_order_ambiguity("not a date") is False
        assert detect_order_ambiguity("") is False


class TestDeadlineOrderAmbiguity:
    """Issue #55: DeadlineGuard must not certify either reading."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_issue_repro_fails_closed(self):
        result = self.guard.verify("03/04/2026", "30 days", "04/03/2026")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_ambiguity_step_emitted_with_raw_strings(self):
        result = self.guard.verify("03/04/2026", "30 days", "04/03/2026")
        steps = [s.step for s in result.verification_trace]
        assert STEP_AMBIGUITY_NOTED in steps
        noted = result.verification_trace[steps.index(STEP_AMBIGUITY_NOTED)]
        assert noted.inputs["signing_date"] == "03/04/2026"
        assert noted.inputs["claimed_deadline"] == "04/03/2026"

    def test_claimed_side_ambiguity_fails_closed(self):
        result = self.guard.verify("2026-01-01", "30 days", "04/03/2026")
        assert result.verified is False
        assert result.is_computable is False

    def test_iso_dates_still_verify(self):
        result = self.guard.verify("2026-01-01", "30 days", "2026-01-31")
        assert result.verified is True

    def test_named_month_dates_still_verify(self):
        result = self.guard.verify("March 4, 2026", "30 days", "2026-04-03")
        assert result.verified is True


class TestBusinessDaysCalculatorAmbiguity:
    """CodeAnt review on #90: the calculator must not silently count."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_ambiguous_inputs_raise(self):
        import pytest

        with pytest.raises(ValueError, match="Order-ambiguous"):
            self.guard.calculate_business_days_between("03/04/2026", "2026-05-01")
        with pytest.raises(ValueError, match="Order-ambiguous"):
            self.guard.calculate_business_days_between("2026-04-01", "04/03/2026")

    def test_unambiguous_inputs_still_count(self):
        count = self.guard.calculate_business_days_between("2026-04-01", "2026-04-08")
        assert count == 5


class TestStatuteOrderAmbiguity:
    """Issue #58: StatuteGuard must not certify WITHIN on ambiguity."""

    def setup_method(self):
        self.guard = StatuteOfLimitationsGuard()

    def test_issue_repro_fails_closed(self):
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="02/01/2024",
            filing_date="01/02/2026",
            claimed_within_period=True,
        )
        assert result.verified is False
        assert result.status == "UNVERIFIABLE"
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_no_deterministic_labels_on_ambiguity(self):
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="02/01/2024",
            filing_date="01/02/2026",
            claimed_within_period=True,
        )
        assert all(s.evidence_type != "DETERMINISTIC" for s in result.verification_trace)
        steps = [s.step for s in result.verification_trace]
        assert STEP_AMBIGUITY_NOTED in steps

    def test_computation_only_mode_is_gated_too(self):
        # Without claimed_within_period the ambiguity gate must still sit
        # before computation — never COMPUTED_ONLY on ambiguous inputs.
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="02/01/2024",
            filing_date="01/02/2026",
        )
        assert result.status == "UNVERIFIABLE"
        assert result.expiration_date is None

    def test_iso_dates_still_verify(self):
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2024-01-15",
            filing_date="2026-01-10",
            claimed_within_period=True,
        )
        assert result.verified is True
        assert result.status == "CLAIM_VERIFIED"
