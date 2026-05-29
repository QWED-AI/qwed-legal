"""
tests/test_verification_trace.py

Phase-1 regression tests for verification_trace on StatuteGuard and ContradictionGuard.
"""

from qwed_legal.guards.statute_guard import StatuteOfLimitationsGuard
from qwed_legal.guards.contradiction_guard import ContradictionGuard, Clause
from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_FACT_DERIVED,
    STEP_AMBIGUITY_NOTED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
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
