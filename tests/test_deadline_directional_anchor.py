"""Regression tests for GHSA-mrv2-8596-cx34.

DeadlineGuard must fail closed (UNVERIFIABLE) when a term is:
  N1 — directional ("30 days before/prior to signing"), which measures the
       period backward, not forward; and
  N2 — anchored to an event outside the signing/execution reference
       ("30 days after closing", "within 30 days of request"), whose real
       reference date is unknown.

Bare-relative terms ("30 days") and affirmatively signing-anchored terms
("30 days from signing", "15 days after execution") must still VERIFY.
"""

from qwed_legal import DeadlineGuard
from qwed_legal.diagnostics import LegalDiagnosticStatus


class TestDirectionalTermsFailClosed:
    """N1: directional wording must never compute forward from signing."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_before_signing_not_verified(self):
        # Claim is signing+30; "before signing" means signing-30. The forward
        # computation would certify the opposite direction.
        result = self.guard.verify("2026-01-15", "30 days before signing", "2026-02-14")
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_prior_to_signing_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days prior to signing", "2026-02-14")
        assert result.verified is False

    def test_ahead_of_signing_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days ahead of signing", "2026-02-14")
        assert result.verified is False

    def test_preceding_signing_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days preceding signing", "2026-02-14")
        assert result.verified is False

    def test_directional_trace_is_unsupported(self):
        result = self.guard.verify("2026-01-15", "30 days before signing", "2026-02-14")
        assert len(result.verification_trace) == 1
        step = result.verification_trace[0]
        assert step.evidence_type == "UNSUPPORTED"
        assert "directional" in step.output.lower()


class TestUnlistedEventAnchorsFailClosed:
    """N2: event anchors beyond the denylist must fail closed."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_after_closing_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days after closing", "2026-02-14")
        assert result.verified is False
        assert result.computed_deadline is None

    def test_after_completion_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days after completion", "2026-02-14")
        assert result.verified is False

    def test_after_notification_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days after notification", "2026-02-14")
        assert result.verified is False

    def test_after_effective_date_not_verified(self):
        result = self.guard.verify(
            "2026-01-15", "30 days after the Effective Date", "2026-02-14"
        )
        assert result.verified is False

    def test_from_completion_not_verified(self):
        result = self.guard.verify("2026-01-15", "30 days from completion", "2026-02-14")
        assert result.verified is False

    def test_within_of_request_not_verified(self):
        result = self.guard.verify(
            "2026-01-15", "within 30 days of request", "2026-02-14"
        )
        assert result.verified is False

    def test_wide_gap_listed_noun_not_verified(self):
        # A >2-word adjective gap previously slipped a denylisted noun through.
        result = self.guard.verify(
            "2026-01-15", "30 days after the said written receipt", "2026-02-14"
        )
        assert result.verified is False

    def test_event_anchor_trace_is_unsupported(self):
        result = self.guard.verify("2026-01-15", "30 days after closing", "2026-02-14")
        assert len(result.verification_trace) == 1
        assert result.verification_trace[0].evidence_type == "UNSUPPORTED"


class TestLegitimateTermsStillVerify:
    """The allowlist inversion must not regress supported terms."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_bare_relative_days(self):
        assert self.guard.verify("2026-01-15", "30 days", "2026-02-14").verified is True

    def test_from_signing(self):
        assert self.guard.verify(
            "2026-01-01", "30 days from signing", "2026-01-31"
        ).verified is True

    def test_after_execution(self):
        assert self.guard.verify(
            "2026-01-01", "15 days after execution", "2026-01-16"
        ).verified is True

    def test_business_days_bare(self):
        assert self.guard.verify(
            "2026-01-01", "10 business days", "2026-01-15"
        ).verified is True

    def test_weeks_and_months_bare(self):
        assert self.guard.verify("2026-01-01", "2 weeks", "2026-01-15").verified is True
        assert self.guard.verify("2026-01-01", "3 months", "2026-04-01").verified is True
