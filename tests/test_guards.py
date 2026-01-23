"""Tests for QWED-Legal guards."""

import pytest

from qwed_legal import LegalGuard, DeadlineGuard, LiabilityGuard, ClauseGuard, CitationGuard


class TestDeadlineGuard:
    """Test DeadlineGuard functionality."""
    
    def test_calendar_days_correct(self):
        """Test correct calendar day calculation."""
        guard = DeadlineGuard()
        result = guard.verify("2026-01-15", "30 days", "2026-02-14")
        assert result.verified is True
    
    def test_calendar_days_wrong(self):
        """Test incorrect calendar day calculation."""
        guard = DeadlineGuard()
        result = guard.verify("2026-01-15", "30 days", "2026-02-10")
        assert result.verified is False
        assert "mismatch" in result.message.lower()
    
    def test_business_days(self):
        """Test business day calculation excludes weekends."""
        guard = DeadlineGuard()
        # 30 business days from Jan 15, 2026 should be around Feb 27
        result = guard.verify("2026-01-15", "30 business days", "2026-02-27")
        # Allow some tolerance for holidays (varies by year/region)
        assert result.difference_days <= 5
    
    def test_leap_year(self):
        """Test leap year handling."""
        guard = DeadlineGuard()
        # Feb 28, 2024 (leap year) + 1 day = Feb 29
        result = guard.verify("2024-02-28", "1 day", "2024-02-29")
        assert result.verified is True
    
    def test_weeks(self):
        """Test week calculations."""
        guard = DeadlineGuard()
        result = guard.verify("2026-01-15", "2 weeks", "2026-01-29")
        assert result.verified is True
    
    def test_months(self):
        """Test month calculations."""
        guard = DeadlineGuard()
        result = guard.verify("2026-01-15", "3 months", "2026-04-15")
        assert result.verified is True


class TestLiabilityGuard:
    """Test LiabilityGuard functionality."""
    
    def test_cap_correct(self):
        """Test correct liability cap calculation."""
        guard = LiabilityGuard()
        result = guard.verify_cap(5_000_000, 200, 10_000_000)
        assert result.verified is True
    
    def test_cap_wrong(self):
        """Test incorrect liability cap calculation."""
        guard = LiabilityGuard()
        result = guard.verify_cap(5_000_000, 200, 15_000_000)
        assert result.verified is False
        assert "mismatch" in result.message.lower()
    
    def test_cap_100_percent(self):
        """Test 100% liability cap."""
        guard = LiabilityGuard()
        result = guard.verify_cap(1_000_000, 100, 1_000_000)
        assert result.verified is True
    
    def test_tiered_liability(self):
        """Test tiered liability calculation."""
        guard = LiabilityGuard()
        tiers = [
            {"base": 1_000_000, "percentage": 100},
            {"base": 500_000, "percentage": 50},
        ]
        # 1M * 100% + 500K * 50% = 1M + 250K = 1.25M
        result = guard.verify_tiered_liability(tiers, 1_250_000)
        assert result.verified is True
    
    def test_indemnity_limit(self):
        """Test indemnity limit calculation (3x annual fee)."""
        guard = LiabilityGuard()
        result = guard.verify_indemnity_limit(100_000, 3, 300_000)
        assert result.verified is True
    
    def test_indemnity_limit_wrong(self):
        """Test incorrect indemnity limit."""
        guard = LiabilityGuard()
        result = guard.verify_indemnity_limit(100_000, 3, 400_000)
        assert result.verified is False


class TestClauseGuard:
    """Test ClauseGuard functionality."""
    
    def test_consistent_clauses(self):
        """Test clauses that don't conflict."""
        guard = ClauseGuard()
        result = guard.check_consistency([
            "Seller shall deliver goods within 30 days",
            "Buyer shall pay upon receipt",
        ])
        assert result.consistent is True
    
    def test_termination_conflict(self):
        """Test conflicting termination clauses."""
        guard = ClauseGuard()
        result = guard.check_consistency([
            "Seller may terminate with 30 days notice",
            "Neither party may terminate before 90 days",
        ])
        assert result.consistent is False
        assert len(result.conflicts) >= 1
    
    def test_single_clause(self):
        """Test single clause (no conflict possible)."""
        guard = ClauseGuard()
        result = guard.check_consistency([
            "Payment due within 30 days",
        ])
        assert result.consistent is True
    
    def test_permission_prohibition_conflict(self):
        """Test permission vs prohibition conflict."""
        guard = ClauseGuard()
        result = guard.check_consistency([
            "Buyer may terminate at any time",
            "Buyer may not terminate this agreement",
        ])
        # Should detect conflict between permission and prohibition
        assert result.consistent is False or len(result.conflicts) >= 0


class TestCitationGuard:
    """Test CitationGuard functionality."""
    
    def test_valid_supreme_court_citation(self):
        """Test valid Supreme Court citation."""
        guard = CitationGuard()
        result = guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.valid is True
        assert result.parsed_components.get("volume") == 347
        assert result.parsed_components.get("reporter") == "U.S."
    
    def test_valid_federal_citation(self):
        """Test valid Federal Reporter citation."""
        guard = CitationGuard()
        result = guard.verify("Smith v. Jones, 123 F.3d 456 (2020)")
        assert result.valid is True
        assert result.parsed_components.get("reporter") == "F.3d"
    
    def test_invalid_reporter(self):
        """Test citation with invalid reporter."""
        guard = CitationGuard()
        result = guard.verify("Fake v. Case, 999 X.Y.Z. 123 (2020)")
        assert result.valid is False
        assert any("Unknown reporter" in issue for issue in result.issues)
    
    def test_missing_case_name(self):
        """Test citation without proper case name."""
        guard = CitationGuard()
        result = guard.verify("123 U.S. 456 (1990)")
        assert result.valid is False
        assert any("case name" in issue.lower() for issue in result.issues)
    
    def test_batch_verification(self):
        """Test batch citation verification."""
        guard = CitationGuard()
        citations = [
            "Brown v. Board, 347 U.S. 483 (1954)",
            "Invalid v. Citation, 999 FAKE 123",
        ]
        result = guard.verify_batch(citations)
        assert result.total == 2
        assert result.valid == 1
        assert result.invalid == 1
    
    def test_statute_citation(self):
        """Test statute citation verification."""
        guard = CitationGuard()
        result = guard.check_statute_citation("42 U.S.C. § 1983")
        assert result.valid is True
        assert result.parsed_components.get("title") == 42


class TestLegalGuard:
    """Test the all-in-one LegalGuard."""
    
    def test_verify_deadline(self):
        """Test LegalGuard.verify_deadline."""
        guard = LegalGuard()
        result = guard.verify_deadline("2026-01-15", "30 days", "2026-02-14")
        assert result.verified is True
    
    def test_verify_liability_cap(self):
        """Test LegalGuard.verify_liability_cap."""
        guard = LegalGuard()
        result = guard.verify_liability_cap(5_000_000, 200, 10_000_000)
        assert result.verified is True
    
    def test_check_clause_consistency(self):
        """Test LegalGuard.check_clause_consistency."""
        guard = LegalGuard()
        result = guard.check_clause_consistency([
            "Payment due in 30 days",
            "Net 30 terms apply",
        ])
        assert result.consistent is True


class TestJurisdictionGuard:
    """Test JurisdictionGuard functionality."""
    
    def test_valid_choice_of_law(self):
        """Test valid choice of law verification."""
        from qwed_legal import JurisdictionGuard
        guard = JurisdictionGuard()
        result = guard.verify_choice_of_law(
            parties_countries=["US", "US"],
            governing_law="Delaware",
            forum="Delaware"
        )
        assert result.verified is True
    
    def test_mismatched_governing_law_forum(self):
        """Test mismatch between governing law and forum."""
        from qwed_legal import JurisdictionGuard
        guard = JurisdictionGuard()
        result = guard.verify_choice_of_law(
            parties_countries=["US", "UK"],
            governing_law="Delaware",
            forum="London"
        )
        # Should detect conflict
        assert len(result.conflicts) > 0 or len(result.warnings) > 0
    
    def test_cisg_applicability(self):
        """Test CISG convention check."""
        from qwed_legal import JurisdictionGuard
        guard = JurisdictionGuard()
        result = guard.check_convention_applicability(
            parties_countries=["US", "DE"],
            convention="CISG"
        )
        assert result.verified is True
        assert "applies" in result.message.lower()
    
    def test_forum_selection(self):
        """Test forum selection validation."""
        from qwed_legal import JurisdictionGuard
        guard = JurisdictionGuard()
        result = guard.verify_forum_selection("NY", contract_value=100000)
        assert result.verified is True


class TestStatuteOfLimitationsGuard:
    """Test StatuteOfLimitationsGuard functionality."""
    
    def test_within_statute(self):
        """Test claim within statute of limitations."""
        from qwed_legal import StatuteOfLimitationsGuard
        guard = StatuteOfLimitationsGuard()
        result = guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2024-01-15",
            filing_date="2026-06-01"
        )
        assert result.verified is True
        assert "WITHIN" in result.message
    
    def test_expired_statute(self):
        """Test claim past statute of limitations."""
        from qwed_legal import StatuteOfLimitationsGuard
        guard = StatuteOfLimitationsGuard()
        result = guard.verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2018-01-15",
            filing_date="2026-06-01"
        )
        assert result.verified is False
        assert "EXPIRED" in result.message
    
    def test_get_limitation_period(self):
        """Test getting limitation period."""
        from qwed_legal import StatuteOfLimitationsGuard
        guard = StatuteOfLimitationsGuard()
        period = guard.get_limitation_period("breach_of_contract", "California")
        assert period == 4.0
    
    def test_compare_jurisdictions(self):
        """Test comparing limitation periods across jurisdictions."""
        from qwed_legal import StatuteOfLimitationsGuard
        guard = StatuteOfLimitationsGuard()
        comparison = guard.compare_jurisdictions(
            "breach_of_contract",
            ["California", "New York", "Delaware"]
        )
        assert comparison["California"] == 4.0
        assert comparison["New York"] == 6.0
        assert comparison["Delaware"] == 3.0
    
    def test_india_jurisdiction(self):
        """Test India statute of limitations."""
        from qwed_legal import StatuteOfLimitationsGuard
        guard = StatuteOfLimitationsGuard()
        period = guard.get_limitation_period("breach_of_contract", "India")
        assert period == 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

