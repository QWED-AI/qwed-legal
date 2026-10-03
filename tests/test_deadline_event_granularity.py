"""Deadline comparison-layer fixes (issues #54, #56).

#54: event-anchored terms ("within 15 days after receipt of written
notice") must fail closed instead of computing from the signing date.
#56: claimed-vs-computed comparison runs at date granularity so sub-daily
offsets cannot floor to a false exact match.
"""

from qwed_legal import DeadlineGuard
from qwed_legal.diagnostics import LegalDiagnosticStatus


class TestEventAnchoredTerms:
    """Issue #54."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_issue_repro_fails_closed(self):
        result = self.guard.verify(
            "2026-01-01",
            "within 15 days after receipt of written notice",
            "2026-01-16",
        )
        assert result.verified is False
        assert result.is_computable is False
        assert result.computed_deadline is None
        assert result.to_diagnostic().status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_anchor_word_named_in_message(self):
        result = self.guard.verify(
            "2026-01-01", "within 15 days after receipt of written notice", "2026-01-16"
        )
        assert "receipt" in result.message
        assert "Expected" not in result.message

    def test_anchor_variants_fails_closed(self):
        for term in (
            "30 days after delivery",
            "15 days following termination",
            "30 days after demand",
            "60 days after breach",
            "45 days after invoice",
            "10 days after occurrence",
            "WITHIN 15 DAYS AFTER RECEIPT",
            "30 days after acceptance",
            "15 days after payment",
            "15 days after receipts",
            "15 days after deliveries",
            "10 days after written notice",
        ):
            result = self.guard.verify("2026-01-01", term, "2026-02-01")
            assert result.verified is False, term
            assert result.is_computable is False, term

    def test_signing_mentions_do_not_trigger_event_gate(self):
        # "notice" here is the obligation, not the anchor: the period
        # starts at signing, which the guard can compute.
        result = self.guard.verify(
            "2026-01-01", "30 days from signing to deliver notice", "2026-01-31"
        )
        assert result.verified is True

    def test_signing_anchored_terms_still_verify(self):
        assert self.guard.verify("2026-01-01", "30 days", "2026-01-31").verified is True
        assert (
            self.guard.verify("2026-01-01", "30 days from signing", "2026-01-31").verified
            is True
        )
        assert (
            self.guard.verify("2026-01-01", "15 days after execution", "2026-01-16").verified
            is True
        )


class TestDateGranularityComparison:
    """Issue #56."""

    def setup_method(self):
        self.guard = DeadlineGuard()

    def test_issue_repro_one_day_late_is_mismatch(self):
        result = self.guard.verify("2026-01-15 23:00", "30 days", "2026-02-15")
        assert result.verified is False
        assert result.difference_days == 1

    def test_same_date_sub_daily_noise_verifies(self):
        # Computed 2026-02-14 23:00 vs claimed 2026-02-14 10:00: same date.
        result = self.guard.verify("2026-01-15 23:00", "30 days", "2026-02-14 10:00")
        assert result.verified is True
        assert result.difference_days == 0

    def test_early_same_date_verifies(self):
        # 23h early but the same calendar date: not a day-level mismatch.
        result = self.guard.verify("2026-01-15 23:00", "30 days", "2026-02-14 00:00")
        assert result.verified is True

    def test_exact_date_still_verifies(self):
        assert self.guard.verify("2026-01-15", "30 days", "2026-02-14").verified is True

    def test_tolerance_applies_at_date_granularity(self):
        result = self.guard.verify("2026-01-15", "30 days", "2026-02-15", tolerance_days=1)
        assert result.verified is True
        assert result.difference_days == 1

    def test_same_moment_different_offsets_verifies(self):
        # 2026-02-14 20:00-05:00 == 2026-02-15 01:00+00:00: compared in the
        # deadline's frame, not UTC, so no false mismatch.
        result = self.guard.verify(
            "2026-01-15 20:00-05:00", "30 days", "2026-02-15 01:00+00:00"
        )
        assert result.verified is True
        assert result.difference_days == 0

    def test_next_day_in_deadline_frame_is_mismatch(self):
        # Same region, next local day: Feb 15 00:00+05:00 is not Feb 14,
        # even though both fall on Feb 14 in UTC.
        result = self.guard.verify(
            "2026-01-15 23:00+05:00", "30 days", "2026-02-15 00:00+05:00"
        )
        assert result.verified is False
        assert result.difference_days == 1

    def test_mismatch_message_reports_compared_days(self):
        # The message must never show identical dates with a non-zero
        # difference: it reports the normalized comparison days.
        result = self.guard.verify(
            "2026-01-15 23:00+05:00", "30 days", "2026-02-14 22:00-08:00"
        )
        assert result.verified is False
        assert "Expected 2026-02-14" in result.message
        assert "claimed 2026-02-15" in result.message
        assert "Difference: 1 days." in result.message
