"""
Tests for StatuteOfLimitationsGuard fail-closed enforcement (Issue #14).

Covers:
- Unknown jurisdictions return UNVERIFIABLE
- Unknown claim types return UNVERIFIABLE
- Partial string matching is eliminated
- Valid jurisdiction + claim type still works
- get_limitation_period returns None for unknowns
"""

from qwed_legal import StatuteOfLimitationsGuard


class TestStatuteGuardFailClosed:
    """Issue #14: StatuteGuard must not fabricate limitation periods."""

    def setup_method(self):
        self.guard = StatuteOfLimitationsGuard()

    # ── Unknown jurisdictions ─────────────────────────────────────

    def test_unknown_jurisdiction_is_unverifiable(self):
        """'Mars Colony' is not a real jurisdiction — must fail closed."""
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="Mars Colony",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False
        assert result.limitation_period_years is None
        assert result.expiration_date is None
        assert "UNVERIFIABLE" in result.message

    def test_gibberish_jurisdiction_is_unverifiable(self):
        """Random string jurisdiction — must fail closed."""
        result = self.guard.verify(
            claim_type="negligence",
            jurisdiction="xyzabc123",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False
        assert "UNVERIFIABLE" in result.message

    def test_partial_match_no_longer_works(self):
        """'CALIF' should NOT partially match 'CALIFORNIA' — fail closed."""
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="CALIF",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False
        assert "UNVERIFIABLE" in result.message

    def test_substring_jurisdiction_no_longer_matches(self):
        """'NEW' should NOT match 'NEW YORK' — fail closed."""
        result = self.guard.verify(
            claim_type="fraud",
            jurisdiction="NEW",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False

    def test_superset_jurisdiction_no_longer_matches(self):
        """'CALIFORNIA STATE' should NOT match 'CALIFORNIA' — fail closed."""
        result = self.guard.verify(
            claim_type="negligence",
            jurisdiction="CALIFORNIA STATE",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False

    # ── Unknown claim types ───────────────────────────────────────

    def test_unknown_claim_type_is_unverifiable(self):
        """'antitrust' is not in the supported claim types — must fail closed."""
        result = self.guard.verify(
            claim_type="antitrust",
            jurisdiction="California",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is True
        assert result.claim_type_matched is False
        assert result.limitation_period_years is None
        assert "UNVERIFIABLE" in result.message

    def test_gibberish_claim_type_is_unverifiable(self):
        """Random claim type — must fail closed."""
        result = self.guard.verify(
            claim_type="space_piracy",
            jurisdiction="New York",
            incident_date="2020-01-01",
            filing_date="2022-01-01",
        )
        assert result.verified is False
        assert result.claim_type_matched is False
        assert "UNVERIFIABLE" in result.message

    # ── Valid inputs still work ────────────────────────────────────

    def test_valid_california_breach_of_contract(self):
        """Known jurisdiction + known claim type — must still verify."""
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2024-01-15",
            filing_date="2026-06-01",
        )
        assert result.verified is True
        assert result.jurisdiction_matched is True
        assert result.claim_type_matched is True
        assert result.limitation_period_years == 4.0
        assert "WITHIN" in result.message

    def test_valid_expired_claim(self):
        """Valid inputs but expired — verified=False, but still matched."""
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2018-01-15",
            filing_date="2026-06-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is True
        assert result.claim_type_matched is True
        assert "EXPIRED" in result.message

    # ── get_limitation_period fail-closed ──────────────────────────

    def test_get_period_unknown_jurisdiction_returns_none(self):
        """get_limitation_period must return None for unknown jurisdiction."""
        period = self.guard.get_limitation_period("breach_of_contract", "Mars")
        assert period is None

    def test_get_period_unknown_claim_type_returns_none(self):
        """get_limitation_period must return None for unknown claim type."""
        period = self.guard.get_limitation_period("antitrust", "California")
        assert period is None

    def test_get_period_valid_returns_value(self):
        """get_limitation_period for known inputs still works."""
        period = self.guard.get_limitation_period("breach_of_contract", "California")
        assert period == 4.0

    # ── compare_jurisdictions with unknowns ────────────────────────

    def test_compare_with_unknown_jurisdiction_returns_none(self):
        """compare_jurisdictions includes None for unknown jurisdictions."""
        comparison = self.guard.compare_jurisdictions(
            "breach_of_contract", ["California", "Mars Colony"]
        )
        assert comparison["California"] == 4.0
        assert comparison["Mars Colony"] is None

    # ── Date parsing errors ───────────────────────────────────────

    def test_invalid_date_fails_closed(self):
        """Unparseable date — must fail closed."""
        result = self.guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="not-a-date",
            filing_date="2026-01-01",
        )
        assert result.verified is False
        assert result.jurisdiction_matched is False
        assert result.incident_date is None
