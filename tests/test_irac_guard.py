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

    result = guard.verify(analysis)

    assert result.status in {STATUS_COHERENCE_INVALID, STATUS_UNVERIFIABLE_REASONING}
    assert result.verified is False
    assert "REASONING UNVERIFIABLE" in result.message or "COHERENCE INVALID" in result.message


def test_irac_missing_section_is_structure_invalid():
    """Missing IRAC sections should fail closed as structure invalid."""
    guard = IRACGuard()
    analysis = """
    Issue: Was there a breach?
    Rule: Breach requires duty and violation.
    Conclusion: There was a breach.
    """

    result = guard.verify(analysis)

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

    result = guard.verify(analysis)

    assert result.structure_valid is False
    assert result.status == STATUS_COHERENCE_INVALID
    assert any("shares no meaningful keywords" in issue for issue in result.coherence_issues)


def test_irac_multiline_sections():
    """CodeRabbit Major: Multiline sections should not be truncated."""
    guard = IRACGuard()
    analysis = """Issue: Is this multiline?
Yes it is.
Rule: The rule says
many things.
Application: It applies the rule
here.
Conclusion: Therefore,
yes."""
    result = guard.verify(analysis)
    assert result.structure_valid is True
    assert "multiline" in result.components["issue"]
    assert "many things" in result.components["rule"]

def test_irac_whole_word_overlap():
    """CodeRabbit Major: Whole word overlap prevents false positives."""
    guard = IRACGuard()
    # Rule keyword "date" is a substring of Application word "candidate"\n    # but must NOT count as overlap under whole-word matching.
    analysis = """
    Issue: Was the candidate selected?
    Rule: The selection date is critical for the hiring process.
    Application: The candidate appeared confident during review.
    Conclusion: Yes.
    """
    result = guard.verify(analysis)
    assert result.status == STATUS_COHERENCE_INVALID
    
def test_verify_structure_backward_compat():
    """Codex P2: verify_structure should return a dict."""
    guard = IRACGuard()
    analysis = "Issue: a\nRule: b\nApplication: c\nConclusion: d"
    result = guard.verify_structure(analysis)
    assert isinstance(result, dict)
    assert result["verified"] is False
    assert "status" in result
