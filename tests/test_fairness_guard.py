import pytest
from qwed_legal.guards.fairness_guard import FairnessGuard

class MockLLMClient:
    def __init__(self, responses):
        self.responses = responses
        self.call_history = []

    def generate(self, prompt: str) -> str:
        self.call_history.append(prompt)
        if prompt not in self.responses:
            raise KeyError(f"MockLLMClient received unexpected prompt: {prompt!r}")
        return self.responses[prompt]

def test_fairness_guard_consistent():
    # Setup mock LLM that returns the same decision regardless of prompt
    llm = MockLLMClient({
        "Should we approve the loan for John?": "APPROVED",
        "Should we approve the loan for Jane?": "APPROVED"
    })
    
    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "his": "her"}
    
    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)
    
    assert result["verified"] is True
    assert result["status"] == "FAIRNESS_VERIFIED"
    assert llm.call_history == ["Should we approve the loan for Jane?"]

def test_fairness_guard_inconsistent_bias_detected():
    # Setup mock LLM that returns a DIFFERENT decision for the counterfactual
    llm = MockLLMClient({
        "Should we approve the loan for John?": "APPROVED",
        "Should we approve the loan for Jane?": "DENIED" # Bias detected!
    })
    
    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "his": "her"}
    
    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)
    
    assert result["verified"] is False
    assert result["risk"] == "JUDICIAL_BIAS_DETECTED"
    assert "variance" in result
    assert result["variance"]["original"] == "APPROVED"
    assert result["variance"]["counterfactual"] == "DENIED"

def test_fairness_guard_requires_llm_client():
    guard = FairnessGuard(llm_client=None)
    with pytest.raises(ValueError, match="LLM client must be provided"):
        guard.verify_decision_fairness("prompt", "decision", {"a": "b"})

def test_fairness_guard_preserves_case_and_matches_insensitively():
    llm = MockLLMClient({
        "Should we approve the loan for Jane? She is a good candidate. Give it to HER.": "APPROVED"
    })
    
    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John? He is a good candidate. Give it to HIM."
    original_decision = "APPROVED"
    swaps = {"John": "Jane", "he": "she", "him": "her"}
    
    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)
    
    assert result["verified"] is True
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
    
    assert result["verified"] is True
    assert llm.call_history == ["he applied for the loan, but she did not"]

def test_fairness_guard_handles_none_from_llm():
    # Setup mock LLM that returns None
    llm = MockLLMClient({
        "Should we approve the loan for Jane?": None
    })
    
    guard = FairnessGuard(llm_client=llm)
    original_prompt = "Should we approve the loan for John?"
    original_decision = "APPROVED"
    swaps = {"John": "Jane"}
    
    result = guard.verify_decision_fairness(original_prompt, original_decision, swaps)
    
    assert result["verified"] is False
    assert result["risk"] == "LLM_GENERATION_FAILED"
