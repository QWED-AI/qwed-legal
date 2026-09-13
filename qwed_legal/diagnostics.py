"""
QWED-Legal Structured Verification Diagnostics.

Implements the 3-layer LegalDiagnosticResult model (Issues #37 decision /
#40) — Option A hybrid: the ecosystem DiagnosticResult contract layered
ON TOP of the per-step verification_trace, which is preserved verbatim
as the Layer-2 evidence payload.

    Layer 1 — Agent-Safe Diagnostics
        agent_message: str
        Agent/model-facing summary. The guard's existing message — the
        verification_trace vocabulary already excludes rule IDs and
        detection logic.

    Layer 2 — Developer Diagnostics
        developer_fields: dict
        Structured developer evidence: claim_inputs, verification_trace
        (the full per-step record with evidence_type taxonomy), result
        snapshot, and guard-specific fields.

    Layer 3 — Proof Diagnostics
        proof_ref: Optional[str]
        SHA-256 over the RFC 8785 canonical JSON of the proof evidence
        (claim inputs + full trace). Present only when status == VERIFIED.
        None for UNVERIFIABLE / BLOCKED — this is the authority bit.

Constraints (non-negotiable, per the #37 decision):
- Diagnostics are NOT explainability — no confidence scores, no
  chain-of-thought.
- All diagnostic fields must originate from verification results, traces,
  or claim inputs — never from model output directly.
- VERIFIED requires proof_ref is not None — structurally enforced.
- Non-VERIFIED rejects proof_ref — structurally enforced.
- Frozen dataclass — prevents post-construction mutation.
- Self-declared attestations (ProvenanceGuard) never map to VERIFIED —
  a passing provenance check attests internal consistency of a caller-
  supplied declaration, not external assurance (issue #42/#45).

This module does NOT depend on any other QWED package — qwed-legal is a
separate package. The canonicalization implements RFC 8785 (JCS) for the
JSON data-model subset the guards emit (str/int/bool/null/list/dict);
floats and other types fail closed rather than being hashed loosely.
"""

from __future__ import annotations

from collections.abc import Mapping

import dataclasses
import hashlib
import re
import types
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class LegalDiagnosticStatus(str, Enum):
    """Legal verification diagnostic status.

    Three states only — the richer distinctions live in
    developer_fields.verification_trace (the 5-level evidence_type
    taxonomy) and in the guards' own status fields, not in the
    ecosystem-facing status.

    VERIFIED:
        The legal claim was compared against deterministic computation
        and matches. proof_ref MUST be present. Downstream gates MAY
        admit for control flow.

    UNVERIFIABLE:
        The legal claim could not be proven. proof_ref MUST be None.
        Reasons: no claim supplied (computed-only mode), ambiguous or
        uninterpretable input, self-declared attestation, heuristic
        pass, citation authority not verifiable.
        Downstream gates MUST NOT admit for control flow.

    BLOCKED:
        The guard deterministically rejected the claim: contradiction,
        mismatch, tampered evidence, format-invalid, impossible
        timeline. proof_ref MUST be None.
        Downstream gates MUST NOT admit for control flow.
    """
    VERIFIED = "VERIFIED"
    UNVERIFIABLE = "UNVERIFIABLE"
    BLOCKED = "BLOCKED"


def _rfc8785_string(value: str) -> str:
    """Serialize a string per RFC 8785 §3.2.2.2 (ECMAScript escaping).

    Lone surrogates are rejected — they cannot be encoded as UTF-8 and
    would make the proof reference unresolvable (PR #48 review).
    """
    for ch in value:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            raise ValueError(
                "canonicalize: string contains a lone surrogate — "
                "unencodable as UTF-8 (fail-closed)."
            )
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif code >= 0x20:
            out.append(ch)
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(f"\\u{code:04x}")
    out.append('"')
    return "".join(out)


def canonicalize(value: Any) -> str:
    """RFC 8785 (JSON Canonicalization Scheme) serialization.

    Supports the JSON data-model subset the guards emit: str, int,
    bool, None, list, dict (str keys). Object keys are sorted by their
    UTF-16 code units (RFC 8785 §3.2.3); strings are escaped per
    §3.2.2.2; there is no insignificant whitespace.

    Floats and any other type raise ValueError — fail closed rather
    than hashing a loosely-specified serialization (the guards emit no
    floats in proof evidence).
    """
    if isinstance(value, str):
        return _rfc8785_string(value)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        # RFC 8785 number serialization follows ECMAScript: integers
        # outside the IEEE 754 safe range are not interoperable — an
        # ECMAScript consumer would serialize them differently, so the
        # proof reference would not resolve cross-language (PR #48
        # review, Greptile).
        if not (-(2**53) <= value <= 2**53):
            raise ValueError(
                "canonicalize: integer outside the IEEE 754 safe range "
                "(-2^53..2^53) — fail-closed."
            )
        return str(value)
    if isinstance(value, float):
        raise ValueError(
            "canonicalize: float values are not supported — "
            "proof evidence must use exact numeric types (fail-closed)."
        )
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonicalize(item) for item in value) + "]"
    if isinstance(value, Mapping):
        # Includes the read-only mappings produced by _deep_freeze —
        # resolution must work directly on the retained frozen evidence.
        if not all(isinstance(key, str) for key in value):
            raise ValueError(
                "canonicalize: object keys must be strings (fail-closed)."
            )
        # RFC 8785 §3.2.3: order keys by their UTF-16 code units.
        ordered = sorted(value.keys(), key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(
            f"{_rfc8785_string(key)}:{canonicalize(value[key])}" for key in ordered
        ) + "}"
    raise ValueError(
        f"canonicalize: unsupported type {type(value).__name__} — "
        "proof evidence must be str/int/bool/None/list/dict (fail-closed)."
    )


def compute_proof_ref(evidence: Dict[str, Any]) -> str:
    """Compute the proof reference hash from the proof evidence.

    The proof_ref binds the verdict (status=VERIFIED) to the specific
    evidence that justified it: the claim inputs and the full per-step
    verification_trace (including evidence types). If either changes,
    the hash changes — verdict/evidence drift is structurally detectable
    via resolve_proof_ref.

    Args:
        evidence: The proof artifact dict (claim inputs + trace + result
            snapshot). Must canonicalize under RFC 8785.

    Returns:
        sha256-prefixed hex digest string, e.g. "sha256:abcdef...".

    Raises:
        ValueError: If evidence cannot be canonicalized (fail-closed).
    """
    # Coerce the evidence into the canonicalization-supported subset
    # first (sets sorted, non-primitives type-tagged) so callers never
    # hash a loosely-specified structure.
    digest = hashlib.sha256(canonicalize(_json_safe(evidence)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def resolve_proof_ref(proof_ref: str, evidence: Dict[str, Any]) -> bool:
    """Verify a proof_ref against evidence — recomputes and compares.

    A consumer that retained the evidence dict can detect any
    post-issuance tampering (trace mutation, claim alteration,
    evidence-type flips) by recomputing the hash.

    Args:
        proof_ref: The "sha256:..." reference to verify.
        evidence: The retained proof artifact dict.

    Returns:
        True when the recomputed hash matches; False on any mismatch or
        canonicalization failure (fail-closed).
    """
    if not isinstance(proof_ref, str):
        return False
    try:
        return compute_proof_ref(evidence) == proof_ref
    except ValueError:
        return False


_PROOF_REF_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze containers: mappings become read-only proxies,
    lists/tuples become tuples, sets/frozensets become sorted tuples.
    Deep-freezing the retained evidence prevents in-place mutation that
    would decouple it from its proof_ref (PR #48 review) — including
    nested tuples, sets, and frozensets (PR #48 review R3: the earlier
    version did not recurse into them)."""
    if isinstance(value, Mapping):
        return types.MappingProxyType(
            {k: _deep_freeze(v) for k, v in value.items()}
        )
    if isinstance(value, (set, frozenset)):
        # Sets have no stable iteration order across hash seeds — sort by
        # a deterministic serialized representation before freezing.
        return tuple(_deep_freeze(v) for v in sorted(value, key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class LegalDiagnosticResult:
    """Unified 3-layer legal verification diagnostic result (issue #40).

    Three layers:
        1. agent_message    — Layer 1 (agent-safe, no internals)
        2. developer_fields  — Layer 2 (structured developer evidence;
           carries the full verification_trace)
        3. proof_ref         — Layer 3 (RFC 8785 canonical-JSON proof hash)

    Authority contract:
        proof_ref is not None  → authoritative, admissible for control flow
        proof_ref is None      → non-authoritative, NOT admissible for
        control flow

    Constraints enforced in __post_init__:
        - status == VERIFIED  requires proof_ref is not None
        - status == UNVERIFIABLE or BLOCKED  requires proof_ref is None
        - agent_message must be non-empty
    """

    status: LegalDiagnosticStatus
    agent_message: str
    developer_fields: Dict[str, Any] = field(default_factory=dict)
    proof_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LegalDiagnosticStatus):
            valid = ", ".join(s.value for s in LegalDiagnosticStatus)
            raise ValueError(f"status must be a LegalDiagnosticStatus ({valid})")

        if not isinstance(self.agent_message, str) or not self.agent_message.strip():
            raise ValueError(
                "agent_message must be a non-empty string — "
                "Layer 1 diagnostics are mandatory"
            )

        if not isinstance(self.developer_fields, dict):
            raise ValueError("developer_fields must be a dict")

        if self.status is LegalDiagnosticStatus.VERIFIED and not self.proof_ref:
            raise ValueError(
                "VERIFIED status requires proof_ref is not None and non-empty — "
                "a legal claim cannot be marked proven without a proof artifact "
                "hash. Use UNVERIFIABLE if no proof was established."
            )

        if self.status is not LegalDiagnosticStatus.VERIFIED and self.proof_ref is not None:
            raise ValueError(
                f"{self.status.value} status requires proof_ref is None — "
                "non-VERIFIED states are non-authoritative by construction."
            )

        if self.proof_ref is not None and not _PROOF_REF_RE.fullmatch(self.proof_ref):
            raise ValueError(
                "proof_ref must be 'sha256:' followed by 64 hex characters — "
                "forged or malformed references are rejected at construction."
            )

        # Deep-freeze the evidence container: frozen=True does not cover
        # nested dicts/lists, and post-hash mutation of the retained
        # evidence would decouple it from the proof_ref (PR #48 review).
        object.__setattr__(self, "developer_fields", _deep_freeze(self.developer_fields))

    @property
    def is_verified(self) -> bool:
        """True only when status is VERIFIED (implies proof_ref present)."""
        return self.status is LegalDiagnosticStatus.VERIFIED

    @property
    def is_authoritative(self) -> bool:
        """Authority bit — True when proof_ref is present (admissible for
        control flow)."""
        return self.proof_ref is not None

    @property
    def is_fail_closed(self) -> bool:
        """True when status is UNVERIFIABLE or BLOCKED (non-pass)."""
        return self.status in (
            LegalDiagnosticStatus.UNVERIFIABLE,
            LegalDiagnosticStatus.BLOCKED,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for API/SDK responses (frozen containers are
        converted back to plain dicts/lists)."""
        def _plain(value: Any) -> Any:
            if isinstance(value, types.MappingProxyType):
                return {k: _plain(v) for k, v in value.items()}
            if isinstance(value, dict):
                return {k: _plain(v) for k, v in value.items()}
            if isinstance(value, (list, tuple, set, frozenset)):
                return [_plain(v) for v in value]
            return value

        return {
            "status": self.status.value,
            "agent_message": self.agent_message,
            "developer_fields": _plain(self.developer_fields),
            "proof_ref": self.proof_ref,
            "is_authoritative": self.is_authoritative,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LegalDiagnosticResult":
        """Deserialize from dict."""
        status = data.get("status", "UNVERIFIABLE")
        if isinstance(status, str):
            try:
                status = LegalDiagnosticStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in LegalDiagnosticStatus)
                raise ValueError(
                    f"from_dict: invalid status {status!r} — "
                    f"must be one of: {valid}."
                ) from None
        elif not isinstance(status, LegalDiagnosticStatus):
            valid = ", ".join(s.value for s in LegalDiagnosticStatus)
            raise ValueError(
                f"from_dict: invalid status type {type(status).__name__} — "
                f"must be one of: {valid}."
            )

        agent_message = data.get("agent_message")
        if not isinstance(agent_message, str) or not agent_message.strip():
            raise ValueError(
                "from_dict: 'agent_message' is missing or empty — "
                "Layer 1 diagnostics are mandatory."
            )

        developer_fields = data.get("developer_fields", {})
        if not isinstance(developer_fields, dict):
            raise ValueError("from_dict: 'developer_fields' must be a dict.")

        return cls(
            status=status,
            agent_message=agent_message,
            developer_fields=developer_fields,
            proof_ref=data.get("proof_ref"),
        )

    @classmethod
    def verified(
        cls,
        agent_message: str,
        developer_fields: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> "LegalDiagnosticResult":
        """Construct a VERIFIED result with proof_ref computed from evidence."""
        return cls(
            status=LegalDiagnosticStatus.VERIFIED,
            agent_message=agent_message,
            developer_fields=developer_fields,
            proof_ref=compute_proof_ref(evidence),
        )

    @classmethod
    def unverifiable(
        cls,
        agent_message: str,
        developer_fields: Optional[Dict[str, Any]] = None,
    ) -> "LegalDiagnosticResult":
        """Construct an UNVERIFIABLE result (non-pass, non-authoritative)."""
        return cls(
            status=LegalDiagnosticStatus.UNVERIFIABLE,
            agent_message=agent_message,
            developer_fields=developer_fields or {},
            proof_ref=None,
        )

    @classmethod
    def blocked(
        cls,
        agent_message: str,
        developer_fields: Optional[Dict[str, Any]] = None,
    ) -> "LegalDiagnosticResult":
        """Construct a BLOCKED result (claim deterministically rejected)."""
        return cls(
            status=LegalDiagnosticStatus.BLOCKED,
            agent_message=agent_message,
            developer_fields=developer_fields or {},
            proof_ref=None,
        )


class LegalDiagnosticsMixin:
    """Mixin for guard result dataclasses: 3-layer DiagnosticResult adapter.

    Result classes inheriting this mixin gain ``to_diagnostic(claim_inputs)``,
    which builds the RFC 8785 proof evidence from (claim inputs, full
    verification_trace, result snapshot) and maps the guard outcome onto the
    ecosystem tri-state via the class's ``_diagnostic_status()`` hook.

    Subclasses declare ``_diagnostic_agent_message()`` when the guard
    message needs adjustment; the default uses ``self.message``.
    """

    def _freeze_evidence_fields(self, *names: str) -> None:
        """Deep-freeze the named evidence fields (lists -> tuples, dicts
        -> read-only mappings) so post-construction mutation cannot
        decouple retained evidence from its proof_ref (PR #48 review)."""
        for name in names:
            # __dict__ access instead of dynamic getattr — the QWED
            # DYNAMIC_EXECUTION_BOUNDARY rule flags getattr with variable
            # names, and these field names are compile-time constants.
            object.__setattr__(self, name, _deep_freeze(self.__dict__[name]))

    def _diagnostic_status(self) -> LegalDiagnosticStatus:
        """Map the guard outcome onto the ecosystem tri-state. Default:
        verified=True → VERIFIED, everything else → UNVERIFIABLE — except
        that an empty agent_message can never be VERIFIED (Layer 1 is
        mandatory and LegalDiagnosticResult would reject it; Sentry R3).
        Subclasses override for guard-specific mappings."""
        if self.__dict__.get("verified", False) and str(
            self.__dict__.get("message", "")
        ).strip():
            return LegalDiagnosticStatus.VERIFIED
        return LegalDiagnosticStatus.UNVERIFIABLE

    def _diagnostic_agent_message(self) -> str:
        return self.__dict__.get("message", "")

    def to_diagnostic(
        self, claim_inputs: Optional[Dict[str, Any]] = None
    ) -> "LegalDiagnosticResult":
        """Build the 3-layer LegalDiagnosticResult for this guard result.

        The proof evidence binds (claim inputs, full verification_trace,
        result snapshot) — any post-issuance mutation is detectable via
        ``resolve_proof_ref`` (issue #40).
        """
        from qwed_legal.models import trace_to_dict

        # __dict__ access instead of dynamic getattr — see
        # _freeze_evidence_fields (QWED DYNAMIC_EXECUTION_BOUNDARY rule).
        result_snapshot = _json_safe(
            {
                f.name: _json_safe(self.__dict__[f.name])
                for f in dataclasses.fields(self)
                if f.name != "verification_trace"
            }
        )
        # trace_to_dict passes floats through (models._json_safe is
        # float-tolerant); the canonicalizer is not — coerce the trace
        # into the hashable subset as well (floats stringify
        # deterministically).
        trace = _json_safe(
            trace_to_dict(self.__dict__.get("verification_trace", []))
        )
        claim = _json_safe(claim_inputs or {})
        evidence = {
            "claim_inputs": claim,
            "trace": trace,
            "result": result_snapshot,
        }
        developer_fields = {
            "claim_inputs": claim,
            "verification_trace": trace,
            "result": result_snapshot,
        }
        status = self._diagnostic_status()
        agent_message = self._diagnostic_agent_message()
        if status is LegalDiagnosticStatus.VERIFIED and not str(agent_message).strip():
            # Layer 1 is mandatory — an empty agent_message can never back
            # a VERIFIED verdict (PR #48 review, Sentry R3).
            status = LegalDiagnosticStatus.UNVERIFIABLE
        if not str(agent_message).strip():
            agent_message = "Verification completed without an agent-facing message."
        if status is LegalDiagnosticStatus.VERIFIED:
            return LegalDiagnosticResult.verified(
                agent_message=agent_message,
                developer_fields=developer_fields,
                evidence=evidence,
            )
        if status is LegalDiagnosticStatus.BLOCKED:
            return LegalDiagnosticResult.blocked(
                agent_message=agent_message,
                developer_fields=developer_fields,
            )
        return LegalDiagnosticResult.unverifiable(
            agent_message=agent_message,
            developer_fields=developer_fields,
        )


def _json_safe(value: Any) -> Any:
    """Coerce a value into the canonicalization-supported subset without
    losing data (mirrors models._json_safe; kept local to avoid a
    circular import).

    Determinism guarantees (PR #48 review): sets are sorted by their
    serialized representation so equivalent evidence hashes identically,
    and non-primitive values are type-tagged when stringified so distinct
    evidence types (1.0 vs "1.0") never collide.
    """
    if isinstance(value, Mapping):
        # Includes the read-only mappings produced by _deep_freeze.
        # Non-string keys are rejected, not coerced: str(k) would collapse
        # distinct evidence keys ({1: "a"} vs {"1": "a"}) and silently
        # drop values when both are present (PR #48 review, CodeRabbit).
        if not all(isinstance(k, str) for k in value):
            raise ValueError(
                "_json_safe: proof evidence object keys must be strings "
                "(fail-closed — coercion would collapse distinct keys)."
            )
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_json_safe(v) for v in value),
            key=lambda item: canonicalize(item) if not isinstance(item, (dict, list)) else str(item),
        )
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    # Everything else (float, Decimal, datetime, objects) type-tags its
    # stringified form so distinct evidence types never collide.
    return f"{type(value).__name__}:{value}"


def deep_freeze_evidence(value: Any) -> Any:
    """Public wrapper around the recursive evidence freezer."""
    return _deep_freeze(value)


def fairness_to_diagnostic(result: Dict[str, Any]) -> LegalDiagnosticResult:
    """Convert a FairnessGuard.verify_decision_fairness() result dict to
    the 3-layer LegalDiagnosticResult (issue #40).

    Lives here rather than on FairnessGuard so that guard module stays
    untouched (its pre-existing scanner findings must not be dragged
    into a release-blocking state by unrelated edits). FairnessGuard can
    NEVER return verified=True — legal fairness is not deterministically
    provable — so every outcome maps to UNVERIFIABLE. The raw result is
    serialized (VerificationStep objects stringified) so the payload is
    JSON-encodable.
    """
    from qwed_legal.models import trace_to_dict

    serialized = _json_safe(result)
    trace = trace_to_dict(result.get("verification_trace", []))
    return LegalDiagnosticResult.unverifiable(
        agent_message=result.get(
            "message",
            "Fairness cannot be deterministically verified.",
        ),
        developer_fields={
            "verified": result.get("verified", False),
            "fairness_result": {**serialized, "verification_trace": trace},
        },
    )


__all__ = [
    "fairness_to_diagnostic",
    "deep_freeze_evidence",
    "LegalDiagnosticStatus",
    "LegalDiagnosticResult",
    "LegalDiagnosticsMixin",
    "canonicalize",
    "compute_proof_ref",
    "resolve_proof_ref",
]
