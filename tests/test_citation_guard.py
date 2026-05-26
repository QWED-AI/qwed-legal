"""
Tests for issue #17: CitationGuard must not conflate format validity with authority proof.

Key invariants:
- verified is ALWAYS False — CitationGuard has no database access
- format_valid=True → status=unverifiable_authority, NEVER a claim of legal existence
- Fabricated well-formed citations (Unicorn v. Rainbow) must get same treatment as real ones
- FORMAT_INVALID for malformed, unknown reporters, missing case names
- BatchCitationResult uses format_valid/format_invalid (not valid/invalid)
- verify_citation_format() explicitly returns authority_verified=False
- check_statute_citation() same semantics
"""

from qwed_legal.guards.citation_guard import (
    CitationGuard,
    STATUS_FORMAT_INVALID,
    STATUS_UNVERIFIABLE_AUTHORITY,
)


class TestCitationGuardSemantics:
    """Core semantic invariants — format ≠ authority."""

    def setup_method(self):
        self.guard = CitationGuard()

    # verified is ALWAYS False

    def test_verified_always_false_for_real_citation(self):
        """verified must be False even for well-known real cases."""
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert (
            result.verified is False
        ), "CitationGuard.verified must always be False — it has no database access"

    def test_verified_always_false_for_fabricated_citation(self):
        """The core bug: fabricated but well-formed citations must not be 'verified'."""
        result = self.guard.verify("Unicorn v. Rainbow, 347 U.S. 483 (1999)")
        assert (
            result.verified is False
        ), "A fabricated citation with a plausible reporter must never return verified=True"

    def test_verified_always_false_for_hallucinated_citation(self):
        """Hallucinated citation with correct reporter format must not be 'verified'."""
        result = self.guard.verify("Nonexistent v. Case, 123 F.3d 456 (2020)")
        assert result.verified is False

    def test_verified_always_false_for_invalid_citation(self):
        """Invalid citations must also return verified=False (not just valid ones)."""
        result = self.guard.verify("Fake v. Case, 999 X.Y.Z. 123 (2020)")
        assert result.verified is False

    # status field semantics

    def test_format_valid_citation_has_unverifiable_authority_status(self):
        """format_valid=True must produce status=unverifiable_authority, not format_valid."""
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.format_valid is True
        assert (
            result.status == STATUS_UNVERIFIABLE_AUTHORITY
        ), f"Expected status=unverifiable_authority but got: {result.status}"

    def test_fabricated_format_valid_citation_has_unverifiable_status(self):
        """Fabricated but format-valid citation must carry unverifiable_authority status."""
        result = self.guard.verify("Unicorn v. Rainbow, 347 U.S. 483 (1999)")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY

    def test_invalid_citation_has_format_invalid_status(self):
        """Malformed citation must return status=format_invalid."""
        result = self.guard.verify("Fake v. Case, 999 X.Y.Z. 123 (2020)")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID

    # message must state authority is unverifiable

    def test_format_valid_message_states_authority_unverifiable(self):
        """Message for format_valid=True must explicitly warn about authority."""
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.format_valid is True
        assert (
            "UNVERIFIABLE" in result.message.upper()
            or "AUTHORITY" in result.message.upper()
        ), f"Expected UNVERIFIABLE/AUTHORITY in message but got: {result.message}"

    def test_fabricated_citation_message_states_authority_unverifiable(self):
        """Same warning must appear for fabricated citations."""
        result = self.guard.verify("Unicorn v. Rainbow, 347 U.S. 483 (1999)")
        assert (
            "UNVERIFIABLE" in result.message.upper()
            or "AUTHORITY" in result.message.upper()
        )


class TestCitationFormatValidation:
    """Format validation still works correctly after the fix."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_scotus_format_valid(self):
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.format_valid is True
        assert result.citation_type == "US_SCOTUS"
        assert result.parsed_components.get("volume") == 347
        assert result.parsed_components.get("reporter") == "U.S."

    def test_federal_reporter_format_valid(self):
        result = self.guard.verify("Smith v. Jones, 123 F.3d 456 (2020)")
        assert result.format_valid is True
        assert result.citation_type == "US_FED"
        assert result.parsed_components.get("reporter") == "F.3d"

    def test_unknown_reporter_format_invalid(self):
        result = self.guard.verify("Fake v. Case, 999 X.Y.Z. 123 (2020)")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID
        assert any("Unknown reporter" in issue for issue in result.issues)

    def test_missing_case_name_format_invalid(self):
        result = self.guard.verify("123 U.S. 456 (1990)")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID
        assert any("case name" in issue.lower() for issue in result.issues)

    def test_no_citation_format_invalid(self):
        result = self.guard.verify("This is just plain text with no citation.")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID

    # backward compat
    def test_valid_property_aliases_format_valid(self):
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.valid == result.format_valid


class TestStatuteCitationGuard:
    """check_statute_citation: same FORMAT_ONLY semantics."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_valid_statute_format(self):
        result = self.guard.check_statute_citation("42 U.S.C. § 1983")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY
        assert result.parsed_components.get("title") == 42

    def test_valid_statute_verified_always_false(self):
        result = self.guard.check_statute_citation("42 U.S.C. § 1983")
        assert result.verified is False

    def test_invalid_statute_format_invalid(self):
        result = self.guard.check_statute_citation("this is not a statute")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID

    def test_fabricated_statute_number_treated_same_as_real(self):
        """Nonexistent section 99999 passes format check — same UNVERIFIABLE status."""
        result = self.guard.check_statute_citation("42 U.S.C. § 99999")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY
        assert result.verified is False


class TestVerifyCitationFormat:
    """verify_citation_format() must explicitly expose authority_verified=False."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_authority_verified_always_false_in_dict(self):
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert result["authority_verified"] is False

    def test_authority_note_present(self):
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert "authority_note" in result
        assert len(result["authority_note"]) > 0

    def test_format_valid_in_dict(self):
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert result["format_valid"] is True

    def test_status_in_dict(self):
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert result["status"] == STATUS_UNVERIFIABLE_AUTHORITY


class TestBatchCitationResult:
    """verify_batch uses format_valid/format_invalid fields."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_batch_counts_are_correct(self):
        citations = [
            "Brown v. Board, 347 U.S. 483 (1954)",  # format_valid
            "Invalid v. Citation, 999 FAKE 123",  # format_invalid
        ]
        result = self.guard.verify_batch(citations)
        assert result.total == 2
        assert result.format_valid == 1
        assert result.format_invalid == 1

    def test_batch_valid_alias(self):
        """Backward-compat: result.valid == result.format_valid."""
        citations = ["Brown v. Board, 347 U.S. 483 (1954)", "Fake v. X, 999 XYZ 1"]
        result = self.guard.verify_batch(citations)
        assert result.valid == result.format_valid

    def test_batch_invalid_alias(self):
        citations = ["Brown v. Board, 347 U.S. 483 (1954)", "Fake v. X, 999 XYZ 1"]
        result = self.guard.verify_batch(citations)
        assert result.invalid == result.format_invalid

    def test_batch_verified_count_not_exposed(self):
        """BatchCitationResult must NOT expose a 'verified' count — authority not checked."""
        citations = ["Brown v. Board, 347 U.S. 483 (1954)"]
        result = self.guard.verify_batch(citations)
        assert not hasattr(result, "verified"), (
            "BatchCitationResult must not expose a 'verified' count — "
            "CitationGuard cannot verify authority"
        )


class TestStatusConstants:
    """Status constants are importable and have correct values."""

    def test_status_constants_exist(self):
        """Only STATUS_FORMAT_INVALID and STATUS_UNVERIFIABLE_AUTHORITY are returned."""
        assert STATUS_FORMAT_INVALID == "format_invalid"
        assert STATUS_UNVERIFIABLE_AUTHORITY == "unverifiable_authority"

    def test_format_valid_status_never_returned(self):
        """format_valid status is never returned — would conflate format with authority."""
        from qwed_legal.guards.citation_guard import CitationGuard as CG

        r = CG().verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert r.status != "format_valid"
        assert r.status == STATUS_UNVERIFIABLE_AUTHORITY


class TestCitationReviewFixes:
    """
    Tests covering all valid PR review comments.

    Sentry HIGH   — citation field present and populated
    Codex P2      — deprecated 'verified' key restored in verify_citation_format()
    CodeRabbit    — AT&T and other special-char party names not misclassified
    CodeRabbit    — UK neutral citations accepted without case name
    CodeRabbit    — year coerced to int in parsed_components
    """

    def setup_method(self):
        self.guard = CitationGuard()

    # Sentry HIGH — citation field

    def test_citation_field_populated_on_format_valid(self):
        """CitationResult.citation must contain the original input text (TS SDK needs it)."""
        text = "Brown v. Board of Education, 347 U.S. 483 (1954)"
        result = self.guard.verify(text)
        assert result.citation == text

    def test_citation_field_populated_on_format_invalid(self):
        """citation field must be set even for invalid citations."""
        text = "totally invalid text"
        result = self.guard.verify(text)
        assert result.citation == text

    def test_citation_field_populated_for_fabricated(self):
        """citation field present for fabricated-but-well-formed citations."""
        text = "Unicorn v. Rainbow, 347 U.S. 483 (1999)"
        result = self.guard.verify(text)
        assert result.citation == text

    # Codex P2 — deprecated 'verified' key in verify_citation_format()

    def test_verify_citation_format_has_deprecated_verified_key(self):
        """verify_citation_format() must keep 'verified' key for backward compat."""
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert (
            "verified" in result
        ), "Dropped 'verified' key breaks existing integrations that do result['verified']"

    def test_verify_citation_format_deprecated_verified_equals_format_valid(self):
        """Deprecated 'verified' == format_valid (not authority_verified)."""
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert result["verified"] == result["format_valid"]

    def test_verify_citation_format_authority_verified_false_canonical(self):
        """authority_verified=False remains the canonical authority field."""
        result = self.guard.verify_citation_format(
            "Brown v. Board of Education, 347 U.S. 483 (1954)"
        )
        assert result["authority_verified"] is False

    # CodeRabbit MAJOR — special-char party names

    def test_atandt_party_name_not_misclassified(self):
        """AT&T in party name must not be rejected as 'Missing case name'."""
        result = self.guard.verify(
            "AT&T Mobility LLC v. Concepcion, 563 U.S. 333 (2011)"
        )
        assert (
            result.format_valid is True
        ), f"AT&T citation should be format_valid but got: {result.issues}"
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY

    def test_us_plaintiff_not_misclassified(self):
        """'U.S. v. Windsor' style party name must not fail case-name check."""
        result = self.guard.verify("U.S. v. Windsor, 570 U.S. 744 (2013)")
        assert result.format_valid is True

    def test_hyphenated_party_name_not_misclassified(self):
        """Hyphen in party name must not fail case-name check."""
        result = self.guard.verify("Obergefell v. Hodges, 576 U.S. 644 (2015)")
        assert result.format_valid is True

    # CodeRabbit — UK neutral citation accepted without case name

    def test_uk_neutral_citation_no_case_name_required(self):
        """UK neutral citations like [2020] UKSC 5 must pass without 'v.' party names."""
        result = self.guard.verify("[2020] UKSC 5")
        assert result.format_valid is True
        assert result.citation_type == "UK_NEUTRAL"
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY

    def test_uk_neutral_year_is_int(self):
        """Year in UK neutral citation must be coerced to int."""
        result = self.guard.verify("[2020] UKSC 5")
        assert result.format_valid is True
        year = result.parsed_components.get("year")
        assert isinstance(year, int), f"Expected year as int, got {type(year)}: {year}"
        assert year == 2020

    # CodeRabbit MINOR — year coerced to int for all patterns

    def test_india_air_year_is_int(self):
        """Year in INDIA_AIR citation must be coerced to int."""
        result = self.guard.verify("AIR 2001 SC 3021")
        assert result.format_valid is True
        year = result.parsed_components.get("year")
        assert isinstance(year, int), f"Expected year as int, got {type(year)}: {year}"
        assert year == 2001

    def test_scotus_volume_is_int(self):
        """Volume in SCOTUS citation is still coerced to int."""
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        vol = result.parsed_components.get("volume")
        assert isinstance(vol, int)
        assert vol == 347

    # Sentry MEDIUM rejection verification — unverifiable_authority must NOT fail CI
    # (no code test needed — this is a design decision, not a code path)
    # The action_entrypoint.py correctly gates failure on format_invalid only.
    # Adding a test to confirm action_entrypoint logic is unchanged would require
    # subprocess testing; that is out of scope for unit tests.


class TestCitationEarlyReturnBug:
    """Sentry MEDIUM: premature return prevented later patterns from being checked."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_neutral_citation_not_blocked_by_scotus_miss(self):
        """UK neutral citation must not be rejected because US_SCOTUS had a partial match."""
        result = self.guard.verify("[2020] UKSC 5")
        assert result.format_valid is True
        assert result.citation_type == "UK_NEUTRAL"

    def test_india_air_not_blocked_by_earlier_pattern(self):
        """INDIA_AIR must be evaluated even if an earlier pattern partially matched."""
        result = self.guard.verify("AIR 2001 SC 3021")
        assert result.format_valid is True
        assert result.citation_type == "INDIA_AIR"

    def test_bare_scotus_reporter_no_case_name_is_format_invalid(self):
        """No case name, no alternative pattern: must still return format_invalid."""
        result = self.guard.verify("347 U.S. 483")
        assert result.format_valid is False
        assert result.status == "format_invalid"


class TestCaseNamePositionCheck:
    """Sentry LOW: case name v. must appear before the reporter volume, not after."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_case_name_after_reporter_is_format_invalid(self):
        """'347 U.S. 483 Smith v. Jones' must be invalid -- name is after reporter."""
        result = self.guard.verify("347 U.S. 483 Smith v. Jones")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID

    def test_case_name_before_reporter_is_valid(self):
        """Normal citation with name before reporter must pass."""
        result = self.guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY

    def test_atandt_before_reporter_passes(self):
        """Special-char party name before reporter must still pass."""
        result = self.guard.verify(
            "AT&T Mobility LLC v. Concepcion, 563 U.S. 333 (2011)"
        )
        assert result.format_valid is True

    def test_federal_reporter_name_after_reporter_invalid(self):
        """Same positional check applies to F.3d reporter."""
        result = self.guard.verify("123 F.3d 456 Fake v. Case")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID


class TestMixedCitationStatuteFallback:
    """Sentry MEDIUM: bare case fragments must not block valid statute parsing."""

    def setup_method(self):
        self.guard = CitationGuard()

    def test_bare_case_fragment_does_not_block_later_statute(self):
        """A missing case-name fragment should not prevent statute format detection."""
        result = self.guard.verify("347 U.S. 483 and 42 U.S.C. § 1983")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY
        assert result.citation_type == "US_CODE"
        assert result.verified is False

    def test_later_bare_case_fragment_does_not_block_earlier_statute(self):
        """Order should not matter when a valid statute citation is present."""
        result = self.guard.verify("42 U.S.C. § 1983 and 347 U.S. 483")
        assert result.format_valid is True
        assert result.status == STATUS_UNVERIFIABLE_AUTHORITY
        assert result.citation_type == "US_CODE"
        assert result.verified is False

    def test_bare_case_without_statute_still_missing_case_name(self):
        """The fallback must not weaken case-name enforcement for case reporters."""
        result = self.guard.verify("347 U.S. 483")
        assert result.format_valid is False
        assert result.status == STATUS_FORMAT_INVALID
        assert any("case name" in issue.lower() for issue in result.issues)
