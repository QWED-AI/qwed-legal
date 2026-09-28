"""Regression tests for the GitHub Action's clause verification boundary."""

import json
import sys
from pathlib import Path

import pytest

import action_entrypoint


ROOT = Path(__file__).resolve().parents[1]


def _run_argv(argv, monkeypatch, capsys, tmp_path):
    """Run main() with an explicit argv (after the program name)."""
    output = tmp_path / "action-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        sys, "argv", [str(ROOT / "action_entrypoint.py"), *argv]
    )
    with pytest.raises(SystemExit) as raised:
        action_entrypoint.main()
    return raised.value.code, capsys.readouterr().out, output.read_text(encoding="utf-8")


def _run_action(clauses, monkeypatch, capsys, tmp_path):
    return _run_argv(
        ["clause", "", "", "", "", "", "", json.dumps(clauses)],
        monkeypatch,
        capsys,
        tmp_path,
    )


def test_empty_clauses_fail_the_action_closed(monkeypatch, capsys, tmp_path):
    exit_code, stdout, output = _run_action([], monkeypatch, capsys, tmp_path)

    assert exit_code == 1
    assert "Verification FAILED" in stdout
    assert '"status": "invalid_input"' in output


def test_blank_clause_fails_the_action_closed(monkeypatch, capsys, tmp_path):
    exit_code, stdout, output = _run_action(["  \t"], monkeypatch, capsys, tmp_path)

    assert exit_code == 1
    assert "Verification FAILED" in stdout
    assert '"status": "invalid_input"' in output


def test_unsupported_valid_clauses_fail_the_action_closed(
    monkeypatch, capsys, tmp_path
):
    exit_code, stdout, output = _run_action(
        ["Payment due upon receipt", "Buyer shall pay upon receipt"],
        monkeypatch,
        capsys,
        tmp_path,
    )

    assert exit_code == 1
    assert "Verification FAILED" in stdout
    assert '"consistent": false' in output
    assert '"status": "heuristic_pass_limited"' in output


def test_single_clause_fails_closed_insufficient_input(
    monkeypatch, capsys, tmp_path
):
    """Issue #67 comment: a single clause is no-coverage input, not a
    pass — array cardinality must not decide whether analysis runs."""
    exit_code, stdout, output = _run_action(
        ["Payment due upon receipt"],
        monkeypatch,
        capsys,
        tmp_path,
    )

    assert exit_code == 1
    assert "Verification FAILED" in stdout
    assert '"consistent": false' in output
    assert '"status": "insufficient_input"' in output


def test_unknown_mode_fails_closed(monkeypatch, capsys, tmp_path):
    """Issue #67: a typo'd mode must fail, not skip every block into a pass."""
    exit_code, stdout, output = _run_argv(
        ["clauses"], monkeypatch, capsys, tmp_path
    )

    assert exit_code == 1
    assert "Unknown mode" in stdout
    assert "verified<<ghadelimiter_qwed\nfalse" in output


def test_default_invocation_with_no_inputs_fails_closed(
    monkeypatch, capsys, tmp_path
):
    """Issue #67: a bare default run executes zero verifications — that
    must read as failure, not identically to all-passed."""
    exit_code, stdout, output = _run_argv([], monkeypatch, capsys, tmp_path)

    assert exit_code == 1
    assert "No verification performed" in stdout
    assert "verified<<ghadelimiter_qwed\nfalse" in output


def test_mode_with_missing_inputs_fails_closed(monkeypatch, capsys, tmp_path):
    """Issue #67: mode selected but inputs absent — every block skipped
    must fail closed."""
    exit_code, stdout, output = _run_argv(
        ["deadline"], monkeypatch, capsys, tmp_path
    )

    assert exit_code == 1
    assert "No verification performed" in stdout
    assert "verified<<ghadelimiter_qwed\nfalse" in output


def test_block_attests_only_diagnostic_verified():
    """Issues #67/#68 + CodeAnt review: every block is gated on the
    diagnostic ladder (VERIFIED admits), not convenience booleans. Only
    deterministic proof attests — heuristic passes, refusals and
    contradictions all fail, including a novel result shape with
    consistent=False under the default status (Greptile P2)."""
    from qwed_legal.guards.clause_guard import ClauseGuard
    from z3 import Bool, Int

    guard = ClauseGuard()
    assert action_entrypoint._block_attests(
        guard.verify_using_z3([Bool("a"), Int("x") > 5])
    ) is True
    for clauses in (
        ["Seller may terminate with 30 days notice",
         "Buyer may terminate with 60 days notice"],
        ["Payment due upon receipt", "Buyer shall pay upon receipt"],
        ["Payment due upon receipt"],
        [],
        ["  \t"],
    ):
        assert action_entrypoint._block_attests(
            guard.check_consistency(clauses)
        ) is False
    assert action_entrypoint._block_attests(
        guard.verify_using_z3([])
    ) is False


def test_citation_helper_never_attests():
    """Issue #67 comment: citation authority is unconfirmable by design —
    format-valid cites are UNVERIFIABLE_AUTHORITY, never proof."""
    from qwed_legal.guards.citation_guard import CitationGuard

    guard = CitationGuard()
    for text in (
        "Marbury v. Madison, 5 U.S. 137 (1803)",
        "garbage!!! not a citation",
    ):
        result = guard.verify(text)
        assert action_entrypoint._block_attests(result) is False


def test_deadline_liability_blocks_follow_ladder():
    """Deadline/liability blocks use the same helper; deterministic
    matches attest, mismatches do not (no behavior change there)."""
    from qwed_legal import DeadlineGuard, LiabilityGuard

    assert action_entrypoint._block_attests(
        LiabilityGuard().verify_cap(5_000_000, 200, 10_000_000)
    ) is True
    assert action_entrypoint._block_attests(
        LiabilityGuard().verify_cap(5_000_000, 200, 15_000_000)
    ) is False
