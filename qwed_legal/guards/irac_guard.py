import re
from typing import Dict, Any

class IRACGuard:
    """
    Verifies that legal reasoning follows the IRAC framework (Issue, Rule, Application, Conclusion).
    Source: Enforces 'Reasoned Elaboration' standards from MSLR Benchmark.
    """
    def __init__(self):
        # Regex patterns to detect the 4 pillars of legal logic
        self.patterns = {
            "issue": r"(?i)(issue|question presented|legal problem):?\s*(.*)",
            "rule": r"(?i)(rule|law|statute|legal principle):?\s*(.*)",
            "application": r"(?i)(application|analysis|reasoning|applying the law):?\s*(.*)",
            "conclusion": r"(?i)(conclusion|holding|verdict):?\s*(.*)"
        }

    def verify_structure(self, llm_output: str) -> Dict[str, Any]:
        components = {}
        missing_steps = []
        
        # 1. Structural Verification: Does the reasoning path exist?
        for step, pattern in self.patterns.items():
            match = re.search(pattern, llm_output)
            if match:
                components[step] = match.group(2).strip()
            else:
                missing_steps.append(step)
        
        if missing_steps:
            return {
                "verified": False,
                "error": f"Failed Reasoned Elaboration. Missing steps: {', '.join(missing_steps)}. Legal advice must follow IRAC structure.",
                "missing": missing_steps
            }

        # 2. Heuristic Check: Application must reference the Rule
        # MSLR notes that reasoning often fails at the application stage.
        rule_keywords = set(components["rule"].lower().split())
        app_text = components["application"].lower()
        
        # Simple overlap check to ensure Application is actually discussing the Rule
        # Filter short words to reduce noise
        overlap = [w for w in rule_keywords if w in app_text and len(w) > 4]
        
        # If rule is very short, we skip this heuristic to avoid false positives
        if len(rule_keywords) > 3 and len(overlap) < 1:
             return {
                "verified": False,
                "error": "Logical Disconnect: The 'Application' section does not appear to apply the cited 'Rule'.",
                "risk": "Hallucinated Reasoning"
            }

        return {
            "verified": True,
            "components": components,
            "note": "IRAC structure confirmed. Reasoning trace is structurally valid."
        }
