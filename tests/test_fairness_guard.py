import pytest
from qwed_legal.guards.fairness_guard import (
    FairnessGuard,
    STATUS_UNVERIFIABLE_FAIRNESS,
    STATUS_LLM_GENERATION_FAILED,
    RISK_HEURISTIC_BIAS_SIGNAL,
    RISK_LLM_GENERATION_FAILED,
)
from qwed_legal.models import EVIDENCE_DETERMINISTIC


class MockLLMClient:
    def __init__(self, responses):
        self.responses = responses
        self.call_history = []

    def generate(self, prompt: str) -> str:
        self.call_history.append(prompt)
        if prompt not in self.responses:
            raise KeyError(f"MockLLMClient received unexpected prompt: {prompt!r}")
        return self.responses[prompt]


def test_fairness_guard_consistent_is_never_verified():
    # Fail-closed: consistent outcome is NOT proof of fairness (issue #18).
    llm = MockLLMClient({
        "Should we approve the loan for John?": "APPROVED",
        "Should we approve the loan for Jane?": "APPROVED"
    })

    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "his": "her"}

    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)

    assert result["verified"] is False
    assert result["status"] == STATUS_UNVERIFIABLE_FAIRNESS
    assert llm.call_history == ["Should we approve the loan for Jane?"]
    # No trace step may claim deterministic proof of fairness.
    assert all(
        s.evidence_type != EVIDENCE_DETERMINISTIC
        for s in result["verification_trace"]
    )


def test_fairness_guard_inconsistent_bias_signal():
    llm = MockLLMClient({
        "Should we approve the loan for John?": "APPROVED",
        "Should we approve the loan for Jane?": "DENIED"  # Bias signal!
    })

    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "his": "her"}

    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)

    assert result["verified"] is False
    assert result["risk"] == RISK_HEURISTIC_BIAS_SIGNAL
    assert "variance" in result
    assert result["variance"]["original"] == "APPROVED"
    assert result["variance"]["counterfactual"] == "DENIED"


def test_fairness_guard_requires_llm_client():
    guard = FairnessGuard(llm_client=None)
    with pytest.raises(ValueError, match="LLM client must be provided"):
        guard.verify_decision_fairness("prompt", "decision", {"a": "b"})


def test_fairness_guard_empty_swap_fails_closed():
    llm = MockLLMClient({})
    guard = FairnessGuard(llm_client=llm)
    result = guard.verify_decision_fairness("prompt", "decision", {})
    assert result["verified"] is False
    assert result["status"] == STATUS_UNVERIFIABLE_FAIRNESS


def test_fairness_guard_rejects_non_string_swap_value():
    llm = MockLLMClient({})
    guard = FairnessGuard(llm_client=llm)
    with pytest.raises(ValueError, match="must be strings"):
        guard.verify_decision_fairness("prompt", "decision", {"John": None})


def test_fairness_guard_rejects_case_colliding_keys():
    llm = MockLLMClient({})
    guard = FairnessGuard(llm_client=llm)
    with pytest.raises(ValueError, match="collide when"):
        guard.verify_decision_fairness("prompt", "decision", {"he": "she", "He": "him"})


def test_fairness_guard_preserves_case_and_matches_insensitively():
    llm = MockLLMClient({
        "Should we approve the loan for Jane? She is a good candidate. Give it to HER.": "APPROVED"
    })

    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John? He is a good candidate. Give it to HIM."
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "him": "her"}

    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)

    # Still fail-closed even though outcomes were consistent.
    assert result["verified"] is False
    assert llm.call_history == ["Should we approve the loan for Jane? She is a good candidate. Give it to HER."]


def test_fairness_guard_bidirectional_swap_does_not_revert():
    """Bidirectional swap {"he": "she", "she": "he"} must not cancel itself out."""
    original_prompt = "she applied for the loan, but he did not"

    # Expected counterfactual: "he applied for the loan, but she did not"
    llm = MockLLMClient({
        "he applied for the loan, but she did not": "APPROVED",
    })

    guard = FairnessGuard(llm_client=llm)
    result = guard.verify_decision_fairness(
        original_prompt,
        original_decision="APPROVED",
        protected_attribute_swap={"he": "she", "she": "he"},
    )

    assert result["verified"] is False
    assert llm.call_history == ["he applied for the loan, but she did not"]


def test_fairness_guard_handles_none_from_llm():
    llm = MockLLMClient({
        "Should we approve the loan for Jane?": None
    })

    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane"}

    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)

    assert result["verified"] is False
    assert result["risk"] == RISK_LLM_GENERATION_FAILED
    assert result["status"] == STATUS_LLM_GENERATION_FAILED
