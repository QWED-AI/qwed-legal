"""
ProvenanceGuard — Verifies AI-generated content provenance and disclosure compliance.

Ensures that AI-generated legal content carries proper attribution metadata,
disclosure markers, and provenance chains. Designed to support compliance with
AI transparency requirements (e.g., California CAITA 2026, EU AI Act Article 50).

All checks are deterministic — no LLM calls required.
"""

import re
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ProvenanceRecord:
    """
    Metadata structure for tracking AI content provenance.

    Fields:
        content_hash:           SHA-256 hash of the AI-generated content.
        model_id:               Identifier of the model that generated the content.
        generation_timestamp:   ISO-8601 timestamp of generation.
        disclosure_text:        Human-readable AI disclosure statement.
        human_reviewed:         Whether a human has reviewed the content.
        reviewer_id:            Identifier of the human reviewer (if applicable).
    """
    content_hash: str
    model_id: str
    generation_timestamp: str
    disclosure_text: str = ""
    human_reviewed: bool = False
    reviewer_id: Optional[str] = None


class ProvenanceGuard:
    """
    Verifies AI-generated content carries proper provenance metadata
    and disclosure markers.

    Six checks (first three always run, last three are configurable):
    1. **Metadata Completeness** — required fields are present and valid
    2. **Hash Integrity** — content hash matches the actual content
    3. **Timestamp Validity** — ISO-8601 format, not in the future
    4. **Disclosure Compliance** — content includes an AI-generation disclosure
    5. **Model Allowlist** — model_id is in the approved list
    6. **Human Review** — content has been reviewed by a human

    All checks are fully deterministic.
    """

    # Minimum required disclosure keywords (case-insensitive)
    _DISCLOSURE_PATTERN_STRINGS = [
        r"ai[\-\s]generated",
        r"generated\s+by\s+(an?\s+)?ai",
        r"produced\s+(by|using)\s+(an?\s+)?(artificial\s+intelligence|ai|llm)",
        r"machine[\-\s]generated",
        r"automated[\-\s]content",
        r"this\s+(document|content|output)\s+was\s+(generated|created|produced)\s+(by|using)",
    ]
    # Pre-compiled patterns for performance
    DISCLOSURE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DISCLOSURE_PATTERN_STRINGS]

    REQUIRED_METADATA_FIELDS = {
        "content_hash",
        "model_id",
        "generation_timestamp",
    }

    def __init__(
        self,
        require_disclosure: bool = True,
        require_human_review: bool = False,
        allowed_models: Optional[List[str]] = None,
    ):
        """
        Args:
            require_disclosure: Require AI disclosure text in the content.
            require_human_review: Require human_reviewed=True in provenance.
            allowed_models: Allowlist of model IDs. None = allow all;
                            empty list = deny all.
        """
        self.require_disclosure = require_disclosure
        self.require_human_review = require_human_review
        self.allowed_models = allowed_models

    def verify_provenance(
        self,
        content: str,
        provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Full provenance verification pipeline.

        Args:
            content: The AI-generated text to verify.
            provenance: Metadata dict with content_hash, model_id, etc.

        Returns:
            Dict with 'verified', 'checks_passed', 'checks_failed',
            'risk', and 'message' keys.
        """
        if not isinstance(content, str) or not content.strip():
            return self._result(
                verified=False,
                risk="INVALID_CONTENT",
                message="Content must be a non-empty string",
                checks_failed=["content_valid"],
            )

        if not isinstance(provenance, dict):
            return self._result(
                verified=False,
                risk="INVALID_PROVENANCE",
                message="Provenance must be a dict",
                checks_failed=["provenance_valid"],
            )

        checks_passed: List[str] = []
        checks_failed: List[str] = []

        # Check 1: Metadata completeness
        self._check_metadata(provenance, checks_passed, checks_failed)

        # Check 2: Hash integrity
        self._check_hash_integrity(content, provenance, checks_passed, checks_failed)

        # Check 3: Timestamp validity
        self._check_timestamp(provenance, checks_passed, checks_failed)

        # Check 4: AI disclosure
        if self.require_disclosure:
            self._check_disclosure(content, checks_passed, checks_failed)

        # Check 5: Model allowlist
        if self.allowed_models is not None:
            self._check_model_allowed(provenance, checks_passed, checks_failed)

        # Check 6: Human review requirement
        if self.require_human_review:
            self._check_human_review(provenance, checks_passed, checks_failed)

        if checks_failed:
            risk = self._classify_risk(checks_failed)
            return self._result(
                verified=False,
                risk=risk,
                message=f"Provenance verification failed: {', '.join(checks_failed)}",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )

        return self._result(
            verified=True,
            message="All provenance checks passed",
            checks_passed=checks_passed,
        )

    def generate_provenance(
        self,
        content: str,
        model_id: str,
        disclosure_text: str = "",
        human_reviewed: bool = False,
        reviewer_id: Optional[str] = None,
    ) -> ProvenanceRecord:
        """
        Generate a ProvenanceRecord for a piece of AI-generated content.

        Args:
            content: The AI-generated text.
            model_id: Identifier of the generating model.
            disclosure_text: Optional disclosure statement.
            human_reviewed: Whether a human reviewed this content.
            reviewer_id: Identifier of the reviewer.

        Returns:
            ProvenanceRecord with computed hash and timestamp.
        """
        content_hash = self._compute_hash(content)
        timestamp = datetime.now(timezone.utc).isoformat()

        return ProvenanceRecord(
            content_hash=content_hash,
            model_id=model_id,
            generation_timestamp=timestamp,
            disclosure_text=disclosure_text,
            human_reviewed=human_reviewed,
            reviewer_id=reviewer_id,
        )

    # ---- Private check methods ----

    def _check_metadata(
        self, provenance: Dict[str, Any],
        passed: List[str], failed: List[str],
    ) -> None:
        missing = self.REQUIRED_METADATA_FIELDS - set(provenance.keys())
        if missing:
            failed.append("metadata_completeness")
        else:
            # Also check for empty values
            empty = [
                k for k in self.REQUIRED_METADATA_FIELDS
                if not str(provenance.get(k, "")).strip()
            ]
            if empty:
                failed.append("metadata_completeness")
            else:
                passed.append("metadata_completeness")

    @staticmethod
    def _check_hash_integrity(
        content: str, provenance: Dict[str, Any],
        passed: List[str], failed: List[str],
    ) -> None:
        stored_hash = provenance.get("content_hash", "")
        if not stored_hash:
            # Hash will be caught by metadata_completeness check
            return
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if stored_hash != expected:
            failed.append("hash_integrity")
        else:
            passed.append("hash_integrity")

    @staticmethod
    def _check_timestamp(
        provenance: Dict[str, Any],
        passed: List[str], failed: List[str],
    ) -> None:
        ts = provenance.get("generation_timestamp", "")
        if not ts:
            return  # Caught by metadata_completeness
        try:
            parsed = datetime.fromisoformat(str(ts))
            # Reject timestamps in the future
            now = datetime.now(timezone.utc)
            if parsed.tzinfo is None:
                # Assume naive timestamps are UTC
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed > now:
                failed.append("timestamp_valid")
            else:
                passed.append("timestamp_valid")
        except (ValueError, TypeError):
            failed.append("timestamp_valid")

    def _check_disclosure(
        self, content: str,
        passed: List[str], failed: List[str],
    ) -> None:
        for pattern in self.DISCLOSURE_PATTERNS:
            if pattern.search(content):
                passed.append("disclosure_present")
                return
        failed.append("disclosure_present")

    def _check_model_allowed(
        self, provenance: Dict[str, Any],
        passed: List[str], failed: List[str],
    ) -> None:
        model_id = provenance.get("model_id", "")
        if not model_id:
            return  # Caught by metadata_completeness
        if model_id not in self.allowed_models:
            failed.append("model_allowed")
        else:
            passed.append("model_allowed")

    @staticmethod
    def _check_human_review(
        provenance: Dict[str, Any],
        passed: List[str], failed: List[str],
    ) -> None:
        if not provenance.get("human_reviewed", False):
            failed.append("human_review")
        else:
            passed.append("human_review")

    # ---- Helpers ----

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _classify_risk(failed_checks: List[str]) -> str:
        if "hash_integrity" in failed_checks:
            return "CONTENT_TAMPERED"
        if "metadata_completeness" in failed_checks:
            return "INCOMPLETE_PROVENANCE"
        if "disclosure_present" in failed_checks:
            return "MISSING_DISCLOSURE"
        if "model_allowed" in failed_checks:
            return "UNAUTHORIZED_MODEL"
        if "human_review" in failed_checks:
            return "UNREVIEWED_CONTENT"
        if "timestamp_valid" in failed_checks:
            return "INVALID_TIMESTAMP"
        return "PROVENANCE_VERIFICATION_FAILED"

    @staticmethod
    def _result(
        verified: bool,
        risk: str = "",
        message: str = "",
        checks_passed: Optional[List[str]] = None,
        checks_failed: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "verified": verified,
            "risk": risk,
            "message": message,
            "checks_passed": checks_passed or [],
            "checks_failed": checks_failed or [],
        }
