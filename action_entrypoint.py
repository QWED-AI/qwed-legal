#!/usr/bin/env python3
"""
QWED-Legal GitHub Action Entrypoint

Runs legal verification based on inputs and sets GitHub Action outputs.
"""

import json
import os
import sys

from qwed_legal import DeadlineGuard, LiabilityGuard, ClauseGuard, CitationGuard
from qwed_legal.diagnostics import LegalDiagnosticStatus

VALID_MODES = ("deadline", "liability", "clause", "citation", "all")

# Clause statuses that attest consistency and may keep the action verified
# (#68): heuristic "consistent" and deterministic z3_satisfiable. Every
# other status — contradiction, heuristic_pass_limited, invalid_input,
# insufficient_input, or any unknown future status — fails closed.
_ATTESTING_CLAUSE_STATUSES = ("consistent", "z3_satisfiable")


def _clause_block_attests(result) -> bool:
    """Whether a clause result may keep an action verified."""
    return result.status in _ATTESTING_CLAUSE_STATUSES


def _citation_block_attests(result) -> bool:
    """Whether a citation result may keep an action verified.

    Never True: citation authority is unconfirmable by design — a
    format-valid cite maps to UNVERIFIABLE_AUTHORITY (non-authoritative),
    so there is no attesting citation outcome (#67 comment).
    """
    return result.to_diagnostic().status is LegalDiagnosticStatus.VERIFIED


def set_output(name: str, value: str):
    """Set GitHub Action output using heredoc delimiter format."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        # Sanitize the output name (no newlines)
        safe_name = name.replace("\r", "").replace("\n", "")
        # Use heredoc delimiter to prevent newline injection
        delimiter = "ghadelimiter_qwed"
        while delimiter in value:
            delimiter += "_x"
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{safe_name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"::set-output name={name}::{value}")


def main():
    args = sys.argv[1:]

    # Parse arguments
    mode = args[0] if len(args) > 0 and args[0] else "all"
    signing_date = args[1] if len(args) > 1 and args[1] else None
    term = args[2] if len(args) > 2 and args[2] else None
    claimed_deadline = args[3] if len(args) > 3 and args[3] else None
    contract_value = args[4] if len(args) > 4 and args[4] else None
    cap_percentage = args[5] if len(args) > 5 and args[5] else None
    claimed_cap = args[6] if len(args) > 6 and args[6] else None
    clauses_json = args[7] if len(args) > 7 and args[7] else None
    citation = args[8] if len(args) > 8 and args[8] else None
    country = args[9] if len(args) > 9 and args[9] else "US"
    state = args[10] if len(args) > 10 and args[10] else None

    results = {}
    all_verified = True
    messages = []
    executed_blocks = []

    # Fail closed on unknown modes (#67): a typo'd mode previously skipped
    # every block yet emitted verified="true" + exit 0.
    if mode not in VALID_MODES:
        all_verified = False
        messages.append(
            f"Unknown mode '{mode}': expected one of {', '.join(VALID_MODES)}."
        )
        print(messages[-1])

    # Deadline verification
    if mode in ["deadline", "all"] and signing_date and term and claimed_deadline:
        executed_blocks.append("deadline")
        guard = DeadlineGuard(country=country, state=state)
        result = guard.verify(signing_date, term, claimed_deadline)
        results["deadline"] = {
            "verified": result.verified,
            "computed": (
                result.computed_deadline.isoformat()
                if result.computed_deadline
                else None
            ),
            "claimed": claimed_deadline,
            "difference_days": result.difference_days,
            "message": result.message,
        }
        if not result.verified:
            all_verified = False
        messages.append(result.message)
        print(result.message)

    # Liability verification
    if (
        mode in ["liability", "all"]
        and contract_value
        and cap_percentage
        and claimed_cap
    ):
        executed_blocks.append("liability")
        guard = LiabilityGuard()
        result = guard.verify_cap(
            float(contract_value), float(cap_percentage), float(claimed_cap)
        )
        # computed_cap/difference are None on fail-closed (non-finite or
        # out-of-range inputs) — serialize from the RESULT so fail-closed
        # outputs stay strict-JSON (null), never bare NaN/Infinity tokens
        results["liability"] = {
            "verified": result.verified,
            "computed": (
                float(result.computed_cap)
                if result.computed_cap is not None
                else None
            ),
            "claimed": (
                float(result.claimed_cap)
                if result.claimed_cap is not None
                else None
            ),
            "difference": (
                float(result.difference)
                if result.difference is not None
                else None
            ),
            "message": result.message,
        }
        if not result.verified:
            all_verified = False
        messages.append(result.message)
        print(result.message)

    # Clause verification
    if mode in ["clause", "all"] and clauses_json:
        executed_blocks.append("clause")
        try:
            clauses = json.loads(clauses_json)
            guard = ClauseGuard()
            result = guard.check_consistency(clauses)
            results["clause"] = {
                "consistent": result.consistent,
                "status": result.status,
                "conflicts": [(c[0], c[1], c[2]) for c in result.conflicts],
                "message": result.message,
            }
            # Fail on every non-attesting status (#68): contradiction,
            # heuristic_pass_limited, invalid_input and insufficient_input
            # (single-clause no-coverage) all clear all_verified — only an
            # attesting status keeps the action green.
            if not _clause_block_attests(result):
                all_verified = False
            messages.append(result.message)
            print(result.message)
        except json.JSONDecodeError as e:
            results["clause"] = {"error": f"Invalid JSON: {e}"}
            all_verified = False

    # Citation verification
    if mode in ["citation", "all"] and citation:
        executed_blocks.append("citation")
        guard = CitationGuard()
        result = guard.verify(citation)
        results["citation"] = {
            "valid": result.valid,
            "citation_type": result.citation_type,
            "parsed": result.parsed_components,
            "issues": result.issues,
            "message": result.message,
        }
        # Citations never attest: format validity is not authority validity,
        # so even a format-valid cite clears all_verified (#67 comment).
        if not _citation_block_attests(result):
            all_verified = False
        messages.append(result.message)
        print(result.message)

    # Fail closed when nothing executed (#67): missing inputs or a default
    # invocation previously skipped every block yet emitted verified="true".
    if mode in VALID_MODES and not executed_blocks:
        all_verified = False
        messages.append(
            f"No verification performed for mode '{mode}': required inputs "
            "were missing, so every block was skipped. Failing closed."
        )
        print(messages[-1])

    # Set outputs
    set_output("verified", str(all_verified).lower())
    set_output("results", json.dumps(results))
    set_output(
        "message", " | ".join(messages) if messages else "No verification performed"
    )

    # Exit with error if verification failed
    if not all_verified:
        print("\n🛑 QWED Legal: Verification FAILED")
        sys.exit(1)
    else:
        print("\n✅ QWED Legal: All verifications PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
