"""
Phase-3 tests: verification_trace serialization (to_dict / trace_to_dict).
"""

import json
import datetime

from qwed_legal.models import (
    VerificationStep,
    trace_to_dict,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
)
from qwed_legal.guards.statute_guard import StatuteOfLimitationsGuard


def _step(**kwargs):
    defaults = dict(
        step=STEP_CONCLUSION,
        description="desc",
        inputs={"a": 1},
        output="out",
        evidence_type=EVIDENCE_DETERMINISTIC,
    )
    defaults.update(kwargs)
    return VerificationStep(**defaults)


class TestVerificationStepToDict:
    def test_contains_all_fields(self):
        d = _step().to_dict()
        assert set(d.keys()) == {
            "step",
            "description",
            "inputs",
            "output",
            "evidence_type",
            "is_proven",
        }

    def test_is_proven_true_for_deterministic(self):
        assert _step(evidence_type=EVIDENCE_DETERMINISTIC).to_dict()["is_proven"] is True

    def test_is_proven_false_for_parsed(self):
        assert _step(evidence_type=EVIDENCE_PARSED).to_dict()["is_proven"] is False

    def test_json_serializable(self):
        # Should not raise.
        json.dumps(_step().to_dict())

    def test_non_serializable_input_is_stringified(self):
        d = _step(inputs={"date": datetime.date(2020, 1, 1)}).to_dict()
        assert d["inputs"]["date"] == "2020-01-01"
        json.dumps(d)  # still serializable

    def test_nested_inputs_preserved(self):
        d = _step(inputs={"x": {"y": [1, 2, 3]}}).to_dict()
        assert d["inputs"]["x"]["y"] == [1, 2, 3]

    def test_non_string_keys_coerced(self):
        d = _step(inputs={1: "one"}).to_dict()
        assert d["inputs"]["1"] == "one"
        json.dumps(d)


class TestTraceToDict:
    def test_serializes_full_guard_trace(self):
        result = StatuteOfLimitationsGuard().verify(
            claim_type="breach_of_contract",
            jurisdiction="California",
            incident_date="2020-01-01",
            filing_date="2023-01-01",
        )
        serialized = trace_to_dict(result.verification_trace)
        assert isinstance(serialized, list)
        assert all(isinstance(s, dict) for s in serialized)
        # End-to-end: the whole trace must be JSON-serializable.
        json.dumps(serialized)

    def test_empty_trace(self):
        assert trace_to_dict([]) == []

    def test_preserves_order(self):
        steps = [_step(output="first"), _step(output="second")]
        serialized = trace_to_dict(steps)
        assert [s["output"] for s in serialized] == ["first", "second"]
