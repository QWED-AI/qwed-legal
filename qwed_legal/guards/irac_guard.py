"""
IRACGuard: Validate IRAC legal reasoning structure.

IMPORTANT — scope of this guard:
  IRACGuard checks whether a legal analysis text contains the four required
  IRAC components (Issue, Rule, Application, Conclusion) AND performs
  structural coherence checks between them.

  Structural validity is NOT reasoning validity:
  - A text with all four headings may contain logically invalid reasoning.
  - A hallucinated rule or fabricated conclusion still passes structural checks.
  - This guard has no access to legal databases and cannot verify that:
      * the cited rule exists or is correctly stated
      * the application logically follows from the rule
      * the conclusion is legally sound

  Consumers MUST treat IRACGuard results as STRUCTURE_VALID / STRUCTURE_INVALID,
  never as VERIFIED legal reasoning. The status field makes this explicit:

    status="structure_invalid"         — one or more IRAC sections missing
    status="coherence_invalid"         — sections present but structurally incoherent
    status="unverifiable_reasoning"    — structure and coherence pass; reasoning
                                         correctness cannot be proven without
                                         a legal knowledge base

  A status of "unverifiable_reasoning" does NOT mean the legal analysis is
  correct. Reasoning verification requires external legal authority validation.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_AMBIGUITY_NOTED,
    STEP_CONCLUSION,
    EVIDENCE_INFERRED,
    EVIDENCE_UNSUPPORTED,
)

# Status constants
STATUS_STRUCTURE_INVALID = "structure_invalid"
STATUS_COHERENCE_INVALID = "coherence_invalid"
# Always set when structure + coherence pass. Reasoning correctness cannot
# be proven by regex/heuristic means. This is the normal passing state.
STATUS_UNVERIFIABLE_REASONING = "unverifiable_reasoning"


@dataclass
class IRACResult:
    """
    Result of an IRAC structure check.

    Fields:
        structure_valid   - True if all four IRAC sections are present and
                            coherence checks pass. Does NOT mean the reasoning
                            is legally sound.
        status            - one of STATUS_STRUCTURE_INVALID,
                            STATUS_COHERENCE_INVALID, or
                            STATUS_UNVERIFIABLE_REASONING.
        components        - extracted text for each IRAC section.
        missing_sections  - list of IRAC sections not found in the text.
        coherence_issues  - list of structural coherence problems detected.
        message           - human-readable explanation of the result.
    """

    structure_valid: bool
    status: str
    components: Dict[str, str] = field(default_factory=dict)
    missing_sections: List[str] = field(default_factory=list)
    coherence_issues: List[str] = field(default_factory=list)
    message: str = ""
    verification_trace: list = field(default_factory=list)

    @property
    def verified(self) -> bool:
        """
        Always False.

        IRACGuard cannot verify legal reasoning correctness — it has no access
        to legal authority databases. Returning True here would be a false
        claim of reasoning proof. Use structure_valid to check structural
        presence only.
        """
        return False


class IRACGuard:
    """
    Validate that a legal analysis text follows the IRAC framework.

    Scope: STRUCTURAL CHECKING + BASIC COHERENCE ONLY.

    This guard does NOT:
    - Confirm that a cited rule exists in any legal database.
    - Verify that the application logically follows from the rule.
    - Validate that the conclusion is legally sound.
    - Detect hallucinated rules, fabricated cases, or invalid legal logic.

    An IRACResult with structure_valid=True means: the text CONTAINS the four
    required IRAC sections and passes basic coherence checks. It does not mean:
    the legal reasoning is valid.

    Downstream consumers MUST check result.status to distinguish:
      STATUS_UNVERIFIABLE_REASONING  -> structure ok; reasoning unproven
      STATUS_COHERENCE_INVALID       -> sections present but structurally incoherent
      STATUS_STRUCTURE_INVALID       -> one or more sections missing
    """

    _SECTION_PATTERNS: Dict[str, str] = {
        "issue": r"(?im)^\s*(?:\*\*?)?(?:issue|question presented|legal problem)(?:\*\*?)?\s*:?\s*\n?(.*?)(?=(?:\n\s*(?:\*\*?)?(?:rule|law|statute|legal principle|application|analysis|reasoning|applying the law|conclusion|holding|verdict)(?:\*\*?)?\s*:)|\Z)",
        "rule": r"(?im)^\s*(?:\*\*?)?(?:rule|law|statute|legal principle)(?:\*\*?)?\s*:?\s*\n?(.*?)(?=(?:\n\s*(?:\*\*?)?(?:issue|question presented|legal problem|application|analysis|reasoning|applying the law|conclusion|holding|verdict)(?:\*\*?)?\s*:)|\Z)",
        "application": r"(?im)^\s*(?:\*\*?)?(?:application|analysis|reasoning|applying the law)(?:\*\*?)?\s*:?\s*\n?(.*?)(?=(?:\n\s*(?:\*\*?)?(?:issue|question presented|legal problem|rule|law|statute|legal principle|conclusion|holding|verdict)(?:\*\*?)?\s*:)|\Z)",
        "conclusion": r"(?im)^\s*(?:\*\*?)?(?:conclusion|holding|verdict)(?:\*\*?)?\s*:?\s*\n?(.*?)(?=(?:\n\s*(?:\*\*?)?(?:issue|question presented|legal problem|rule|law|statute|legal principle|application|analysis|reasoning|applying the law)(?:\*\*?)?\s*:)|\Z)",
    }

    _MIN_KEYWORD_LEN = 4
    _MIN_RULE_WORDS_FOR_OVERLAP = 4

    def __init__(self) -> None:
        self._compiled = {
            k: re.compile(v, re.DOTALL) for k, v in self._SECTION_PATTERNS.items()
        }

    def verify_structure(self, text: str) -> dict:
        result = self.verify(text)
        return {
            "verified": result.verified,
            "status": result.status,
            "components": result.components,
            "missing": result.missing_sections,
            "error": result.message,
            "coherence_issues": result.coherence_issues,
            "structure_valid": result.structure_valid,
        }

    def verify(self, text: str) -> IRACResult:
        """
        Check whether text contains all four IRAC sections and passes
        basic structural coherence checks.

        Returns IRACResult with:
          structure_valid=True  + status=STATUS_UNVERIFIABLE_REASONING
              when all sections present and coherence checks pass.
              WARNING: does NOT confirm the reasoning is legally valid.

          structure_valid=False + status=STATUS_STRUCTURE_INVALID
              when one or more IRAC sections are missing.

          structure_valid=False + status=STATUS_COHERENCE_INVALID
              when all sections present but structurally incoherent.

        Reasoning correctness is ALWAYS unverifiable. A nonsensical analysis
        like "Rule: The sky is always green" passes if formatted as IRAC.
        """
        components, missing = self._extract_sections(text)

        if missing:
            return IRACResult(
                structure_valid=False,
                status=STATUS_STRUCTURE_INVALID,
                components=components,
                missing_sections=missing,
                message=(
                    f"STRUCTURE INVALID: Missing IRAC section(s): "
                    f"{', '.join(missing)}. Legal analysis must contain "
                    f"Issue, Rule, Application, and Conclusion."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Scanned text for the four IRAC sections.",
                        inputs={"missing_sections": missing},
                        output=f"Missing section(s): {', '.join(missing)}",
                        evidence_type=EVIDENCE_INFERRED,
                    ),
                    VerificationStep(
                        step=STEP_CONCLUSION,
                        description="Required IRAC structure is incomplete.",
                        inputs={"missing_count": len(missing)},
                        output="STRUCTURE INVALID",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                ],
            )

        coherence_issues = self._check_coherence(components)
        if coherence_issues:
            return IRACResult(
                structure_valid=False,
                status=STATUS_COHERENCE_INVALID,
                components=components,
                coherence_issues=coherence_issues,
                message=(
                    f"COHERENCE INVALID: All IRAC sections present but "
                    f"structurally incoherent. "
                    f"Issues: {'; '.join(coherence_issues)}. "
                    f"NOTE: Even coherent structure does not prove the "
                    f"reasoning is legally correct."
                ),
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="All four IRAC sections were located.",
                        inputs={"sections": list(components.keys())},
                        output="All IRAC sections present.",
                        evidence_type=EVIDENCE_INFERRED,
                    ),
                    VerificationStep(
                        step=STEP_AMBIGUITY_NOTED,
                        description="Structural coherence checks failed.",
                        inputs={"coherence_issues": coherence_issues},
                        output="COHERENCE INVALID: structural signals inconsistent.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                ],
            )

        return IRACResult(
            structure_valid=True,
            status=STATUS_UNVERIFIABLE_REASONING,
            components=components,
            message=(
                "STRUCTURE VALID: All four IRAC sections present and "
                "structurally coherent. "
                "REASONING UNVERIFIABLE: IRACGuard cannot confirm the cited "
                "rule exists, the application is logically sound, or the "
                "conclusion is legally correct. Structure check is not proof "
                "of valid legal reasoning."
            ),
            verification_trace=[
                VerificationStep(
                    step=STEP_RULE_IDENTIFIED,
                    description="All four IRAC sections located and coherence checks passed.",
                    inputs={"sections": list(components.keys())},
                    output="Structure present and coherent (heuristic).",
                    evidence_type=EVIDENCE_INFERRED,
                ),
                VerificationStep(
                    step=STEP_CONCLUSION,
                    description="Structure valid, but legal reasoning cannot be proven.",
                    inputs={"reasoning_database_access": False},
                    output=(
                        "REASONING UNVERIFIABLE: structural validity is not proof "
                        "of legally sound reasoning."
                    ),
                    evidence_type=EVIDENCE_UNSUPPORTED,
                ),
            ],
        )

    def _extract_sections(self, text: str) -> Tuple[Dict[str, str], List[str]]:
        """Extract IRAC section content. Returns (components, missing_sections)."""
        components: Dict[str, str] = {}
        missing: List[str] = []
        for section, pattern in self._compiled.items():
            match = pattern.search(text)
            if match:
                components[section] = match.group(1).strip()
            else:
                missing.append(section)
        return components, missing

    def _check_coherence(self, components: Dict[str, str]) -> List[str]:
        """
        Run structural coherence checks on extracted IRAC sections.

        Returns list of coherence issue descriptions (empty = coherent).

        Checks:
          1. Non-empty sections: each section must have substantive content.
          2. Rule-Application keyword overlap: Application must reference at
             least one meaningful keyword from the Rule. Structural signal only
             — does not validate logical soundness.
        """
        issues: List[str] = []

        for section, content in components.items():
            if not content:
                issues.append(f"'{section}' section heading found but has no content.")

        rule_text = components.get("rule", "")
        app_text = components.get("application", "").lower()
        import re as _re

        rule_words = _re.findall(r"\b\w+\b", rule_text.lower())
        rule_keywords = [w for w in rule_words if len(w) >= self._MIN_KEYWORD_LEN]

        if len(rule_keywords) >= self._MIN_RULE_WORDS_FOR_OVERLAP:
            import re as _re

            app_words = set(_re.findall(r"\b\w+\b", app_text))
            overlap = [w for w in rule_keywords if w in app_words]
            if not overlap:
                issues.append(
                    "Application section shares no meaningful keywords with "
                    "the Rule section. The application may be structurally "
                    "disconnected from the stated rule. NOTE: keyword overlap "
                    "is a structural signal only — it does not prove the "
                    "application is logically valid."
                )

        return issues
