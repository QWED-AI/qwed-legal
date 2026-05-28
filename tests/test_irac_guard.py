"""Tests for IRACGuard fail-closed semantics and verification boundaries."""

from qwed_legal.guards.irac_guard import (
    IRACGuard,
    STATUS_COHERENCE_INVALID,
    STATUS_STRUCTURE_INVALID,
    STATUS_UNVERIFIABLE_REASONING,
)


def test_irac_nonsensical_analysis_fails_closed_or_unverifiable_but_never_verified():
    """Issue #12: nonsense must never be represented as legally verified reasoning."""
    guard = IRACGuard()
    analysis = """
    Issue: Is the sky blue?
    Rule: The sky is always green.
    Application: Applying the green-sky rule, the defendant is liable.
    Conclusion: The defendant is liable.
    """

    result = guard.verify_structure(analysis)

    assert result.status in {STATUS_COHERENCE_INVALID, STATUS_UNVERIFIABLE_REASONING}
    assert result.verified is False
    assert (
        "REASONING UNVERIFIABLE" in result.message
        or "COHERENCE INVALID" in result.message
    )


def test_irac_missing_section_is_structure_invalid():
    """Missing IRAC sections should fail closed as structure invalid."""
    guard = IRACGuard()
    analysis = """
    Issue: Was there a breach?
    Rule: Breach requires duty and violation.
    Conclusion: There was a breach.
    """

    result = guard.verify_structure(analysis)

    assert result.structure_valid is False
    assert result.status == STATUS_STRUCTURE_INVALID
    assert "application" in result.missing_sections


def test_irac_rule_application_disconnect_is_coherence_invalid():
    """Rule/application disconnect should fail closed as coherence invalid."""
    guard = IRACGuard()
    analysis = """
    Issue: Was payment due?
    Rule: Contract payment obligation requires invoice acceptance before maturity date.
    Application: The witness discussed weather conditions and traffic delays only.
    Conclusion: Payment was due.
    """

    result = guard.verify_structure(analysis)

    assert result.structure_valid is False
    assert result.status == STATUS_COHERENCE_INVALID
    assert any("shares no meaningful keywords" in issue for issue in result.coherence_issues)
