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


def test_clause_helper_attests_only_attesting_statuses():
    """Issue #68: only consistent + z3_satisfiable keep the action green;
    every refusal status (and any unknown future one) fails."""
    from qwed_legal.guards.clause_guard import ClauseGuard

    guard = ClauseGuard()
    assert action_entrypoint._clause_block_attests(
        guard.check_consistency(
            ["Seller may terminate with 30 days notice",
             "Buyer may terminate with 60 days notice"]
        )
    ) is True
    for clauses in (
        ["Payment due upon receipt", "Buyer shall pay upon receipt"],
        ["Payment due upon receipt"],
        [],
        ["  \t"],
    ):
        result = guard.check_consistency(clauses)
        assert result.status in (
            "heuristic_pass_limited",
            "insufficient_input",
            "invalid_input",
        ), result.status
        assert action_entrypoint._clause_block_attests(result) is False


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
        assert action_entrypoint._citation_block_attests(result) is False
