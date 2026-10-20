"""Tests for the hash-chained audit log."""

from __future__ import annotations

import json

import pytest

from ai_governance_kit.audit_log import (
    GENESIS_PREV_HASH,
    AuditLog,
    _canonical_json,
    _entry_hash,
)


@pytest.fixture
def log(tmp_path) -> AuditLog:
    return AuditLog(tmp_path / "audit.jsonl")


class TestAppend:
    def test_first_entry_starts_at_genesis(self, log):
        entry = log.append("created")
        assert entry["seq"] == 1
        assert entry["prev_hash"] == GENESIS_PREV_HASH

    def test_sequence_increments(self, log):
        assert log.append("a")["seq"] == 1
        assert log.append("b")["seq"] == 2
        assert log.append("c")["seq"] == 3

    def test_chain_links_to_previous_hash(self, log):
        first = log.append("a")
        second = log.append("b")
        assert second["prev_hash"] == first["hash"]

    def test_hash_is_64_hex(self, log):
        entry = log.append("a")
        assert len(entry["hash"]) == 64
        int(entry["hash"], 16)  # raises if not hex

    def test_payload_defaults_to_empty_dict(self, log):
        assert log.append("a")["payload"] == {}

    def test_payload_is_persisted(self, log):
        log.append("a", {"user": "sajjad", "action": "export"})
        assert log.entries()[0]["payload"]["user"] == "sajjad"

    def test_nested_payload_survives_roundtrip(self, log):
        payload = {"nested": {"list": [1, 2, {"deep": True}]}}
        log.append("a", payload)
        assert log.entries()[0]["payload"] == payload

    def test_creates_parent_directories(self, tmp_path):
        log = AuditLog(tmp_path / "deep" / "nested" / "audit.jsonl")
        log.append("a")
        assert log.path.exists()

    def test_unicode_event_type_accepted(self, log):
        log.append("résumé reviewed")
        assert log.entries()[0]["event_type"] == "résumé reviewed"

    def test_empty_event_type_rejected(self, log):
        with pytest.raises(ValueError):
            log.append("")

    def test_non_string_event_type_rejected(self, log):
        with pytest.raises(ValueError):
            log.append(123)  # type: ignore[arg-type]

    def test_one_json_object_per_line(self, log):
        log.append("a")
        log.append("b")
        lines = log.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        for line in lines:
            json.loads(line)


class TestVerify:
    def test_intact_log_verifies(self, log):
        for i in range(5):
            log.append(f"event-{i}")
        assert log.verify() == []

    def test_missing_log_verifies_empty(self, tmp_path):
        assert AuditLog(tmp_path / "absent.jsonl").verify() == []

    def test_tampered_payload_detected(self, log):
        log.append("a", {"amount": 10})
        log.append("b")

        lines = log.path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["payload"]["amount"] = 1_000_000
        lines[0] = json.dumps(entry, sort_keys=True)
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        problems = log.verify()
        assert any("hash mismatch" in p["reason"] for p in problems)

    def test_deleted_entry_detected(self, log):
        for i in range(3):
            log.append(f"event-{i}")
        lines = log.path.read_text(encoding="utf-8").splitlines()
        del lines[1]
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        problems = log.verify()
        assert any("seq mismatch" in p["reason"] for p in problems)
        assert any("prev_hash" in p["reason"] for p in problems)

    def test_reordered_entries_detected(self, log):
        log.append("a")
        log.append("b")
        lines = log.path.read_text(encoding="utf-8").splitlines()
        lines.reverse()
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert log.verify() != []

    def test_malformed_json_reported(self, log):
        log.append("a")
        with log.path.open("a", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        problems = log.verify()
        assert any("malformed JSON" in p["reason"] for p in problems)

    def test_problem_reports_line_numbers(self, log):
        log.append("a")
        log.append("b")
        lines = log.path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["event_type"] = "tampered"
        lines[0] = json.dumps(entry, sort_keys=True)
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert log.verify()[0]["line"] == 1

    def test_blank_lines_are_skipped(self, log):
        log.append("a")
        log.append("b")
        with log.path.open("a", encoding="utf-8") as fh:
            fh.write("\n\n")
        assert log.verify() == []
        assert len(log.entries()) == 2


class TestEntries:
    def test_empty_when_absent(self, tmp_path):
        assert AuditLog(tmp_path / "nope.jsonl").entries() == []

    def test_entries_match_appends(self, log):
        for i in range(3):
            log.append(f"e{i}")
        assert [e["event_type"] for e in log.entries()] == ["e0", "e1", "e2"]

    def test_append_continues_an_existing_chain(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        AuditLog(path).append("first")
        AuditLog(path).append("second")
        assert AuditLog(path).verify() == []


class TestExport:
    def test_export_writes_json_array(self, log, tmp_path):
        log.append("a", {"k": 1})
        log.append("b")
        out = tmp_path / "export.json"
        log.export(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["payload"] == {"k": 1}

    def test_export_of_empty_log(self, tmp_path):
        out = tmp_path / "empty.json"
        AuditLog(tmp_path / "none.jsonl").export(out)
        assert json.loads(out.read_text(encoding="utf-8")) == []


class TestHashing:
    def test_canonical_json_is_key_order_independent(self):
        assert _canonical_json({"b": 1, "a": 2}) == _canonical_json({"a": 2, "b": 1})

    def test_canonical_json_has_no_spaces(self):
        assert " " not in _canonical_json({"a": 1, "b": [1, 2]})

    def test_entry_hash_excludes_the_hash_field(self):
        entry = {"seq": 1, "ts": "t", "event_type": "x", "payload": {}}
        prev = GENESIS_PREV_HASH
        without = _entry_hash(prev, entry)
        entry_with_hash = dict(entry, hash=without)
        assert _entry_hash(prev, entry_with_hash) == without

    def test_hash_changes_with_prev(self):
        entry = {"seq": 1, "event_type": "x", "payload": {}}
        assert _entry_hash("0" * 64, entry) != _entry_hash("1" * 64, entry)
