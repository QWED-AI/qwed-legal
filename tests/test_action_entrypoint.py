"""Regression tests for the GitHub Action's clause verification boundary."""

import json
import sys
from pathlib import Path

import pytest

import action_entrypoint


ROOT = Path(__file__).resolve().parents[1]


def _run_action(clauses, monkeypatch, capsys, tmp_path):
    output = tmp_path / "action-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(ROOT / "action_entrypoint.py"),
            "clause",
            "",
            "",
            "",
            "",
            "",
            "",
            json.dumps(clauses),
        ],
    )
    with pytest.raises(SystemExit) as raised:
        action_entrypoint.main()
    return raised.value.code, capsys.readouterr().out, output.read_text(encoding="utf-8")


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


def test_valid_single_clause_keeps_action_success(monkeypatch, capsys, tmp_path):
    exit_code, stdout, output = _run_action(
        ["Payment due upon receipt"],
        monkeypatch,
        capsys,
        tmp_path,
    )

    assert exit_code == 0
    assert "All verifications PASSED" in stdout
    assert '"consistent": true' in output
