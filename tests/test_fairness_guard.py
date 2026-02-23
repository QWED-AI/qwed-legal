import pytest
from qwed_legal.guards.fairness_guard import FairnessGuard

class MockLLMClient:
    def __init__(self, responses):
        self.responses = responses
        self.call_history = []

    def generate(self, prompt: str) -> str:
        self.call_history.append(prompt)
        # Return the next preset response, or default if not found
        return self.responses.get(prompt, "DENIED")

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
