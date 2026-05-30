"""
tests/test_verification_trace.py

Phase-1 regression tests for verification_trace on StatuteGuard and ContradictionGuard.
"""

from qwed_legal.guards.statute_guard import StatuteOfLimitationsGuard
from qwed_legal.guards.contradiction_guard import ContradictionGuard, Clause
from qwed_legal.guards.deadline_guard import DeadlineGuard
from qwed_legal.guards.liability_guard import LiabilityGuard
from qwed_legal.guards.jurisdiction_guard import JurisdictionGuard
from qwed_legal.guards.clause_guard import ClauseGuard
from qwed_legal.guards.citation_guard import CitationGuard
from qwed_legal.guards.irac_guard import IRACGuard
from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_AMBIGUITY_NOTED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
    EVIDENCE_INFERRED,
    EVIDENCE_UNSUPPORTED,
)


def _statute(**kwargs):
    g = StatuteOfLimitationsGuard()
    defaults = dict(
        claim_type="breach_of_contract",
        jurisdiction="California",
        incident_date="2020-01-01",
        filing_date="2023-01-01",
    )
    defaults.update(kwargs)
    return g.verify(**defaults)


def _contra(clauses):
    return ContradictionGuard().verify_consistency(clauses)


def _clause(text, cat, val):
    return Clause(text=text, category=cat, value=val)


class TestStatuteVerificationTrace:
    def test_happy_path_has_four_steps(self):
        assert len(_statute().verification_trace) == 4

    def test_step_types_in_order(self):
        trace = _statute().verification_trace
        assert trace[0].step == STEP_RULE_IDENTIFIED
        assert trace[1].step == STEP_FACT_DERIVED
        assert trace[2].step == STEP_FACT_DERIVED
        assert trace[3].step == STEP_CONCLUSION

    def test_evidence_types_happy_path(self):
        trace = _statute().verification_trace
        assert trace[0].evidence_type == EVIDENCE_PARSED
        assert trace[1].evidence_type == EVIDENCE_DETERMINISTIC
        assert trace[2].evidence_type == EVIDENCE_DETERMINISTIC
        assert trace[3].evidence_type == EVIDENCE_DETERMINISTIC

    def test_conclusion_is_last_step(self):
        assert _statute().verification_trace[-1].step == STEP_CONCLUSION

    def test_conclusion_is_proven(self):
        assert _statute().verification_trace[-1].is_proven() is True

    def test_conclusion_within_statute(self):
        assert "WITHIN STATUTE" in _statute().verification_trace[-1].output

    def test_expired_claim_conclusion_says_expired(self):
        result = _statute(filing_date="2026-01-01")
        assert "EXPIRED" in result.verification_trace[-1].output

    def test_rule_identified_is_parsed_not_deterministic(self):
        trace = _statute().verification_trace
        assert trace[0].evidence_type == EVIDENCE_PARSED
        assert trace[0].evidence_type != EVIDENCE_DETERMINISTIC

    def test_unsupported_jurisdiction_single_unsupported_step(self):
        result = _statute(jurisdiction="MARS")
        assert len(result.verification_trace) == 1
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED
        assert result.verification_trace[0].step == STEP_RULE_IDENTIFIED

    def test_unsupported_claim_type_single_unsupported_step(self):
        result = _statute(claim_type="quantum_litigation")
        assert len(result.verification_trace) == 1
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_all_steps_are_verification_step_instances(self):
        for step in _statute().verification_trace:
            assert isinstance(step, VerificationStep)

    def test_step_inputs_dict_present(self):
        for step in _statute().verification_trace:
            assert isinstance(step.inputs, dict)

    def test_step_output_non_empty(self):
        for step in _statute().verification_trace:
            assert isinstance(step.output, str) and step.output.strip()

    def test_verification_trace_is_list(self):
        assert isinstance(_statute().verification_trace, list)

    def test_parsed_step_is_not_proven(self):
        assert _statute().verification_trace[0].is_proven() is False

    def test_unsupported_step_is_not_proven(self):
        assert _statute(jurisdiction="MARS").verification_trace[0].is_proven() is False

    def test_claim_mismatch_last_step_not_statute_conclusion(self):
        result = _statute(claimed_within_period=False)
        assert result.verified is False
        assert result.verification_trace[-1].output == "CLAIM INCORRECT"
        assert result.verification_trace[-1].is_proven() is True


class TestContradictionVerificationTrace:
    def test_trace_key_present_in_dict(self):
        assert "verification_trace" in _contra(
            [_clause("Max liability 5000", "LIABILITY", 5000)]
        )

    def test_trace_is_list(self):
        assert isinstance(
            _contra([_clause("Max liability 5000", "LIABILITY", 5000)])[
                "verification_trace"
            ],
            list,
        )

    def test_all_trace_entries_are_verification_steps(self):
        r = _contra([_clause("Max liability 5000", "LIABILITY", 5000)])
        for step in r["verification_trace"]:
            assert isinstance(step, VerificationStep)

    def test_contradiction_conclusion_deterministic(self):
        r = _contra(
            [
                _clause("Max liability capped at 5000", "LIABILITY", 5000),
                _clause("Minimum penalty is 10000", "LIABILITY", 10000),
            ]
        )
        assert r["status"] == "contradiction"
        conclusion = r["verification_trace"][-1]
        assert conclusion.step == STEP_CONCLUSION
        assert conclusion.evidence_type == EVIDENCE_DETERMINISTIC
        assert conclusion.is_proven() is True

    def test_consistent_clauses_conclusion_deterministic(self):
        r = _contra(
            [
                _clause("Max liability capped at 10000", "LIABILITY", 10000),
                _clause("Minimum penalty is 1000", "LIABILITY", 1000),
            ]
        )
        assert r["status"] == "consistent"
        conclusion = r["verification_trace"][-1]
        assert conclusion.step == STEP_CONCLUSION
        assert conclusion.evidence_type == EVIDENCE_DETERMINISTIC

    def test_fact_derived_steps_per_clause(self):
        clauses = [
            _clause("Max liability capped at 5000", "LIABILITY", 5000),
            _clause("Max liability capped at 8000", "LIABILITY", 8000),
        ]
        r = _contra(clauses)
        fact_steps = [s for s in r["verification_trace"] if s.step == STEP_FACT_DERIVED]
        assert len(fact_steps) == 2

    def test_fact_derived_evidence_is_deterministic(self):
        r = _contra([_clause("Max liability capped at 5000", "LIABILITY", 5000)])
        fact_steps = [s for s in r["verification_trace"] if s.step == STEP_FACT_DERIVED]
        assert all(s.evidence_type == EVIDENCE_DETERMINISTIC for s in fact_steps)

    def test_rule_identified_is_parsed(self):
        r = _contra([_clause("Max liability capped at 5000", "LIABILITY", 5000)])
        assert r["verification_trace"][0].step == STEP_RULE_IDENTIFIED
        assert r["verification_trace"][0].evidence_type == EVIDENCE_PARSED

    def test_unsupported_category_has_unsupported_step(self):
        r = _contra([_clause("Payment due in 30 days", "PAYMENT", 30)])
        assert r["status"] == "unverifiable"
        assert any(
            s.evidence_type == EVIDENCE_UNSUPPORTED for s in r["verification_trace"]
        )
        assert not any(s.step == STEP_FACT_DERIVED for s in r["verification_trace"])

    def test_empty_clauses_has_unsupported_step(self):
        r = _contra([])
        assert r["status"] == "unverifiable"
        assert r["verification_trace"][0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_partial_coverage_has_ambiguity_noted(self):
        r = _contra(
            [
                _clause("Max liability capped at 5000", "LIABILITY", 5000),
                _clause("Payment due in 30 days", "PAYMENT", 30),
            ]
        )
        assert any(s.step == STEP_AMBIGUITY_NOTED for s in r["verification_trace"])

    def test_conclusion_is_last_step(self):
        r = _contra([_clause("Max liability capped at 5000", "LIABILITY", 5000)])
        assert r["verification_trace"][-1].step == STEP_CONCLUSION

    def test_partial_coverage_conclusion_is_deterministic(self):
        r = _contra(
            [
                _clause("Max liability capped at 5000", "LIABILITY", 5000),
                _clause("Payment due in 30 days", "PAYMENT", 30),
            ]
        )
        assert r["status"] == "partial_coverage"
        assert r["verification_trace"][-1].evidence_type == EVIDENCE_DETERMINISTIC

    def test_message_mentions_only_present_supported_categories(self):
        r = _contra([_clause("Max liability capped at 5000", "LIABILITY", 5000)])
        assert "LIABILITY clauses" in r["message"]
        assert "DURATION and LIABILITY clauses" not in r["message"]


class TestDeadlineVerificationTrace:
    def _verify(self, **kwargs):
        defaults = dict(
            signing_date="2026-01-15",
            term="30 days",
            claimed_deadline="2026-02-14",
        )
        defaults.update(kwargs)
        return DeadlineGuard().verify(**defaults)

    def test_trace_present_and_steps(self):
        trace = self._verify().verification_trace
        assert trace[0].step == STEP_RULE_IDENTIFIED
        assert trace[0].evidence_type == EVIDENCE_PARSED
        assert trace[-1].step == STEP_CONCLUSION
        assert trace[-1].is_proven() is True

    def test_ambiguous_term_unsupported(self):
        result = self._verify(term="a reasonable period")
        assert result.verified is False
        assert len(result.verification_trace) == 1
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_parse_error_unsupported(self):
        result = self._verify(signing_date="not-a-date")
        assert result.verified is False
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_calendar_days_remain_deterministic(self):
        result = self._verify(term="30 days")
        assert result.verification_trace[-1].evidence_type == EVIDENCE_DETERMINISTIC

    def test_business_days_with_invalid_calendar_fail_closed(self):
        # Force an invalid holiday calendar; business-day result must not be proven.
        guard = DeadlineGuard(country="ZZ_NOT_A_COUNTRY")
        assert guard.holiday_calendar_valid is False
        result = guard.verify("2026-01-15", "10 business days", "2026-01-29")
        assert result.verified is False
        assert result.verification_trace[-1].evidence_type == EVIDENCE_UNSUPPORTED
        assert result.verification_trace[-1].is_proven() is False

    def test_business_days_with_valid_calendar_deterministic(self):
        guard = DeadlineGuard(country="US")
        assert guard.holiday_calendar_valid is True
        result = guard.verify("2026-01-15", "10 business days", "2026-01-29")
        assert result.verification_trace[-1].evidence_type == EVIDENCE_DETERMINISTIC


class TestLiabilityVerificationTrace:
    def test_cap_trace_deterministic(self):
        result = LiabilityGuard().verify_cap(5_000_000, 200, 10_000_000)
        trace = result.verification_trace
        assert result.verified is True
        assert trace[-1].step == STEP_CONCLUSION
        assert trace[-1].is_proven() is True
        assert all(isinstance(s, VerificationStep) for s in trace)

    def test_cap_mismatch_conclusion(self):
        result = LiabilityGuard().verify_cap(5_000_000, 200, 15_000_000)
        assert result.verified is False
        assert result.verification_trace[-1].output == "CAP MISMATCH"

    def test_tiered_trace(self):
        result = LiabilityGuard().verify_tiered_liability(
            [{"base": 1_000_000, "percentage": 100}], 1_000_000
        )
        assert result.verification_trace[-1].step == STEP_CONCLUSION

    def test_indemnity_trace(self):
        result = LiabilityGuard().verify_indemnity_limit(100_000, 3, 300_000)
        assert result.verification_trace[-1].is_proven() is True


class TestJurisdictionVerificationTrace:
    def test_trace_present(self):
        result = JurisdictionGuard().verify_choice_of_law(
            parties_countries=["US"],
            governing_law="California",
            forum="California",
        )
        trace = result.verification_trace
        assert trace[0].step == STEP_RULE_IDENTIFIED
        assert trace[0].evidence_type == EVIDENCE_PARSED
        assert trace[-1].step == STEP_CONCLUSION

    def test_conclusion_is_inferred_not_proof(self):
        result = JurisdictionGuard().verify_choice_of_law(
            parties_countries=["US"],
            governing_law="California",
            forum="California",
        )
        assert result.verification_trace[-1].evidence_type == EVIDENCE_INFERRED
        assert result.verification_trace[-1].is_proven() is False

    def test_warnings_emit_ambiguity_step(self):
        result = JurisdictionGuard().verify_choice_of_law(
            parties_countries=["US", "DE"],
            governing_law="California",
            forum="California",
        )
        assert any(
            s.step == STEP_AMBIGUITY_NOTED for s in result.verification_trace
        )

    def test_forum_selection_has_trace(self):
        result = JurisdictionGuard().verify_forum_selection("California")
        assert len(result.verification_trace) >= 2
        assert result.verification_trace[0].step == STEP_RULE_IDENTIFIED
        assert result.verification_trace[-1].step == STEP_CONCLUSION

    def test_forum_selection_warning_is_not_verified(self):
        # Below diversity-jurisdiction threshold -> warning -> must NOT verify.
        result = JurisdictionGuard().verify_forum_selection(
            "California", contract_value=50000
        )
        assert result.verified is False
        assert any(
            s.step == STEP_AMBIGUITY_NOTED for s in result.verification_trace
        )
        assert result.verification_trace[-1].output == "FORUM NOT VERIFIED"

    def test_choice_of_law_empty_parties_fail_closed(self):
        result = JurisdictionGuard().verify_choice_of_law(
            parties_countries=[],
            governing_law="California",
            forum="California",
        )
        assert result.verified is False
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_convention_all_members_deterministic(self):
        result = JurisdictionGuard().check_convention_applicability(
            ["US", "DE"], "CISG"
        )
        assert result.verified is True
        assert result.verification_trace[-1].evidence_type == EVIDENCE_DETERMINISTIC
        assert result.verification_trace[-1].is_proven() is True

    def test_convention_unknown_unsupported(self):
        result = JurisdictionGuard().check_convention_applicability(
            ["US"], "MADE_UP_CONVENTION"
        )
        assert result.verified is False
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED

    def test_convention_partial_membership_has_trace(self):
        result = JurisdictionGuard().check_convention_applicability(
            ["US", "ZZ"], "CISG"
        )
        assert any(
            s.step == STEP_AMBIGUITY_NOTED for s in result.verification_trace
        )

    def test_convention_empty_parties_fail_closed(self):
        result = JurisdictionGuard().check_convention_applicability([], "CISG")
        assert result.verified is False
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED


class TestClauseVerificationTrace:
    def test_heuristic_conclusion_not_proven(self):
        result = ClauseGuard().check_consistency(
            [
                "Seller may terminate with 30 days notice",
                "Buyer may terminate with 60 days notice",
            ]
        )
        trace = result.verification_trace
        assert trace[-1].step == STEP_CONCLUSION
        assert trace[-1].is_proven() is False
        assert trace[-1].evidence_type == EVIDENCE_INFERRED

    def test_limited_coverage_unsupported_step(self):
        result = ClauseGuard().check_consistency(
            ["The sky is blue", "Grass is green"]
        )
        assert result.status == "heuristic_pass_limited"
        assert any(
            s.evidence_type == EVIDENCE_UNSUPPORTED for s in result.verification_trace
        )

    def test_z3_path_is_deterministic(self):
        from z3 import Bool

        p = Bool("p")
        result = ClauseGuard().verify_using_z3([p, p])
        assert result.consistent is True
        assert result.verification_trace[-1].evidence_type == EVIDENCE_DETERMINISTIC
        assert result.verification_trace[-1].is_proven() is True

    def test_z3_empty_unsupported(self):
        result = ClauseGuard().verify_using_z3([])
        assert result.verification_trace[0].evidence_type == EVIDENCE_UNSUPPORTED


class TestCitationVerificationTrace:
    def test_format_valid_authority_unsupported(self):
        result = CitationGuard().verify("Brown v. Board, 347 U.S. 483")
        assert result.format_valid is True
        trace = result.verification_trace
        assert trace[0].evidence_type == EVIDENCE_PARSED
        # Authority can never be proven by format match.
        assert trace[-1].evidence_type == EVIDENCE_UNSUPPORTED
        assert trace[-1].is_proven() is False

    def test_format_invalid_trace(self):
        result = CitationGuard().verify("not a citation")
        assert result.format_valid is False
        assert result.verification_trace[-1].output == "FORMAT INVALID"

    def test_statute_format_trace(self):
        result = CitationGuard().check_statute_citation("42 U.S.C. § 1983")
        assert result.format_valid is True
        assert result.verification_trace[0].evidence_type == EVIDENCE_PARSED


class TestIRACVerificationTrace:
    _VALID = (
        "Issue: Whether the contract is enforceable.\n"
        "Rule: A contract requires offer, acceptance, and consideration.\n"
        "Application: Here, offer and acceptance and consideration are present.\n"
        "Conclusion: The contract is enforceable.\n"
    )

    def test_structure_valid_reasoning_unsupported(self):
        result = IRACGuard().verify(self._VALID)
        assert result.structure_valid is True
        trace = result.verification_trace
        assert trace[0].evidence_type == EVIDENCE_INFERRED
        # Reasoning correctness can never be proven structurally.
        assert trace[-1].evidence_type == EVIDENCE_UNSUPPORTED
        assert trace[-1].is_proven() is False

    def test_missing_section_unsupported(self):
        result = IRACGuard().verify("Issue: something\nRule: a rule")
        assert result.structure_valid is False
        assert result.verification_trace[-1].evidence_type == EVIDENCE_UNSUPPORTED

    def test_no_step_is_deterministic(self):
        result = IRACGuard().verify(self._VALID)
        assert all(
            s.evidence_type != EVIDENCE_DETERMINISTIC
            for s in result.verification_trace
        )
