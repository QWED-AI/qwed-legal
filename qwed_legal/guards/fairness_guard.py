from typing import Dict, Any

class FairnessGuard:
    """
    Evaluates algorithmic fairness using Counterfactual Testing.
    Source: Inspired by the JudiFair benchmark for judicial fairness [Source 337, 338].
    """
    def __init__(self, llm_client=None):
        self.llm_client = llm_client # Used strictly for the counterfactual parallel run

    def verify_decision_fairness(self, original_prompt: str, original_decision: str, protected_attribute_swap: dict) -> Dict[str, Any]:
        """
        Swaps pronouns/names (e.g., "he" -> "she", "John" -> "Jane") and re-runs the prompt.
        Deterministically compares the outcomes.
        """
        import re
        # 1. Generate Counterfactual Prompt
        counterfactual_prompt = original_prompt
        for original, replacement in protected_attribute_swap.items():
            # Use word boundaries to prevent 'the' turning into 'tshe' when swapping 'he'
            pattern = rf"\b{re.escape(original)}\b"
            counterfactual_prompt = re.sub(pattern, replacement, counterfactual_prompt)

        # 2. Get Counterfactual Decision (Parallel Execution)
        if not self.llm_client:
            raise ValueError("LLM client must be provided for counterfactual execution.")
            
        cf_decision = self.llm_client.generate(counterfactual_prompt)

        # 3. Deterministic Equality Check (Strict outcome matching)
        is_consistent = (original_decision == cf_decision)

        if not is_consistent:
            return {
                "verified": False,
                "risk": "JUDICIAL_BIAS_DETECTED",
                "message": "The agent's decision changed when protected attributes were altered. This violates fairness constraints.",
                "variance": {"original": original_decision, "counterfactual": cf_decision}
            }
            
        return {"verified": True, "status": "FAIRNESS_VERIFIED"}
