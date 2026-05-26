"""
CitationGuard: Validate legal citation format.

IMPORTANT — scope of this guard:
  CitationGuard checks whether a citation STRING matches a known reporter
  pattern (e.g., U.S., F.3d, UKSC). This is FORMAT validation only.

  Format validity is NOT authority validity:
  - A well-formatted citation may refer to a case that does not exist.
  - A hallucinated citation with a plausible reporter still passes format checks.
  - This guard has no access to case law databases, and cannot confirm that the
    cited authority exists, is correctly identified, or applies to the claim made.

  Consumers MUST treat CitationGuard results as FORMAT_VALID / FORMAT_INVALID,
  never as VERIFIED legal authority. The status field makes this explicit:
    status="format_valid"            — matches a known reporter pattern
    status="format_invalid"          — does not match any pattern
    status="unverifiable_authority"  — format is valid but authority is unconfirmed

  A status of "format_valid" or "unverifiable_authority" does NOT mean the
  cited case exists. Authority verification requires an external legal database.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Status constants — use these instead of comparing strings directly
STATUS_FORMAT_VALID = "format_valid"
STATUS_FORMAT_INVALID = "format_invalid"
# Returned alongside format_valid when authority cannot be confirmed.
# This is ALWAYS set when a format match is found — CitationGuard cannot
# check case databases, so authority is always unverifiable.
STATUS_UNVERIFIABLE_AUTHORITY = "unverifiable_authority"


@dataclass
class CitationResult:
    """
    Result of a citation format check.

    Fields:
        format_valid    — True if citation matches a known reporter pattern.
                          Does NOT mean the cited case exists.
        status          — one of STATUS_FORMAT_VALID, STATUS_FORMAT_INVALID,
                          or STATUS_UNVERIFIABLE_AUTHORITY.
        citation_type   — reporter category matched (e.g., "US_SCOTUS"), or None.
        parsed_components — regex-extracted fields (volume, reporter, page, etc.)
        issues          — list of format problems found (empty when format_valid=True)
        message         — human-readable explanation of the result
        risk            — optional risk level string
    """

    format_valid: bool
    status: str
    citation_type: Optional[str] = None
    parsed_components: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    message: str = ""
    risk: Optional[str] = None

    # ── Backward-compatibility properties ─────────────────────────────────────
    @property
    def valid(self) -> bool:
        """Alias for format_valid. Use format_valid in new code."""
        return self.format_valid

    @property
    def verified(self) -> bool:
        """
        Always False.

        CitationGuard cannot verify legal authority — it has no access to case
        law databases. Returning True here would be a false claim of authority
        proof. Use format_valid to check citation format only.
        """
        return False


@dataclass
class BatchCitationResult:
    """Result of a batch citation format check."""

    total: int
    format_valid: int
    format_invalid: int

    # Backward-compat aliases
    @property
    def valid(self) -> int:
        return self.format_valid

    @property
    def invalid(self) -> int:
        return self.format_invalid


class CitationGuard:
    """
    Validate legal citation format against known reporter patterns.

    Scope: FORMAT CHECKING ONLY.

    This guard does NOT:
    - Confirm a cited case exists in any database.
    - Validate that a case name is real or correctly identified.
    - Verify that a cited authority supports the proposition claimed.
    - Detect hallucinated citations that use plausible reporter formats.

    A CitationResult with format_valid=True means: "the citation STRING looks
    like a real citation." It does not mean: "this legal authority exists."

    Downstream consumers MUST check result.status to distinguish:
      STATUS_FORMAT_VALID / STATUS_UNVERIFIABLE_AUTHORITY  → format ok, authority unknown
      STATUS_FORMAT_INVALID                                 → format is malformed
    """

    # Known case citation reporter patterns
    CASE_PATTERNS: Dict[str, str] = {
        "US_SCOTUS": r"(?P<volume>\d{1,4})\s+(?P<reporter>U\.?S\.?)\s+(?P<page>\d{1,4})",
        "US_FED": r"(?P<volume>\d{1,4})\s+(?P<reporter>F\.(?:2d|3d)?)\s+(?P<page>\d{1,4})",
        "UK_NEUTRAL": r"\[(?P<year>\d{4})\]\s+(?P<court>UKSC|EWCA\s+Civ|EWHC)\s+(?P<number>\d+)",
        "INDIA_AIR": r"AIR\s+(?P<year>\d{4})\s+(?P<court>SC|Bom|Del)\s+(?P<page>\d+)",
    }

    # Known statute citation patterns
    STATUTE_PATTERNS: Dict[str, str] = {
        "US_CODE": r"(?P<title>\d{1,3})\s+U\.?S\.?C\.?\s+§+\s*(?P<section>[\d\w]+)",
    }

    # Regex for a case name prefix: "Something v. Something"
    _CASE_NAME_RE = re.compile(r"^([A-Z][a-zA-Z\s\.]+)\sv\.\s([A-Z][a-zA-Z\s\.,]+)")

    def __init__(self) -> None:
        # Compile patterns once
        self._compiled_case = {k: re.compile(v) for k, v in self.CASE_PATTERNS.items()}
        self._compiled_statute = {
            k: re.compile(v) for k, v in self.STATUTE_PATTERNS.items()
        }

    # ── Public API ─────────────────────────────────────────────────────────────

    def verify(self, text: str) -> CitationResult:
        """
        Check whether `text` matches a known legal citation format.

        Returns CitationResult with:
          format_valid=True  + status=STATUS_UNVERIFIABLE_AUTHORITY
              when a reporter pattern matches.
              WARNING: this does NOT confirm the cited case exists.

          format_valid=False + status=STATUS_FORMAT_INVALID
              when no pattern matches or required elements are missing.

        Authority is ALWAYS unverifiable — CitationGuard has no database access.
        """
        is_statute = "U.S.C." in text or "§" in text
        has_case_name = bool(self._CASE_NAME_RE.search(text))

        if not has_case_name and not is_statute:
            if re.search(r"\d+\s+[A-Za-z\.]+\s+\d+", text):
                return CitationResult(
                    format_valid=False,
                    status=STATUS_FORMAT_INVALID,
                    issues=["Missing case name"],
                    message=(
                        "FORMAT INVALID: Citation is missing a case name "
                        "(expected 'Party v. Party, ...' format)."
                    ),
                )

        # Try each case reporter pattern
        for citation_type, pattern in self._compiled_case.items():
            match = pattern.search(text)
            if match:
                components = self._parse_components(match.groupdict())
                return CitationResult(
                    format_valid=True,
                    status=STATUS_UNVERIFIABLE_AUTHORITY,
                    citation_type=citation_type,
                    parsed_components=components,
                    message=(
                        f"FORMAT VALID ({citation_type}): Citation matches the "
                        f"{citation_type} reporter pattern. "
                        f"AUTHORITY UNVERIFIABLE: CitationGuard cannot confirm "
                        f"this case exists or is correctly identified. "
                        f"Format match is not proof of legal authority."
                    ),
                )

        # Unknown/invalid reporter pattern
        if re.search(r"\d+\s+[A-Z\.]+\s+\d+", text):
            return CitationResult(
                format_valid=False,
                status=STATUS_FORMAT_INVALID,
                issues=["Unknown reporter"],
                message=(
                    "FORMAT INVALID: Citation contains an unrecognized reporter "
                    "abbreviation. Supported reporters: "
                    f"{', '.join(self.CASE_PATTERNS.keys())}."
                ),
            )

        return CitationResult(
            format_valid=False,
            status=STATUS_FORMAT_INVALID,
            issues=["No valid citation found"],
            message="FORMAT INVALID: No recognizable citation pattern found in the text.",
        )

    def verify_citation_format(self, text: str) -> Dict[str, Any]:
        """
        Explicit format-check API. Returns a dict describing format validity only.

        Prefer verify() for structured results. This method is provided for
        backward compatibility and for callers who explicitly want format info.
        """
        result = self.verify(text)
        return {
            "format_valid": result.format_valid,
            "status": result.status,
            "citation_type": result.citation_type,
            "issues": result.issues,
            "message": result.message,
            # Explicit note — not a property alias, an intentional field
            "authority_verified": False,
            "authority_note": (
                "CitationGuard performs format validation only. "
                "Authority verification requires an external legal database."
            ),
        }

    def check_statute_citation(self, text: str) -> CitationResult:
        """
        Check whether `text` matches a known statute citation format (e.g., 42 U.S.C. § 1983).

        Same scope as verify(): FORMAT ONLY. Does not confirm the statute section exists
        or has the legal meaning attributed to it.
        """
        for citation_type, pattern in self._compiled_statute.items():
            match = pattern.search(text)
            if match:
                components = self._parse_components(match.groupdict())
                return CitationResult(
                    format_valid=True,
                    status=STATUS_UNVERIFIABLE_AUTHORITY,
                    citation_type=citation_type,
                    parsed_components=components,
                    message=(
                        f"FORMAT VALID ({citation_type}): Statute citation matches "
                        f"the {citation_type} pattern. "
                        f"AUTHORITY UNVERIFIABLE: CitationGuard cannot confirm "
                        f"this statute section exists or applies as cited."
                    ),
                )

        return CitationResult(
            format_valid=False,
            status=STATUS_FORMAT_INVALID,
            issues=["Invalid statute format"],
            message=(
                "FORMAT INVALID: No recognized statute citation pattern found. "
                f"Supported patterns: {', '.join(self.STATUTE_PATTERNS.keys())}."
            ),
        )

    def verify_batch(self, citations: List[str]) -> BatchCitationResult:
        """
        Check a list of citation strings for format validity.

        Returns counts of format_valid and format_invalid. Note that format_valid
        citations are NOT verified legal authorities — see verify() for details.
        """
        valid_count = sum(1 for c in citations if self.verify(c).format_valid)
        invalid_count = len(citations) - valid_count
        return BatchCitationResult(
            total=len(citations),
            format_valid=valid_count,
            format_invalid=invalid_count,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_components(groupdict: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce numeric fields (volume, title, page, number) to int where possible."""
        result = {}
        for key, value in groupdict.items():
            if value is not None and key in {"volume", "title", "page", "number"}:
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value
            else:
                result[key] = value
        return result
