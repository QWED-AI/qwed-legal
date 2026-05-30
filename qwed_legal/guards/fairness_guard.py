"""
FairnessGuard: heuristic counterfactual fairness checks.

IMPORTANT — scope of this guard (see issue #18):
  FairnessGuard performs a single counterfactual swap and a deterministic
  string comparison of decisions. This is a HEURISTIC signal, not a legal
  fairness proof.

  Fail-closed contract:
  - This guard can NEVER return verified=True. Legal fairness cannot be proven
    by text substitution + string equality.
  - A consistent outcome is reported as UNVERIFIABLE_FAIRNESS (heuristic only):
    it does not prove the absence of bias.
  - A differing outcome is reported as a HEURISTIC bias *signal* that warrants
    human review — not a deterministic proof of bias either, but it is a
    fail-closed (verified=False) result.
  - Incomplete fairness inputs (missing client, empty swap, None generation)
    fail closed; they are never treated as safe.
"""

import re
from typing import Dict, Any

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_CONCLUSION,
    EVIDENCE_HEURISTIC,
    EVIDENCE_UNSUPPORTED,
)

# Status constants
STATUS_NO_SWAP_REQUIRED = "NO_SWAP_REQUIRED"
STATUS_UNVERIFIABLE_FAIRNESS = "UNVERIFIABLE_FAIRNESS"
STATUS_LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"

# Risk constants
RISK_HEURISTIC_BIAS_SIGNAL = "HEURISTIC_BIAS_SIGNAL"
RISK_LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"


class FairnessGuard:
    """
    Evaluates algorithmic fairness using counterfactual testing.

    This is a HEURISTIC guard. It can never prove fairness, so it never
    returns verified=True. See issue #18.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client  # Used for synchronous counterfactual generation

    def verify_decision_fairness(
        self,
        original_prompt: str,
        original_decision: str,
        protected_attribute_swap: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Swap protected attributes (e.g., "he" -> "she", "John" -> "Jane"),
        re-run the prompt, and heuristically compare the outcomes.

        Fail-closed: this method never returns verified=True. A consistent
        outcome is UNVERIFIABLE_FAIRNESS (heuristic), not proof of fairness.
        """
        if not self.llm_client:
            raise ValueError("LLM client must be provided for counterfactual execution.")

        if not protected_attribute_swap:
            # No protected attributes to swap — fairness cannot be assessed.
            # Fail-closed: this is not a verified-safe result.
            return {
                "verified": False,
                "status": STATUS_UNVERIFIABLE_FAIRNESS,
                "message": (
                    "UNVERIFIABLE_FAIRNESS: No protected attributes provided to "
                    "swap. Fairness cannot be assessed from incomplete input."
                ),
                "verification_trace": [
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="No protected attributes supplied for counterfactual swap.",
                        inputs={"protected_attribute_swap": protected_attribute_swap},
                        output="UNSUPPORTED: incomplete fairness input.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            }

        # 1. Generate counterfactual prompt (single-pass to avoid cascade re-substitution)
        combined_pattern = (
            r"\b(" + "|".join(re.escape(k) for k in protected_attribute_swap) + r")\b"
        )
        lower_swap_dict = {k.lower(): v for k, v in protected_attribute_swap.items()}

        def match_case(match):
            word = match.group()
            rep = lower_swap_dict[word.lower()].lower()
            if word.isupper():
                return rep.upper()
            elif word.istitle():
                return rep.capitalize()
            return rep

        counterfactual_prompt = re.sub(
            combined_pattern, match_case, original_prompt, flags=re.IGNORECASE
        )

        # 2. Get counterfactual decision (sequential/synchronous)
        cf_decision = self.llm_client.generate(counterfactual_prompt)

        if cf_decision is None:
            return {
                "verified": False,
                "risk": RISK_LLM_GENERATION_FAILED,
                "status": STATUS_LLM_GENERATION_FAILED,
                "message": "The LLM client returned None for the counterfactual prompt.",
                "verification_trace": [
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Generated counterfactual prompt via attribute swap.",
                        inputs={"protected_attribute_swap": protected_attribute_swap},
                        output="Counterfactual prompt generated.",
                        evidence_type=EVIDENCE_HEURISTIC,
                    ),
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="LLM returned no counterfactual decision.",
                        inputs={"counterfactual_decision": None},
                        output="UNSUPPORTED: counterfactual generation failed.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                ],
            }

        # 3. Heuristic equality check (strict outcome matching)
        is_consistent = (
            original_decision.strip().lower() == cf_decision.strip().lower()
        )

        trace = [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Generated counterfactual prompt via protected-attribute swap.",
                inputs={"protected_attribute_swap": protected_attribute_swap},
                output="Counterfactual prompt generated (heuristic substitution).",
                evidence_type=EVIDENCE_HEURISTIC,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Compared original and counterfactual decisions by string equality.",
                inputs={
                    "original_decision": original_decision,
                    "counterfactual_decision": cf_decision,
                },
                output=f"Outcomes {'match' if is_consistent else 'differ'} (string compare).",
                evidence_type=EVIDENCE_HEURISTIC,
            ),
        ]

        if not is_consistent:
            trace.append(
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Outcomes differed under counterfactual swap (heuristic signal).",
                    inputs={
                        "original": original_decision,
                        "counterfactual": cf_decision,
                    },
                    output=(
                        "HEURISTIC BIAS SIGNAL: outcome changed under swap — "
                        "requires human review (not a deterministic proof)."
                    ),
                    evidence_type=EVIDENCE_HEURISTIC,
                )
            )
            return {
                "verified": False,
                "risk": RISK_HEURISTIC_BIAS_SIGNAL,
                "status": STATUS_UNVERIFIABLE_FAIRNESS,
                "message": (
                    "HEURISTIC_BIAS_SIGNAL: The decision changed when protected "
                    "attributes were altered. This is a heuristic signal that "
                    "warrants human review; it is not a deterministic proof of "
                    "bias, and fairness cannot be verified by this guard."
                ),
                "variance": {
                    "original": original_decision,
                    "counterfactual": cf_decision,
                },
                "verification_trace": trace,
            }

        # Consistent outcome — fail-closed: NOT proof of fairness.
        trace.append(
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Outcomes matched under a single counterfactual swap.",
                inputs={"single_swap": True},
                output=(
                    "UNVERIFIABLE_FAIRNESS: consistent outcome under one swap is "
                    "not proof of fairness."
                ),
                evidence_type=EVIDENCE_UNSUPPORTED,
            )
        )
        return {
            "verified": False,
            "status": STATUS_UNVERIFIABLE_FAIRNESS,
            "message": (
                "UNVERIFIABLE_FAIRNESS: Outcomes were consistent under a single "
                "counterfactual swap, but legal fairness cannot be proven by "
                "heuristic text substitution and string equality. A single swap "
                "does not prove fairness across relevant dimensions."
            ),
            "consistent": True,
            "verification_trace": trace,
        }
