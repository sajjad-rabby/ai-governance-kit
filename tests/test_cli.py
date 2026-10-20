"""Tests for the ``govkit`` command-line interface."""

from __future__ import annotations

import json

import pytest

from ai_governance_kit.audit_log import AuditLog
from ai_governance_kit.cli import main
from ai_governance_kit.risk_register import Register

CARD_YAML = """
name: churn-classifier
version: 2.1.0
developer: Example Corp
license: Proprietary
summary: Gradient-boosted trees.
intended_use: Rank accounts for a retention campaign.
out_of_scope_uses:
  - Credit decisions
training_data:
  rows: 210000
limitations: Degrades on sparse accounts.
"""


@pytest.fixture
def card_path(tmp_path):
    path = tmp_path / "card.yaml"
    path.write_text(CARD_YAML, encoding="utf-8")
    return path


@pytest.fixture
def register_path(tmp_path, register):
    path = tmp_path / "register.json"
    register.save_json(path)
    return path


class TestBasics:
    def test_no_args_prints_help(self, capsys):
        assert main([]) == 0
        assert "usage:" in capsys.readouterr().out

    def test_audit_without_action_is_usage_error(self, capsys):
        assert main(["audit"]) == 1
        assert "needs an action" in capsys.readouterr().err


class TestCard:
    def test_renders_markdown(self, card_path, capsys):
        assert main(["card", "--input", str(card_path)]) == 0
        out = capsys.readouterr().out
        assert "# Model Card: churn-classifier" in out

    def test_writes_to_file(self, card_path, tmp_path):
        out = tmp_path / "card.md"
        assert main(["card", "--input", str(card_path), "--output", str(out)]) == 0
        assert out.read_text(encoding="utf-8").startswith("# Model Card:")

    def test_to_yaml(self, card_path, capsys):
        assert main(["card", "--input", str(card_path), "--to-yaml"]) == 0
        assert "developer: Example Corp" in capsys.readouterr().out

    def test_missing_input_errors(self, tmp_path, capsys):
        assert main(["card", "--input", str(tmp_path / "nope.yaml")]) == 1
        assert "error:" in capsys.readouterr().err

    def test_dash_output_means_stdout(self, card_path, capsys):
        assert main(["card", "--input", str(card_path), "--output", "-"]) == 0
        assert "# Model Card" in capsys.readouterr().out


class TestRegister:
    def test_markdown_output(self, register_path, capsys):
        assert main(["register", "--path", str(register_path)]) == 0
        out = capsys.readouterr().out
        assert out.startswith("# AI Risk Register")
        assert "Total risks: 4" in out

    def test_custom_title(self, register_path, capsys):
        main(["register", "--path", str(register_path), "--title", "Q3 Review"])
        assert "# Q3 Review" in capsys.readouterr().out

    def test_json_format(self, register_path, capsys):
        assert main(["register", "--path", str(register_path), "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)[0]["id"] == "R-001"

    def test_csv_format(self, register_path, capsys):
        assert main(["register", "--path", str(register_path), "--format", "csv"]) == 0
        out = capsys.readouterr().out
        assert out.splitlines()[0].startswith("id,title,description")

    def test_missing_file_errors(self, tmp_path, capsys):
        assert main(["register", "--path", str(tmp_path / "nope.json")]) == 1
        assert "error:" in capsys.readouterr().err


class TestRegisterSummary:
    def test_sorted_table(self, register_path, capsys):
        assert main(["register-summary", "--path", str(register_path)]) == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("R-")]
        assert len(lines) == 4
        # descending by score: R-001 (16) then R-002 (15)
        assert lines[0].startswith("R-001")
        assert lines[1].startswith("R-002")

    def test_json_counts(self, register_path, capsys):
        main(["register-summary", "--path", str(register_path), "--json"])
        summary = json.loads(capsys.readouterr().out)
        assert summary["total"] == 4
        assert summary["High"] == 2


class TestClassify:
    def test_minimal_by_default(self, capsys):
        assert main(["classify", "--use-case", "other"]) == 0
        assert "Tier: Minimal" in capsys.readouterr().out

    def test_high_risk_use_case(self, capsys):
        main(["classify", "--use-case", "employment"])
        assert "Tier: High" in capsys.readouterr().out

    def test_prohibited_flag(self, capsys):
        main(["classify", "--use-case", "other", "--social-scoring", "yes"])
        assert "Tier: Prohibited" in capsys.readouterr().out

    def test_numeric_choice(self, capsys):
        main(["classify", "--use-case", "2"])
        assert "Use case: employment" in capsys.readouterr().out

    def test_json_output(self, capsys):
        assert main(["classify", "--use-case", "chatbot", "--json"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["tier"] == "Limited"

    def test_invalid_use_case_errors(self, capsys):
        assert main(["classify", "--use-case", "teleportation"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_disclaimer_always_printed(self, capsys):
        main(["classify", "--use-case", "other"])
        assert "NOT legal advice" in capsys.readouterr().out

    def test_questions_command(self, capsys):
        assert main(["questions"]) == 0
        out = capsys.readouterr().out
        assert "social_scoring" in out
        assert "use_case" in out


class TestChecklist:
    def test_part11_default(self, capsys):
        assert main(["checklist"]) == 0
        out = capsys.readouterr().out
        assert "21 CFR Part 11" in out
        assert "- [ ] **P11-01" in out

    def test_alcoa(self, capsys):
        main(["checklist", "--standard", "alcoa"])
        out = capsys.readouterr().out
        assert "ALCOA" in out
        assert "- [ ] **A-01" in out

    def test_checked_items_render_ticked(self, capsys):
        main(["checklist", "--standard", "alcoa", "--checked", "A-01,A-02"])
        out = capsys.readouterr().out
        assert "- [x] **A-01" in out
        assert "- [x] **A-02" in out
        assert "- [ ] **A-03" in out

    def test_signoff_table_present(self, capsys):
        main(["checklist"])
        assert "| Role | Name | Date | Signature |" in capsys.readouterr().out


class TestAudit:
    def test_append_then_verify(self, tmp_path, capsys):
        path = tmp_path / "audit.jsonl"
        assert main(["audit", "append", "--path", str(path), "--event", "created"]) == 0
        assert "appended seq=1" in capsys.readouterr().out
        assert main(["audit", "verify", "--path", str(path)]) == 0
        assert "OK: 1 entr" in capsys.readouterr().out

    def test_append_payload(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        main(["audit", "append", "--path", str(path),
              "--event", "export", "--payload", '{"n": 3}'])
        assert AuditLog(path).entries()[0]["payload"] == {"n": 3}

    def test_invalid_payload_errors(self, tmp_path, capsys):
        path = tmp_path / "audit.jsonl"
        assert main(["audit", "append", "--path", str(path),
                     "--event", "x", "--payload", "{bad"]) == 1
        assert "valid JSON" in capsys.readouterr().err

    def test_non_object_payload_errors(self, tmp_path, capsys):
        path = tmp_path / "audit.jsonl"
        assert main(["audit", "append", "--path", str(path),
                     "--event", "x", "--payload", "[1]"]) == 1
        assert "JSON object" in capsys.readouterr().err

    def test_append_to_tampered_log_refused(self, tmp_path, capsys):
        path = tmp_path / "audit.jsonl"
        main(["audit", "append", "--path", str(path), "--event", "a"])
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"seq": 99, "hash": "deadbeef"}\n')
        assert main(["audit", "append", "--path", str(path), "--event", "b"]) == 1
        assert "failed verification" in capsys.readouterr().err

    def test_verify_tampered_log_fails(self, tmp_path, capsys):
        path = tmp_path / "audit.jsonl"
        main(["audit", "append", "--path", str(path), "--event", "a"])
        entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        entry["event_type"] = "tampered"
        path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
        assert main(["audit", "verify", "--path", str(path)]) == 1
        assert "FAILED" in capsys.readouterr().out

    def test_verify_missing_file_is_ok(self, tmp_path, capsys):
        assert main(["audit", "verify", "--path", str(tmp_path / "none.jsonl")]) == 0
        assert "OK: 0 entr" in capsys.readouterr().out


class TestCsvRoundTripThroughCli:
    def test_csv_output_reimports(self, register_path, tmp_path, capsys):
        main(["register", "--path", str(register_path), "--format", "csv",
              "--output", str(tmp_path / "out.csv")])
        reloaded = Register.load_csv(tmp_path / "out.csv")
        assert len(reloaded.risks) == 4
