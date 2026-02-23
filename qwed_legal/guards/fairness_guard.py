import re
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
        if not self.llm_client:
            raise ValueError("LLM client must be provided for counterfactual execution.")

        # 1. Generate Counterfactual Prompt (single-pass to avoid cascade re-substitution)
        combined_pattern = r'\b(' + '|'.join(re.escape(k) for k in protected_attribute_swap) + r')\b'
        lower_swap_dict = {k.lower(): v for k, v in protected_attribute_swap.items()}
        
        def match_case(match):
            word = match.group()
            rep = lower_swap_dict[word.lower()]
            if word.isupper():
                return rep.upper()
            elif word.istitle():
                return rep.capitalize()
            return rep
            
        counterfactual_prompt = re.sub(combined_pattern, match_case, original_prompt, flags=re.IGNORECASE)

        # 2. Get Counterfactual Decision (sequential/synchronous)
        cf_decision = self.llm_client.generate(counterfactual_prompt)

        # 3. Deterministic Equality Check (Strict outcome matching)
        is_consistent = (original_decision.strip().lower() == cf_decision.strip().lower())

        if not is_consistent:
            return {
                "verified": False,
                "risk": "JUDICIAL_BIAS_DETECTED",
                "message": "The agent's decision changed when protected attributes were altered. This violates fairness constraints.",
                "variance": {"original": original_decision, "counterfactual": cf_decision}
            }
            
        return {"verified": True, "status": "FAIRNESS_VERIFIED"}
