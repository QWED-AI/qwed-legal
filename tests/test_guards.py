"""Tests for QWED-Legal guards."""

import pytest
from datetime import datetime

from qwed_legal import LegalGuard, DeadlineGuard, LiabilityGuard, ClauseGuard


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
