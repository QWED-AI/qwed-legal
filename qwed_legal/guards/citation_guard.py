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
    status="format_invalid"          — does not match any known reporter pattern
    status="unverifiable_authority"  — matches a pattern; authority unconfirmed
                                       (this is the normal result for valid-format
                                       citations — format ≠ authority)

  A status of "unverifiable_authority" does NOT mean the cited case exists.
  Authority verification requires an external legal database.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_CONCLUSION,
    EVIDENCE_PARSED,
    EVIDENCE_UNSUPPORTED,
)


# Status constants — use these instead of comparing strings directly
#
# Possible values returned by verify() and check_statute_citation():
#   STATUS_FORMAT_INVALID          — citation does not match any known pattern
#   STATUS_UNVERIFIABLE_AUTHORITY  — citation matches a pattern but authority
#                                   cannot be confirmed (no database access)
#
# Note: there is intentionally NO "format_valid" status. When a citation matches
# a reporter pattern, status is ALWAYS "unverifiable_authority" — because format
# validity does not imply authority validity and must not be confused with it.
STATUS_FORMAT_INVALID = "format_invalid"
STATUS_UNVERIFIABLE_AUTHORITY = "unverifiable_authority"

# Pattern that matches " v. " — the defining element of a party-vs-party case name.
# Used positionally: we require this marker to appear BEFORE the reporter match start,
# not just anywhere in the string.
_V_DOT_RE = re.compile(r"\sv\.\s", re.IGNORECASE)


@dataclass
class CitationResult:
    """
    Result of a citation format check.

    Fields:
        format_valid    — True if citation matches a known reporter pattern.
                          Does NOT mean the cited case exists.
        status          — one of STATUS_FORMAT_INVALID or STATUS_UNVERIFIABLE_AUTHORITY.
                          Note: STATUS_FORMAT_VALID is never returned — when a citation
                          matches a pattern, status is always STATUS_UNVERIFIABLE_AUTHORITY
                          because format validity does not imply authority validity.
        citation        — the original citation text passed to verify(). Included
                          so callers and the TypeScript SDK can echo it back.
        citation_type   — reporter category matched (e.g., "US_SCOTUS"), or None.
        parsed_components — regex-extracted fields (volume, reporter, page, etc.
                          Numeric fields are coerced to int where possible.)
        issues          — list of format problems found (empty when format_valid=True)
        message         — human-readable explanation of the result
        risk            — optional risk level string
    """

    format_valid: bool
    status: str
    citation: str = ""  # original input text — for SDK / caller echo-back
    citation_type: Optional[str] = None
    parsed_components: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    message: str = ""
    risk: Optional[str] = None
    verification_trace: list = field(default_factory=list)

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
      STATUS_UNVERIFIABLE_AUTHORITY  → format ok, authority unknown (normal passing state)
      STATUS_FORMAT_INVALID          → citation is malformed
    """

    # Known case citation reporter patterns.
    # Patterns for case reporters (US_SCOTUS, US_FED) require a case name to
    # appear BEFORE the reporter group. Neutral citation patterns (UK_NEUTRAL)
    # do not mandate a party-name prefix.
    CASE_PATTERNS: Dict[str, str] = {
        # U.S. Supreme Court: "Brown v. Board, 347 U.S. 483"
        # Case name enforced by requiring .+ v. . prefix before the volume/reporter
        "US_SCOTUS": (
            r"(?i)(?:.+\sv\.\s\S.+?\s)?"
            r"(?P<volume>\d{1,4})\s+(?P<reporter>U\.?S\.?)\s+(?P<page>\d{1,4})"
        ),
        # Federal Reporter: "Smith v. Jones, 123 F.3d 456"
        "US_FED": (
            r"(?i)(?:.+\sv\.\s\S.+?\s)?"
            r"(?P<volume>\d{1,4})\s+(?P<reporter>F\.(?:2d|3d)?)\s+(?P<page>\d{1,4})"
        ),
        # UK Neutral: "[2020] UKSC 5" — no party names required
        "UK_NEUTRAL": (
            r"\[(?P<year>\d{4})\]\s+(?P<court>UKSC|EWCA\s+Civ|EWHC)\s+(?P<number>\d+)"
        ),
        # India AIR: "AIR 2001 SC 3021" — no party names required
        "INDIA_AIR": (r"AIR\s+(?P<year>\d{4})\s+(?P<court>SC|Bom|Del)\s+(?P<page>\d+)"),
    }

    # Case reporter types that require a "Party v. Party" prefix to be format-valid.
    # Neutral citation types (UK_NEUTRAL, INDIA_AIR) do not require party names.
    _REQUIRES_CASE_NAME = frozenset({"US_SCOTUS", "US_FED"})

    # Known statute citation patterns
    STATUTE_PATTERNS: Dict[str, str] = {
        "US_CODE": r"(?P<title>\d{1,3})\s+U\.?S\.?C\.?\s+§+\s*(?P<section>[\d\w]+)",
    }

    def __init__(self) -> None:
        # Compile patterns once at init time (not dynamically at runtime)
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
              when a reporter pattern matches (and case-name is present if required).
              WARNING: this does NOT confirm the cited case exists.

          format_valid=False + status=STATUS_FORMAT_INVALID
              when no pattern matches or required elements are missing.

        Authority is ALWAYS unverifiable — CitationGuard has no database access.
        """
        is_statute = "U.S.C." in text or "§" in text

        # Try each case reporter pattern.
        # Case-name enforcement is per-pattern: US_SCOTUS and US_FED require a
        # "Party v. Party" prefix; UK_NEUTRAL and INDIA_AIR do not.
        # We track whether any pattern matched but was skipped due to missing
        # case name — used to surface the right error message if no pattern succeeds.
        skipped_for_case_name = False
        for citation_type, pattern in self._compiled_case.items():
            match = pattern.search(text)
            if not match:
                continue

            # For reporter types that mandate a case name, verify one is present
            # AND that it appears BEFORE the reporter in the string.
            # Positional check prevents "347 U.S. 483 Smith v. Jones" from passing
            # (case name after reporter is not a valid citation prefix).
            # Use continue (not return): a later pattern may match without case name.
            if citation_type in self._REQUIRES_CASE_NAME:
                v_dot = _V_DOT_RE.search(text)
                # "v." must exist AND appear before the volume number.
                # Use match.start("volume") — the volume group is always the first
                # numeric capture and is the true start of the reporter section.
                # match.start() alone would be 0 because the pattern has an optional
                # case-name prefix group, making match.start() unreliable here.
                volume_start = (
                    match.start("volume")
                    if "volume" in match.groupdict()
                    else match.start()
                )
                if not v_dot or v_dot.start() >= volume_start:
                    # No "v." found, or "v." at/after reporter — case name not a prefix
                    skipped_for_case_name = True
                    continue

            components = self._parse_components(match.groupdict())
            return CitationResult(
                format_valid=True,
                status=STATUS_UNVERIFIABLE_AUTHORITY,
                citation=text,
                citation_type=citation_type,
                parsed_components=components,
                message=(
                    f"FORMAT VALID ({citation_type}): Citation matches the "
                    f"{citation_type} reporter pattern. "
                    f"AUTHORITY UNVERIFIABLE: CitationGuard cannot confirm "
                    f"this case exists or is correctly identified. "
                    f"Format match is not proof of legal authority."
                ),
                verification_trace=self._format_match_trace(citation_type, text),
            )

        # Statute check (done after case patterns to avoid dual-matching)
        # Important: run this before returning a deferred "Missing case name"
        # error. Mixed text can contain a bare case reporter fragment (e.g.
        # "347 U.S. 483") and a valid statute citation. A missing case-name
        # fragment should not prevent a later valid statute format from being
        # detected. The result remains FORMAT ONLY / AUTHORITY UNVERIFIABLE.
        if is_statute:
            # Let check_statute_citation handle it for a structured result
            return self.check_statute_citation(text)

        # If a reporter pattern matched but was skipped due to missing case name,
        # and no other pattern succeeded, surface "Missing case name" specifically.
        if skipped_for_case_name:
            return CitationResult(
                format_valid=False,
                status=STATUS_FORMAT_INVALID,
                citation=text,
                issues=["Missing case name"],
                message=(
                    "FORMAT INVALID: Citation is missing a case name "
                    "(expected 'Party v. Party, ...' format for this reporter)."
                ),
                verification_trace=self._format_invalid_trace(text, "Missing case name"),
            )

        # Unknown/invalid reporter pattern
        if re.search(r"\d+\s+[A-Z\.]+\s+\d+", text):
            return CitationResult(
                format_valid=False,
                status=STATUS_FORMAT_INVALID,
                citation=text,
                issues=["Unknown reporter"],
                message=(
                    "FORMAT INVALID: Citation contains an unrecognized reporter "
                    "abbreviation. Supported reporters: "
                    f"{', '.join(self.CASE_PATTERNS.keys())}."
                ),
                verification_trace=self._format_invalid_trace(text, "Unknown reporter"),
            )

        return CitationResult(
            format_valid=False,
            status=STATUS_FORMAT_INVALID,
            citation=text,
            issues=["No valid citation found"],
            message="FORMAT INVALID: No recognizable citation pattern found in the text.",
            verification_trace=self._format_invalid_trace(text, "No valid citation found"),
        )

    def verify_citation_format(self, text: str) -> Dict[str, Any]:
        """
        Explicit format-check API. Returns a dict describing format validity only.

        Backward-compat note:
          - 'verified' key is retained as a deprecated alias for format_valid.
            It reflects whether the citation FORMAT is valid, NOT whether the
            legal authority exists. New code should use 'format_valid' instead.
          - 'authority_verified' is always False (canonical field for auth check).
        """
        result = self.verify(text)
        return {
            "format_valid": result.format_valid,
            # Deprecated alias — equals format_valid, not authority verification.
            # Kept for backward compatibility. Use 'format_valid' in new code.
            "verified": result.format_valid,
            "status": result.status,
            "citation_type": result.citation_type,
            "citation": result.citation,
            "issues": result.issues,
            "message": result.message,
            # Explicit authority fields — these are the canonical source of truth
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
                    citation=text,
                    citation_type=citation_type,
                    parsed_components=components,
                    message=(
                        f"FORMAT VALID ({citation_type}): Statute citation matches "
                        f"the {citation_type} pattern. "
                        f"AUTHORITY UNVERIFIABLE: CitationGuard cannot confirm "
                        f"this statute section exists or applies as cited."
                    ),
                    verification_trace=self._format_match_trace(citation_type, text),
                )

        return CitationResult(
            format_valid=False,
            status=STATUS_FORMAT_INVALID,
            citation=text,
            issues=["Invalid statute format"],
            message=(
                "FORMAT INVALID: No recognized statute citation pattern found. "
                f"Supported patterns: {', '.join(self.STATUTE_PATTERNS.keys())}."
            ),
            verification_trace=self._format_invalid_trace(text, "Invalid statute format"),
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
    def _format_match_trace(citation_type: str, text: str) -> list:
        """Trace for a format-matching citation. Format match is PARSED, not authority proof."""
        return [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Matched citation string against a known reporter pattern.",
                inputs={"citation": text, "citation_type": citation_type},
                output=f"Format matched reporter pattern: {citation_type}",
                evidence_type=EVIDENCE_PARSED,
            ),
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Format is valid, but legal authority cannot be confirmed.",
                inputs={"authority_database_access": False},
                output=(
                    "AUTHORITY UNVERIFIABLE: format match is not proof the cited "
                    "authority exists."
                ),
                evidence_type=EVIDENCE_UNSUPPORTED,
            ),
        ]

    @staticmethod
    def _format_invalid_trace(text: str, issue: str) -> list:
        """Trace for a citation that does not match any known format."""
        return [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Checked citation string against known reporter patterns.",
                inputs={"citation": text},
                output=f"No matching pattern: {issue}",
                evidence_type=EVIDENCE_PARSED,
            ),
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Citation format is invalid.",
                inputs={"issue": issue},
                output="FORMAT INVALID",
                evidence_type=EVIDENCE_UNSUPPORTED,
            ),
        ]

    @staticmethod
    def _parse_components(groupdict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerce numeric fields to int where possible.

        Fields coerced: volume, title, page, number, year.
        All other fields are left as-is.
        """
        _NUMERIC_FIELDS = {"volume", "title", "page", "number", "year"}
        result = {}
        for key, value in groupdict.items():
            if value is not None and key in _NUMERIC_FIELDS:
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value
            else:
                result[key] = value
        return result
