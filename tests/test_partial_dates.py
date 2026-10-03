"""Partial-date fail-closed enforcement (issues #57, #59).

dateutil fills missing components from the wall clock ("March 2024" takes
today's day-of-month), so identical inputs verify opposite verdicts on
different days. Both guards share one dual-sentinel helper
(qwed_legal.dates.detect_incomplete_date) and refuse partial dates before
any computation. The fail-closed path reads no clock, so nightly
re-verification is stable by construction. Parsed datetimes on the
rejection path are recorded as None — clock-contaminated values must not
be laundered into the result; raw strings stay in the trace.
"""

from qwed_legal import DeadlineGuard, StatuteOfLimitationsGuard
from qwed_legal.dates import detect_incomplete_date
from qwed_legal.diagnostics import LegalDiagnosticStatus
from qwed_legal.models import STEP_AMBIGUITY_NOTED


class TestDetectIncompleteDate:
    """Shared helper unit tests."""

    def test_partial_dates_detected(self):
        assert detect_incomplete_date("March 2024") is True
        assert detect_incomplete_date("April") is True
        assert detect_incomplete_date("2026") is True
        assert detect_incomplete_date("Friday") is True
        assert detect_incomplete_date("23:00") is True

    def test_complete_dates_pass(self):
        assert detect_incomplete_date("2026-04-03") is False
        assert detect_incomplete_date("03/04/2026") is False
        assert detect_incomplete_date("March 4, 2026") is False
        assert detect_incomplete_date("2026-01-15 23:00") is False

    def test_unparseable_and_empty_pass_through(self):
        # Unparseable inputs fail closed downstream at parse time, not here.
        assert detect_incomplete_date("not a date") is False
        assert detect_incomplete_date("") is False


class TestDeadlinePartialDates:
    """Issue #57 (deadline prong)."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_month_only_signing_fails_closed(self):
        result = self.guard.verify("March 2024", "30 days", "2026-04-15")
        assert result.verified is False
        assert result.is_computable is False
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_contaminated_datetimes_not_recorded(self):
        result = self.guard.verify("March 2024", "30 days", "2026-04-15")
        assert result.signing_date is None
        steps = [s.step for s in result.verification_trace]
        assert STEP_AMBIGUITY_NOTED in steps

    def test_relative_weekday_fails_closed(self):
        result = self.guard.verify("Friday", "30 days", "2026-04-15")
        assert result.verified is False
        assert result.is_computable is False

    def test_complete_datetime_with_time_still_verifies(self):
        result = self.guard.verify("2026-01-15 23:00", "30 days", "2026-02-14 23:00")
        assert result.verified is True

    def test_iso_dates_still_verify(self):
        result = self.guard.verify("2026-01-01", "30 days", "2026-01-31")
        assert result.verified is True


class TestStatutePartialDates:
    """Issue #59: statute-side acceptance, stable across run days."""

    def setup_method(self):
        self.guard = StatuteOfLimitationsGuard()

    def test_month_only_intake_never_verifies(self):
        # Canonical #59 case: must not be ACCEPT on some days and DECLINE
        # on others — UNVERIFIABLE on every run day by construction.
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="March 2024",
            filing_date="2026-04-01",
            claimed_within_period=True,
        )
        assert result.verified is False
        assert result.status == "UNVERIFIABLE"
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_computation_only_mode_is_gated_too(self):
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="March 2024",
            filing_date="2026-04-01",
        )
        assert result.status == "UNVERIFIABLE"
        assert result.expiration_date is None

    def test_no_deterministic_labels_on_partial(self):
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="March 2024",
            filing_date="2026-04-01",
            claimed_within_period=True,
        )
        assert all(s.evidence_type != "DETERMINISTIC" for s in result.verification_trace)

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
