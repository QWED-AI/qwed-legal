"""
Tests for the 3-layer LegalDiagnosticResult model (issue #40, Option A
decision from #37) and the RFC 8785 proof_ref binding.
"""

import dataclasses
import json

import pytest

from qwed_legal import (
    Clause,
    CitationGuard,
    ClauseGuard,
    ContradictionGuard,
    DeadlineGuard,
    FairnessGuard,
    IRACGuard,
    JurisdictionGuard,
    LegalDiagnosticResult,
    LegalDiagnosticStatus,
    LiabilityGuard,
    ProvenanceGuard,
    StatuteOfLimitationsGuard,
    canonicalize,
    compute_proof_ref,
    resolve_proof_ref,
)
from qwed_legal.diagnostics import fairness_to_diagnostic


class TestCanonicalize:
    """RFC 8785 (JCS) serialization for the guard evidence subset."""

    def test_scalars(self):
        assert canonicalize("hi") == '"hi"'
        assert canonicalize(42) == "42"
        assert canonicalize(True) == "true"
        assert canonicalize(False) == "false"
        assert canonicalize(None) == "null"

    def test_string_escaping(self):
        assert canonicalize('say "hi"') == '"say \\"hi\\""'
        assert canonicalize("back\\slash") == '"back\\\\slash"'
        assert canonicalize("line\nbreak") == '"line\\nbreak"'
        assert canonicalize("\x01") == '"\\u0001"'

    def test_object_keys_sorted_by_utf16_code_units(self):
        # For BMP characters UTF-16 code-unit order equals code-point
        # order; the sort key (utf-16-be bytes) is deterministic.
        assert canonicalize({"b": 1, "a": 2}) == '{"a":2,"b":1}'
        assert canonicalize({"\u00e9": 1, "z": 2}) == '{"z":2,"\u00e9":1}'

    def test_nested_arrays_and_objects(self):
        value = {"trace": [{"step": 1}, {"step": 2}], "ok": True}
        assert canonicalize(value) == '{"ok":true,"trace":[{"step":1},{"step":2}]}'

    def test_float_fails_closed(self):
        with pytest.raises(ValueError):
            canonicalize(1.5)
        with pytest.raises(ValueError):
            canonicalize({"amount": 2.5})

    def test_unsupported_type_fails_closed(self):
        with pytest.raises(ValueError):
            canonicalize(object())


class TestProofRef:
    """proof_ref binds the verdict to the evidence: any mutation is
    detectable via resolve_proof_ref (issue #40)."""

    def setup_method(self):
        self.evidence = {
            "claim_inputs": {"term": "30 days", "signing_date": "2026-01-15"},
            "trace": [
                {"step": "RULE_IDENTIFIED", "evidence_type": "PARSED"},
                {"step": "CONCLUSION", "evidence_type": "DETERMINISTIC"},
            ],
            "result": {"verified": True},
        }
        self.ref = compute_proof_ref(self.evidence)

    def test_ref_format(self):
        assert self.ref.startswith("sha256:")
        assert len(self.ref) == len("sha256:") + 64

    def test_resolve_round_trip(self):
        assert resolve_proof_ref(self.ref, self.evidence) is True

    def test_trace_mutation_detected(self):
        tampered = {
            **self.evidence,
            "trace": [
                {"step": "RULE_IDENTIFIED", "evidence_type": "HEURISTIC"},
                {"step": "CONCLUSION", "evidence_type": "DETERMINISTIC"},
            ],
        }
        assert resolve_proof_ref(self.ref, tampered) is False

    def test_claim_mutation_detected(self):
        tampered = {
            **self.evidence,
            "claim_inputs": {"term": "300 days", "signing_date": "2026-01-15"},
        }
        assert resolve_proof_ref(self.ref, tampered) is False

    def test_resolve_fails_closed_on_uncanonicalizable(self):
        assert resolve_proof_ref(self.ref, {"bad": 1.5}) is False
        assert resolve_proof_ref(None, self.evidence) is False


class TestLegalDiagnosticResultContract:
    """Structural enforcement: VERIFIED requires proof_ref; non-VERIFIED
    rejects it; frozen dataclass prevents post-construction mutation."""

    def test_verified_requires_proof_ref(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult(
                status=LegalDiagnosticStatus.VERIFIED,
                agent_message="msg",
            )

    def test_non_verified_rejects_proof_ref(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult(
                status=LegalDiagnosticStatus.UNVERIFIABLE,
                agent_message="msg",
                proof_ref="sha256:" + "0" * 64,
            )

    def test_empty_agent_message_rejected(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult(
                status=LegalDiagnosticStatus.UNVERIFIABLE,
                agent_message="  ",
            )

    def test_result_is_frozen(self):
        result = LegalDiagnosticResult.unverifiable(agent_message="msg")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.agent_message = "tampered"

    def test_authority_bit(self):
        verified = LegalDiagnosticResult.verified(
            agent_message="msg",
            developer_fields={},
            evidence={"claim": "x"},
        )
        assert verified.is_authoritative is True
        assert verified.is_verified is True
        blocked = LegalDiagnosticResult.blocked(agent_message="msg")
        assert blocked.is_authoritative is False
        assert blocked.is_fail_closed is True


class TestVerificationStepFrozen:
    """Issue #40 / audit P1-L3: evidence steps are immutable after
    construction — the DETERMINISTIC→HEURISTIC flip is now impossible."""

    def test_step_is_frozen(self):
        from qwed_legal.models import (
            EVIDENCE_DETERMINISTIC,
            EVIDENCE_HEURISTIC,
            VerificationStep,
        )

        step = VerificationStep(
            step="CONCLUSION",
            description="d",
            inputs={},
            output="out",
            evidence_type=EVIDENCE_DETERMINISTIC,
        )
        assert step.is_proven() is True
        with pytest.raises(dataclasses.FrozenInstanceError):
            step.evidence_type = EVIDENCE_HEURISTIC
        with pytest.raises(dataclasses.FrozenInstanceError):
            step.output = "rewritten"


class TestGuardToDiagnostic:
    """Per-guard to_diagnostic adapters map outcomes onto the ecosystem
    tri-state with the full verification_trace as Layer-2 payload."""

    def test_deadline_verified_is_authoritative(self):
        result = DeadlineGuard().verify("2026-01-01", "30 days", "2026-01-31")
        diagnostic = result.to_diagnostic(
            claim_inputs={
                "signing_date": "2026-01-01",
                "term": "30 days",
                "claimed_deadline": "2026-01-31",
            }
        )
        assert diagnostic.status is LegalDiagnosticStatus.VERIFIED
        assert diagnostic.is_authoritative is True
        assert diagnostic.proof_ref.startswith("sha256:")
        trace = diagnostic.developer_fields["verification_trace"]
        assert len(trace) == 4  # full per-step trace preserved
        # Round-trip: the retained evidence resolves the proof_ref.
        assert resolve_proof_ref(diagnostic.proof_ref, {
            "claim_inputs": diagnostic.developer_fields["claim_inputs"],
            "trace": diagnostic.developer_fields["verification_trace"],
            "result": diagnostic.developer_fields["result"],
        }) is True

    def test_deadline_mismatch_is_blocked(self):
        result = DeadlineGuard().verify("2026-01-01", "30 days", "2026-03-31")
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.BLOCKED
        assert diagnostic.is_authoritative is False

    def test_deadline_ambiguous_is_unverifiable(self):
        result = DeadlineGuard().verify("2026-01-01", "promptly", "2026-01-31")
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_statute_computed_only_is_unverifiable(self):
        result = StatuteOfLimitationsGuard().verify(
            claim_type="negligence",
            jurisdiction="Texas",
            incident_date="2024-01-01",
            filing_date="2024-06-01",
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_statute_claim_verified_is_authoritative(self):
        result = StatuteOfLimitationsGuard().verify(
            claim_type="negligence",
            jurisdiction="Texas",
            incident_date="2024-01-01",
            filing_date="2024-06-01",
            claimed_within_period=True,
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.VERIFIED

    def test_statute_claim_incorrect_is_blocked(self):
        result = StatuteOfLimitationsGuard().verify(
            claim_type="negligence",
            jurisdiction="Texas",
            incident_date="2024-01-01",
            filing_date="2024-06-01",
            claimed_within_period=False,
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.BLOCKED

    def test_citation_is_never_authoritative(self):
        result = CitationGuard().check_statute_citation("42 U.S.C. § 1983")
        diagnostic = result.to_diagnostic()
        # Authority is never verifiable — even format-valid cites are
        # UNVERIFIABLE, never VERIFIED.
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert diagnostic.is_authoritative is False

    def test_clause_contradiction_is_blocked(self):
        result = ClauseGuard().check_consistency(
            [
                "Seller may terminate with 30 days notice",
                "Neither party may terminate before 90 days",
            ]
        )
        diagnostic = result.to_diagnostic()
        # ClauseGuard is heuristic: a detected contradiction is BLOCKED,
        # but a heuristic pass would be UNVERIFIABLE, never VERIFIED.
        assert diagnostic.status is LegalDiagnosticStatus.BLOCKED

    def test_clause_heuristic_pass_is_never_verified(self):
        result = ClauseGuard().check_consistency(
            ["Seller may terminate with 30 days notice"]
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert diagnostic.is_authoritative is False

    def test_provenance_self_declared_is_never_authoritative(self):
        guard = ProvenanceGuard()
        content = "AI-generated legal memo."
        record = guard.generate_provenance(content, "gpt-x")
        result = guard.verify_provenance(
            content,
            {
                "content_hash": record.content_hash,
                "model_id": "gpt-x",
                "generation_timestamp": record.generation_timestamp,
            },
        )
        diagnostic = guard.to_diagnostic(result)
        # Self-declared provenance attests internal consistency only —
        # never authority (issue #42/#45).
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert diagnostic.is_authoritative is False
        assert (
            diagnostic.developer_fields["assurance"] == "SELF_DECLARED"
        )

    def test_provenance_tamper_is_blocked(self):
        guard = ProvenanceGuard()
        result = guard.verify_provenance(
            "tampered content",
            {
                "content_hash": "0" * 64,
                "model_id": "gpt-x",
                "generation_timestamp": "2026-01-01T00:00:00+00:00",
            },
        )
        diagnostic = guard.to_diagnostic(result)
        assert diagnostic.status is LegalDiagnosticStatus.BLOCKED


class TestDiagnosticsEdgePaths:
    """Coverage for error paths and adapters (Sonar new-code coverage)."""

    def test_from_dict_round_trip(self):
        diagnostic = LegalDiagnosticResult.unverifiable(
            agent_message="unverifiable message",
            developer_fields={"guard": "deadline"},
        )
        restored = LegalDiagnosticResult.from_dict(diagnostic.to_dict())
        assert restored.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert restored.agent_message == "unverifiable message"

    def test_from_dict_rejects_bad_status(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult.from_dict({"status": "MAYBE"})

    def test_from_dict_rejects_missing_agent_message(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult.from_dict({"status": "UNVERIFIABLE"})

    def test_from_dict_rejects_bad_developer_fields(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult.from_dict(
                {"status": "UNVERIFIABLE", "agent_message": "m", "developer_fields": []}
            )

    def test_proof_ref_format_enforced(self):
        with pytest.raises(ValueError):
            LegalDiagnosticResult(
                status=LegalDiagnosticStatus.VERIFIED,
                agent_message="msg",
                proof_ref="not-a-hash",
            )

    def test_blocked_constructor(self):
        blocked = LegalDiagnosticResult.blocked(
            agent_message="blocked", developer_fields={"guard": "x"}
        )
        assert blocked.is_fail_closed is True
        assert blocked.proof_ref is None

    def test_safe_integer_boundary(self):
        """Integers within the IEEE 754 safe range hash; outside it the
        canonicalizer fails closed (PR #48 review, Greptile)."""
        edge = 2**53
        assert canonicalize(edge) == str(edge)
        with pytest.raises(ValueError):
            canonicalize(edge + 1)

    def test_lone_surrogate_rejected(self):
        with pytest.raises(ValueError):
            canonicalize("bad \ud800 surrogate")

    def test_set_evidence_is_order_deterministic(self):
        """Equivalent sets hash identically regardless of iteration
        order (PR #48 review)."""
        a = compute_proof_ref({"items": {"b", "a", "c"}})
        b = compute_proof_ref({"items": {"c", "b", "a"}})
        assert a == b

    def test_type_tagged_stringification_distinguishes_types(self):
        """float 1.0 and string '1.0' must not collide in proof data
        (PR #48 review)."""
        assert compute_proof_ref({"v": 1.0}) != compute_proof_ref({"v": "1.0"})

    def test_from_dict_round_trip_authorized(self):
        verified = LegalDiagnosticResult.verified(
            agent_message="proven",
            developer_fields={"guard": "deadline"},
            evidence={"claim": "inputs"},
        )
        restored = LegalDiagnosticResult.from_dict(verified.to_dict())
        assert restored.status is LegalDiagnosticStatus.VERIFIED
        assert restored.proof_ref == verified.proof_ref

    def test_frozen_developer_fields_block_mutation(self):
        diagnostic = LegalDiagnosticResult.unverifiable(
            agent_message="m", developer_fields={"guard": "deadline"}
        )
        with pytest.raises(TypeError):
            diagnostic.developer_fields["guard"] = "tampered"

    def test_frozen_trace_blocks_append(self):
        result = DeadlineGuard().verify("2026-01-01", "30 days", "2026-01-31")
        diagnostic = result.to_diagnostic()
        trace = diagnostic.developer_fields["verification_trace"]
        with pytest.raises(AttributeError):
            trace.append("forged")

    def test_step_inputs_block_mutation(self):
        from qwed_legal.models import (
            EVIDENCE_DETERMINISTIC,
            VerificationStep,
        )

        step = VerificationStep(
            step="CONCLUSION",
            description="d",
            inputs={"z3_result": "sat"},
            output="out",
            evidence_type=EVIDENCE_DETERMINISTIC,
        )
        with pytest.raises(TypeError):
            step.inputs["z3_result"] = "unsat"

    def test_result_trace_is_immutable_sequence(self):
        result = DeadlineGuard().verify("2026-01-01", "30 days", "2026-01-31")
        with pytest.raises(AttributeError):
            result.verification_trace.append("forged")

    def test_contradiction_adapter_verified(self):
        guard = ContradictionGuard()
        clauses = [
            Clause(text="Term is exactly 12 months.", category="DURATION", value=12),
        ]
        result = guard.verify_consistency(clauses)
        diagnostic = ContradictionGuard.to_diagnostic(result, clauses)
        assert diagnostic.status is LegalDiagnosticStatus.VERIFIED
        assert diagnostic.is_authoritative is True
        # Evidence reconstruction from developer_fields alone.
        assert resolve_proof_ref(diagnostic.proof_ref, {
            "claim_inputs": diagnostic.developer_fields["claim_inputs"],
            "trace": diagnostic.developer_fields["verification_trace"],
            "result": diagnostic.developer_fields["result"],
        }) is True

    def test_contradiction_adapter_blocked(self):
        guard = ContradictionGuard()
        result = guard.verify_consistency(
            [
                Clause(text="Term is exactly 12 months.", category="DURATION", value=12),
                Clause(text="Term is maximum 2 months.", category="DURATION", value=2),
            ]
        )
        diagnostic = ContradictionGuard.to_diagnostic(result)
        assert diagnostic.status is LegalDiagnosticStatus.BLOCKED

    def test_fairness_adapter_json_encodable(self):
        from qwed_legal.diagnostics import fairness_to_diagnostic

        class _MockLLM:
            def generate(self, prompt):
                return "approved"

        guard = FairnessGuard(llm_client=_MockLLM())
        result = guard.verify_decision_fairness(
            original_prompt="Should we approve the application?",
            original_decision="approved",
            protected_attribute_swap={"John": "Jane"},
        )
        diagnostic = fairness_to_diagnostic(result)
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        # The payload must be JSON-encodable (steps serialized).
        json.dumps(diagnostic.to_dict())

    def test_irac_diagnostic_mapping(self):

        result = IRACGuard().verify(
            "Issue: was X? Rule: r. Application: a. Conclusion: c."
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status in (
            LegalDiagnosticStatus.UNVERIFIABLE,
            LegalDiagnosticStatus.BLOCKED,
        )
        assert diagnostic.is_authoritative is False

    def test_jurisdiction_diagnostic_mapping(self):

        result = JurisdictionGuard().verify_choice_of_law(
            parties_countries=["United States", "United States"],
            governing_law="California",
        )
        diagnostic = result.to_diagnostic()
        # PARSED/INFERRED evidence can never back VERIFIED (CodeAnt
        # Critical): a passing jurisdiction check is non-authoritative.
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        assert diagnostic.is_authoritative is False

    def test_tiered_liability_diagnostic_mapping(self):
        from qwed_legal import LiabilityGuard

        result = LiabilityGuard().verify_tiered_liability(
            [{"base": 1_000_000, "percentage": 100}], 1_000_000
        )
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.VERIFIED

    def test_liability_unverifiable_mapping(self):
        result = LiabilityGuard().verify_cap(float("inf"), 200, 1_000_000)
        diagnostic = result.to_diagnostic()
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE

    def test_fairness_adapter(self):
        from qwed_legal import FairnessGuard

        class _MockLLM:
            def generate(self, prompt):
                return "approved"

        guard = FairnessGuard(llm_client=_MockLLM())
        result = guard.verify_decision_fairness(
            original_prompt="Should we approve the application?",
            original_decision="approved",
            protected_attribute_swap={"John": "Jane"},
        )
        diagnostic = fairness_to_diagnostic(result)
        assert diagnostic.status is LegalDiagnosticStatus.UNVERIFIABLE
        # The payload must be JSON-encodable (steps serialized).
        import json

        json.dumps(diagnostic.to_dict())

