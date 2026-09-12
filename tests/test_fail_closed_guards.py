"""
Tests for issue #20: fail-closed enforcement across legal guards.

Covers:
- ContradictionGuard: unsupported categories → UNVERIFIABLE
- ContradictionGuard: empty input → UNVERIFIABLE
- ContradictionGuard: mixed supported+unsupported → partial_coverage warning
- ContradictionGuard: supported categories still work correctly
- ClauseGuard: no extractable propositions → HEURISTIC_PASS caveat, not VERIFIED
- ClauseGuard: known conflicts still detected
- JurisdictionGuard: unknown party countries → warning in result
"""

from qwed_legal.guards.contradiction_guard import Clause, ContradictionGuard
from qwed_legal.guards.clause_guard import ClauseGuard
from qwed_legal.guards.jurisdiction_guard import JurisdictionGuard


# ─── ContradictionGuard ────────────────────────────────────────────────────────


class TestContradictionGuardFailClosed:
    """Issue #20: ContradictionGuard must not silently ignore unsupported categories."""

    def setup_method(self):
        self.guard = ContradictionGuard()

    # Empty input

    def test_empty_clauses_unverifiable(self):
        """Empty list must return UNVERIFIABLE — no constraints ≠ consistent."""
        result = self.guard.verify_consistency([])
        assert result["verified"] is False
        assert result["status"] == "unverifiable"
        assert "UNVERIFIABLE" in result["message"]

    # Unsupported categories

    def test_payment_category_unverifiable(self):
        """PAYMENT clauses are not modeled — must return UNVERIFIABLE."""
        result = self.guard.verify_consistency(
            [
                Clause(text="Payment due in 15 days.", category="PAYMENT", value=15),
                Clause(text="Payment due in 60 days.", category="PAYMENT", value=60),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "unverifiable"
        assert "UNVERIFIABLE" in result["message"]
        assert "PAYMENT" in result["message"]
        assert "PAYMENT" in result["unsupported"]

    def test_penalty_category_unverifiable(self):
        """PENALTY clauses are not modeled — must return UNVERIFIABLE."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Penalty of $5000 for late delivery.",
                    category="PENALTY",
                    value=5000,
                ),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "unverifiable"
        assert "PENALTY" in result["unsupported"]

    def test_novel_category_unverifiable(self):
        """Any category not in {DURATION, LIABILITY} must fail closed."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Confidential for 2 years.",
                    category="CONFIDENTIALITY",
                    value=24,
                ),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "unverifiable"
        assert "CONFIDENTIALITY" in result["unsupported"]

    def test_entirely_unknown_categories_unverifiable(self):
        """Mix of unsupported categories only → UNVERIFIABLE (not silently SAT)."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Pay invoice within 30 days.", category="PAYMENT", value=30
                ),
                Clause(
                    text="Liquidated damages of $1000/day.",
                    category="DAMAGES",
                    value=1000,
                ),
                Clause(
                    text="Govern by English law.", category="GOVERNING_LAW", value=0
                ),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "unverifiable"
        assert len(result["unsupported"]) > 0

    # Partial coverage (some supported, some not)

    def test_mixed_categories_partial_coverage(self):
        """Mix of DURATION + PAYMENT → partial_coverage warning, not silent verification."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Contract duration exactly 12 months.",
                    category="DURATION",
                    value=12,
                ),
                Clause(text="Payment due in 30 days.", category="PAYMENT", value=30),
            ]
        )
        # PAYMENT is unsupported — must be flagged
        assert "PAYMENT" in result["unsupported"]
        # If supported clause (DURATION) is satisfiable, result may be verified=True
        # BUT must carry partial_coverage status, not "consistent"
        if result["verified"]:
            assert result["status"] == "partial_coverage"
            assert (
                "excluded" in result["message"].lower()
                or "unsupported" in result["message"].lower()
            )

    # Supported categories still work

    def test_duration_contradiction_detected(self):
        """DURATION contradiction (min > max) must still be caught."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Contract duration minimum 24 months.",
                    category="DURATION",
                    value=24,
                ),
                Clause(
                    text="Contract duration maximum 12 months.",
                    category="DURATION",
                    value=12,
                ),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "contradiction"

    def test_liability_contradiction_detected(self):
        """LIABILITY contradiction (penalty > cap) must still be caught."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Liability capped at 5000.", category="LIABILITY", value=5000
                ),
                Clause(
                    text="Penalty fixed at 10000.", category="LIABILITY", value=10000
                ),
            ]
        )
        assert result["verified"] is False
        assert result["status"] == "contradiction"

    def test_consistent_duration_clauses_pass(self):
        """Non-contradictory DURATION clauses must return consistent."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Contract duration minimum 6 months.",
                    category="DURATION",
                    value=6,
                ),
                Clause(
                    text="Contract duration maximum 24 months.",
                    category="DURATION",
                    value=24,
                ),
            ]
        )
        assert result["verified"] is True
        assert result["status"] == "consistent"
        assert result["unsupported"] == []

    def test_consistent_liability_clauses_pass(self):
        """Non-contradictory LIABILITY clauses must return consistent."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Liability capped at 50000.", category="LIABILITY", value=50000
                ),
                Clause(
                    text="Penalty fixed at 10000.", category="LIABILITY", value=10000
                ),
            ]
        )
        assert result["verified"] is True
        assert result["status"] == "consistent"

    def test_unsupported_key_in_result(self):
        """Result must always include 'unsupported' key listing skipped categories."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Duration exactly 12 months.", category="DURATION", value=12
                ),
            ]
        )
        assert "unsupported" in result
        assert isinstance(result["unsupported"], list)

    def test_status_key_always_present(self):
        """Result must always include a 'status' field."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Duration exactly 12 months.", category="DURATION", value=12
                ),
            ]
        )
        assert "status" in result
        assert result["status"] in {
            "consistent",
            "contradiction",
            "unverifiable",
            "partial_coverage",
        }


# ─── ClauseGuard ──────────────────────────────────────────────────────────────


class TestClauseGuardFailClosed:
    """Issue #20: ClauseGuard must not claim VERIFIED when coverage is zero."""

    def setup_method(self):
        self.guard = ClauseGuard()

    def test_unsupported_clause_type_is_not_verified(self):
        """
        Clauses with no extractable termination/notice/exclusivity propositions
        must return HEURISTIC_PASS with a caveat, not 'VERIFIED'.
        """
        result = self.guard.check_consistency(
            [
                "Payment shall be made in USD.",
                "Governing law shall be English law.",
            ]
        )
        # Must NOT say "VERIFIED" — no propositions were extracted
        assert (
            "VERIFIED" not in result.message.upper()
            or "HEURISTIC" in result.message.upper()
        )
        # Must indicate limited coverage
        assert any(
            kw in result.message.upper()
            for kw in ["HEURISTIC", "LIMITED", "CANNOT", "COVERAGE"]
        ), f"Expected coverage caveat in: {result.message}"

    def test_known_termination_conflict_still_detected(self):
        """Known conflicts must still be detected after the fix."""
        result = self.guard.check_consistency(
            [
                "Seller may terminate with 30 days notice.",
                "Neither party may terminate before 90 days.",
            ]
        )
        assert result.consistent is False

    def test_single_clause_heuristic(self):
        """Single clause returns consistent — cannot conflict with itself."""
        result = self.guard.check_consistency(
            ["Seller may terminate with 30 days notice."]
        )
        assert result.consistent is True

    def test_payment_clauses_not_falsely_verified(self):
        """Payment-only clauses must not return VERIFIED — guard has no payment model."""
        result = self.guard.check_consistency(
            [
                "Payment due in 15 days.",
                "Payment due in 60 days.",
            ]
        )
        # Must carry the limited-coverage status
        assert result.status == "heuristic_pass_limited"

    def test_heuristic_pass_message_present_for_recognised_clauses(self):
        """Clauses with recognisable termination patterns get HEURISTIC_PASS message."""
        result = self.guard.check_consistency(
            [
                "Seller may terminate with 30 days notice.",
                "Buyer may terminate with 60 days notice.",
            ]
        )
        assert result.consistent is True
        assert "HEURISTIC" in result.message.upper()


# ─── JurisdictionGuard ────────────────────────────────────────────────────────


class TestJurisdictionGuardFailClosed:
    """Issue #20: JurisdictionGuard must not silently skip unknown party countries."""

    def setup_method(self):
        self.guard = JurisdictionGuard()

    def test_unknown_party_country_generates_warning(self):
        """Unknown party country code must appear in warnings, not be silently skipped."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US", "UNKNOWN_COUNTRY_XYZ"],
            governing_law="New York",
        )
        warning_text = " ".join(result.warnings)
        assert "UNKNOWN_COUNTRY_XYZ" in warning_text or any(
            "unrecognized" in w.lower() or "unknown" in w.lower()
            for w in result.warnings
        ), f"Expected unknown country warning. Warnings: {result.warnings}"

    def test_known_party_countries_no_spurious_warning(self):
        """Known countries must not trigger the unknown-country warning."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US", "GB"],
            governing_law="New York",
        )
        unknown_warnings = [
            w
            for w in result.warnings
            if "unrecognized" in w.lower() and ("US" in w or "GB" in w)
        ]
        assert len(unknown_warnings) == 0

    def test_unknown_governing_law_is_conflict(self):
        """Unknown governing law must add to conflicts (existing behaviour preserved)."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US"],
            governing_law="Unknown Territory",
        )
        assert result.verified is False
        assert len(result.conflicts) > 0

    def test_known_governing_law_passes(self):
        """Valid governing law with known parties must not produce conflicts."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US"],
            governing_law="New York",
        )
        assert result.verified is True
        assert len(result.conflicts) == 0

    def test_all_unknown_parties_warns(self):
        """All-unknown party countries must all appear in warnings."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["ATLANTIS", "NARNIA"],
            governing_law="New York",
        )
        warning_text = " ".join(result.warnings)
        assert "ATLANTIS" in warning_text or any(
            "unrecognized" in w.lower() for w in result.warnings
        )

    def test_choice_of_law_warnings_fail_closed(self):
        """Issue #16: warning-only ambiguity must not return verified=True."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["Germany", "India"],
            governing_law="New York",
            forum_selection="New York",
            contract_type="sale_of_goods",
        )

        assert result.verified is False
        assert result.conflicts == []
        assert result.warnings
        assert "UNVERIFIABLE" in result.message
        assert "VERIFIED" not in result.message

    def test_cross_border_legal_system_warning_blocks_verification(self):
        """Known cross-system parties are ambiguous unless further legal analysis resolves them."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["DE", "IN"],
            governing_law="New York",
            forum="New York",
        )

        assert result.verified is False
        assert result.conflicts == []
        assert any("different legal systems" in warning for warning in result.warnings)
        assert "AMBIGUOUS" in result.message

    def test_country_code_state_collision_does_not_hide_foreign_party(self):
        """DE/IN country codes must not be treated as Delaware/Indiana parties."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US", "Germany"],
            governing_law="New York",
        )

        assert result.verified is False
        assert result.conflicts == []
        assert any("CISG" in warning for warning in result.warnings)
        assert "UNVERIFIABLE" in result.message

    def test_domestic_sale_of_goods_does_not_trigger_international_warning(self):
        """Domestic sale-of-goods contracts must not receive a CISG warning."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US", "US"],
            governing_law="New York",
            forum="New York",
            contract_type="sale_of_goods",
        )

        assert result.verified is True
        assert result.conflicts == []
        assert not any("CISG" in warning for warning in result.warnings)

    def test_party_country_normalization_does_not_treat_states_as_foreign(self):
        """State names in party-country input must not become India/Germany."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["Indiana", "Delaware"],
            governing_law="New York",
            forum="New York",
            contract_type="sale_of_goods",
        )

        assert result.verified is True
        assert result.conflicts == []
        assert not result.warnings

    def test_ambiguous_de_code_still_supports_delaware_mismatch_check(self):
        """Raw DE is ambiguous and must still support Delaware mismatch checks."""
        # Raw "DE" can mean Delaware or Germany. In governing-law context, keep
        # it eligible for US-state handling. Non-US parties avoid CISG noise so
        # the assertion focuses on the forum/governing-law mismatch message.
        result = self.guard.verify_choice_of_law(
            parties_countries=["FR", "IT"],
            governing_law="DE",
            forum="London",
        )

        assert any("US state" in conflict for conflict in result.conflicts)

    def test_governing_law_country_name_not_treated_as_us_state(self):
        """Germany normalizes to DE but must remain a country reference."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["FR", "IT"],
            governing_law="Germany",
            forum="London",
        )

        assert result.conflicts == []
        assert not any("US state" in conflict for conflict in result.conflicts)

    def test_state_law_does_not_match_colliding_party_country_code(self):
        """US state laws must not match colliding foreign party country codes."""
        delaware_result = self.guard.verify_choice_of_law(
            parties_countries=["DE", "FR"],
            governing_law="Delaware",
            forum="Delaware",
        )
        indiana_result = self.guard.verify_choice_of_law(
            parties_countries=["IN", "GB"],
            governing_law="Indiana",
            forum="Indiana",
        )

        for result in [delaware_result, indiana_result]:
            assert result.verified is True
            assert result.conflicts == []
            assert not any("favors one party" in warning for warning in result.warnings)

    def test_conflict_message_includes_warning_count_when_both_exist(self):
        """Summary message should mention warnings when conflicts also exist."""
        result = self.guard.verify_choice_of_law(
            parties_countries=["US", "UK"],
            governing_law="Delaware",
            forum="London",
        )

        assert result.conflicts
        assert result.warnings
        assert "CONFLICTS DETECTED" in result.message
        assert "warning" in result.message.lower()


class TestContradictionGuardValueProvenance:
    """Issue #42: clause values are caller-supplied — the guard must
    record whether each encoded value is evidenced by the clause text,
    and keyword matching must not fire on substrings."""

    def setup_method(self):
        self.guard = ContradictionGuard()

    def _fact_steps(self, clauses):
        result = self.guard.verify_consistency(clauses)
        return result, [
            s for s in result["verification_trace"] if s.step == "FACT_DERIVED"
        ]

    def test_caller_invented_value_is_labeled(self):
        """The audit repro: value 999 with text 'exactly 1 month' — the
        solver encodes the TEXT operand (1), never the invented number,
        and the disagreement is disclosed in trace and message."""
        result, steps = self._fact_steps(
            [Clause(text="Contract term is exactly 1 month", category="DURATION", value=999)]
        )
        assert steps[0].inputs["encoded_constraints"] == [{"op": "eq", "operand": 1}]
        assert steps[0].inputs["caller_value"] == 999
        assert steps[0].inputs["caller_value_agrees"] is False
        assert "disagree" in result["message"]

    def test_text_evidenced_value_is_labeled_parsed(self):
        result, steps = self._fact_steps(
            [Clause(text="Liability capped at 5000.", category="LIABILITY", value=5000)]
        )
        assert steps[0].inputs["encoded_constraints"] == [{"op": "le", "operand": 5000}]
        assert steps[0].inputs["caller_value_agrees"] is True

    def test_substring_keyword_no_longer_encodes(self):
        """'cap' inside 'capability' must NOT encode a liability cap —
        the clause is now unmodeled (partial coverage), not mis-encoded."""
        result, steps = self._fact_steps(
            [Clause(text="Our escape capability is legendary.", category="LIABILITY", value=100)]
        )
        assert steps == []  # nothing encoded
        assert result["status"] == "partial_coverage"

    def test_word_boundary_keywords_still_match(self):
        """Real keywords must still encode after the boundary tightening."""
        _, steps = self._fact_steps(
            [
                Clause(text="Term is exactly 6 months.", category="DURATION", value=6),
                Clause(text="Liability capped at 5000.", category="LIABILITY", value=5000),
                Clause(text="Penalty of at least 500.", category="LIABILITY", value=500),
            ]
        )
        assert len(steps) == 3

    def test_keyword_without_operand_is_unmodeled(self):
        """A recognized keyword with no adjacent number cannot be encoded
        from the caller's value — the clause stays unmodeled."""
        result, steps = self._fact_steps(
            [Clause(text="Term is 12 months minimum.", category="DURATION", value=1)]
        )
        assert steps == []
        assert result["status"] == "partial_coverage"

    def test_provenance_binds_to_constraint_operand(self):
        """The encoded operand is the one bound to the recognized phrase —
        a number elsewhere in the text does not evidence a differing
        caller value, which is disclosed as a disagreement (PR #45
        review, CodeRabbit)."""
        result, steps = self._fact_steps(
            [
                Clause(
                    text="Term is exactly 12 months; notice is 6 days.",
                    category="DURATION",
                    value=6,
                )
            ]
        )
        assert steps[0].inputs["encoded_constraints"] == [{"op": "eq", "operand": 12}]
        assert steps[0].inputs["caller_value"] == 6
        assert steps[0].inputs["caller_value_agrees"] is False
        assert "disagree" in result["message"]

    def test_unsat_is_text_attributable_with_disagreements_disclosed(self):
        """The solver encodes only text-derived operands, so an UNSAT is
        a genuine text contradiction even when caller declarations
        disagree; the disagreements stay visible in the trace."""
        result = self.guard.verify_consistency(
            [
                Clause(text="Contract term is exactly 1 month", category="DURATION", value=999),
                Clause(text="Contract term is exactly 2 months", category="DURATION", value=888),
            ]
        )
        assert result["status"] == "contradiction"
        conclusion = [s for s in result["verification_trace"] if s.step == "CONCLUSION"][0]
        assert conclusion.evidence_type == "DETERMINISTIC"
        fact_steps = [s for s in result["verification_trace"] if s.step == "FACT_DERIVED"]
        assert [s.inputs["encoded_constraints"] for s in fact_steps] == [[{"op": "eq", "operand": 1}], [{"op": "eq", "operand": 2}]]
        assert all(s.inputs["caller_value_agrees"] is False for s in fact_steps)
        assert "disagree" in result["message"]

    def test_unsat_over_evidenced_values_is_deterministic_contradiction(self):
        """Fully text-evidenced conflicting values keep the deterministic
        contradiction verdict."""
        result = self.guard.verify_consistency(
            [
                Clause(text="Contract term is exactly 12 months", category="DURATION", value=12),
                Clause(text="Contract term is maximum 2 months", category="DURATION", value=2),
            ]
        )
        assert result["status"] == "contradiction"
        conclusion = [s for s in result["verification_trace"] if s.step == "CONCLUSION"][0]
        assert conclusion.evidence_type == "DETERMINISTIC"

    def test_disagreeing_declaration_does_not_change_solver_conclusion(self):
        """A differing caller declaration is unused by the solver — it
        must not downgrade a text-derived conclusion (PR #45 review,
        CodeRabbit/Greptile)."""
        result = self.guard.verify_consistency(
            [Clause(text="Contract term is exactly 1 month", category="DURATION", value=999)]
        )
        assert result["status"] == "consistent"
        assert result["verified"] is True
        assert "disagree" in result["message"]

    def test_encoding_steps_are_deterministic(self):
        """Every encoded constraint is a deterministic encoding of a
        text-derived operand."""
        result = self.guard.verify_consistency(
            [
                Clause(text="Contract term is exactly 1 month", category="DURATION", value=999),
                Clause(text="Term is exactly 6 months.", category="DURATION", value=6),
            ]
        )
        for s in result["verification_trace"]:
            if s.step == "FACT_DERIVED":
                assert s.evidence_type == "DETERMINISTIC"
                assert s.is_proven() is True

    def test_unsupported_numeric_operands_fail_closed(self):
        """Signed, decimal, formatted, and embedded operands are
        unsupported — the clause stays unmodeled rather than encoding an
        altered value (PR #45 review, CodeRabbit)."""
        for text, bad_operand in [
            ("Term is exactly -30 days.", "-30"),
            ("Term is exactly 1.5 months.", "1.5"),
            ("Cap is exactly 1,500 dollars.", "1,500"),
            ("Term is exactly 1e3 months.", "1e3"),
            ("Term is exactly - 30 days.", "- 30 (spaced sign)"),
            # Non-ASCII digits pass isdigit() but crash int() — the
            # operand grammar is ASCII-only, so these fail closed
            # (PR #45 review, Sentry HIGH).
            ("Term is exactly ²³ days.", "²³ (superscript)"),
            ("Term is exactly ٣٠ days.", "٣٠ (arabic-indic)"),
        ]:
            result, steps = self._fact_steps(
                [Clause(text=text, category="DURATION", value=30)]
            )
            assert steps == [], f"{bad_operand} must not encode"
            assert result["status"] == "partial_coverage"

    def test_spaced_sign_is_not_encoded(self):
        """'exactly - 30 days' must not encode 30 — the whitespace-
        separated sign invalidates the operand (PR #45 review, Greptile
        executed bypass)."""
        result = self.guard.verify_consistency(
            [
                Clause(text="Term is exactly - 30 days.", category="DURATION", value=30),
                Clause(text="Term is maximum 29 days.", category="DURATION", value=29),
            ]
        )
        # The signed clause is unmodeled; the modeled maximum-29 clause
        # alone is satisfiable — no contradiction is manufactured from
        # a silently sign-stripped operand.
        assert result["status"] == "partial_coverage"
        assert result["verified"] is False

    def test_malformed_operand_fails_closed_whole_clause(self):
        """A recognized phrase with a malformed operand fails closed the
        WHOLE clause — encoding only the later valid subset would present
        a partial model as complete and could hide a conflict
        (PR #45 review, Greptile-executed)."""
        result, steps = self._fact_steps(
            [
                Clause(
                    text="Liability is capped at 1.5 million; maximum is 5000.",
                    category="LIABILITY",
                    value=5000,
                )
            ]
        )
        assert steps == []
        assert result["status"] == "partial_coverage"
        assert result["verified"] is False

    def test_malformed_rule_does_not_hide_conflict(self):
        """Greptile's executed scenario: the malformed clause is skipped,
        so the modeled subset cannot report a false fully-verified
        agreement when the omitted amount might conflict."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Liability is fixed at 1.5 million and minimum is 100.",
                    category="LIABILITY",
                    value=100,
                ),
                Clause(text="Liability is capped at 200.", category="LIABILITY", value=200),
            ]
        )
        assert result["status"] == "partial_coverage"
        assert result["verified"] is False

    def test_multiple_valid_constraints_in_one_clause_all_encoded(self):
        """A clause stating several recognized constraints encodes all of
        them, not just the first."""
        _, steps = self._fact_steps(
            [
                Clause(
                    text="Liability is capped at 5000 and maximum is 6000.",
                    category="LIABILITY",
                    value=5000,
                )
            ]
        )
        assert len(steps) == 1
        assert steps[0].inputs["encoded_constraints"] == [
            {"op": "le", "operand": 5000},
            {"op": "le", "operand": 6000},
        ]

    def test_phrase_suffixes_are_not_recognized(self):
        """Terminal word boundaries: 'maximumly' and 'capability' must
        not match their phrase prefixes (PR #45 review, CodeRabbit)."""
        for text in ["Term is maximumly 2 months.", "Our capability 100 is legendary."]:
            result, steps = self._fact_steps(
                [
                    Clause(text=text, category="DURATION" if "maximumly" in text else "LIABILITY", value=2)
                ]
            )
            assert steps == [], f"{text!r} must not encode"
            assert result["status"] == "partial_coverage"

    def test_legacy_value_provenance_field_retained(self):
        """The legacy value_provenance trace field is retained during the
        deprecation window; under operand binding every encoded operand
        is text-derived (PR #45 review, Greptile P1)."""
        _, steps = self._fact_steps(
            [Clause(text="Term is exactly 6 months.", category="DURATION", value=6)]
        )
        assert steps[0].inputs["value_provenance"] == "parsed_from_text"

    def test_repeated_same_phrase_all_encoded(self):
        """Every occurrence of a repeated phrase is a separate
        constraint — 'capped at 7000 and capped at 5000' with penalty
        6000 is contradictory (PR #45 review, Greptile R6 executed)."""
        result = self.guard.verify_consistency(
            [
                Clause(
                    text="Liability is capped at 7000 and capped at 5000.",
                    category="LIABILITY",
                    value=7000,
                ),
                Clause(text="Penalty is 6000.", category="LIABILITY", value=6000),
            ]
        )
        assert result["status"] == "contradiction"
        fact_steps = [s for s in result["verification_trace"] if s.step == "FACT_DERIVED"]
        assert fact_steps[0].inputs["encoded_constraints"] == [
            {"op": "le", "operand": 7000},
            {"op": "le", "operand": 5000},
        ]

    def test_repeated_malformed_phrase_fails_closed(self):
        """A later malformed repeated phrase makes the whole clause
        unmodeled, not just skipped (PR #45 review, Greptile R6)."""
        result, steps = self._fact_steps(
            [
                Clause(
                    text="Liability is capped at 7000 and capped at 1.5 million.",
                    category="LIABILITY",
                    value=7000,
                )
            ]
        )
        assert steps == []
        assert result["status"] == "partial_coverage"
        assert result["verified"] is False

    def test_unicode_operand_fails_closed_whole_clause(self):
        """A recognized phrase followed by a non-ASCII numeral is a
        malformed constraint — the whole clause fails closed instead of
        silently omitting it (PR #45 review, Greptile R8 executed)."""
        result, steps = self._fact_steps(
            [
                Clause(
                    text="Term is exactly 12 and exactly \u0663\u0660 days.",
                    category="DURATION",
                    value=12,
                )
            ]
        )
        assert steps == []
        assert result["status"] == "partial_coverage"
        assert result["verified"] is False

    def test_prose_phrase_occurrences_are_not_constraints(self):
        """A recognized word in prose (no operand follows) is not a
        constraint occurrence and does not taint other rules — 'Max'
        before 'capped at 5000' is an abbreviation, not a maximum
        constraint (PR #45 review, R8 detector refinement)."""
        result, steps = self._fact_steps(
            [Clause(text="Max liability capped at 5000", category="LIABILITY", value=5000)]
        )
        assert len(steps) == 1
        assert steps[0].inputs["encoded_constraints"] == [{"op": "le", "operand": 5000}]
        assert result["status"] == "consistent"
        assert result["verified"] is True


class TestClauseGuardDayExtraction:
    """Issue #41: day extraction must cover phrasings where the day count
    is not directly attached to the context word."""

    def setup_method(self):
        self.guard = ClauseGuard()

    def test_issue_repro_proximity_extraction(self):
        """'give notice within 10 days of discovery' returned None before
        the fix — the number is separated from 'notice' by 'within'."""
        days = self.guard._extract_days(
            "buyer shall give notice within 10 days of discovery", "notice"
        )
        assert days == 10

    def test_directional_patterns_still_work(self):
        assert self.guard._extract_days(
            "seller may terminate with 30 days notice", "notice"
        ) == 30
        assert self.guard._extract_days(
            "neither party may terminate before 90 days from execution", "before"
        ) == 90

    def test_no_day_expression_near_context_returns_none(self):
        assert self.guard._extract_days(
            "the notice requirement is governed by the appendix", "notice"
        ) is None

    def test_proximity_requires_context_word_nearby(self):
        """A day-expression far from the context word must not be
        misattributed."""
        far_text = (
            "notice requirements are set out in the earlier provisions of this "
            "agreement, and the Parties shall comply with a 10 days cure period "
            "described elsewhere"
        )
        assert self.guard._extract_days(far_text, "notice") is None
