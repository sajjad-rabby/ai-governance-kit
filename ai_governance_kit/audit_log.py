"""Append-only audit log where each entry commits to the previous one.

Every entry stores its timestamp, event name, payload and a SHA-256 hash of the entry
serialized canonically. The first entry's ``prev_hash`` is 64 zeros.

    {"seq": N, "ts": ISO8601 UTC, "event_type": str, "payload": obj,
     "prev_hash": hex, "hash": hex}

``hash`` covers ``prev_hash`` plus the entry itself (excluding ``hash``)
serialized canonically. The first entry's ``prev_hash`` is 64 zeros.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

GENESIS_PREV_HASH = "0" * 64


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_hash(prev_hash: str, entry: Dict[str, Any]) -> str:
    basis = {"prev_hash": prev_hash}
    basis.update({k: v for k, v in entry.items() if k != "hash"})
    return hashlib.sha256(_canonical_json(basis).encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained audit log persisted as JSONL."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    # -- writing -----------------------------------------------------------

    def append(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Append one event; returns the stored entry including its hash."""
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event_type must be a non-empty string")
        prev_hash = GENESIS_PREV_HASH
        seq = 1
        existing = self.entries()
        if existing:
            prev_hash = existing[-1]["hash"]
            seq = existing[-1]["seq"] + 1
        entry = {
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload if payload is not None else {},
            "prev_hash": prev_hash,
        }
        entry["hash"] = _entry_hash(prev_hash, entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    # -- reading -----------------------------------------------------------

    def entries(self) -> List[Dict[str, Any]]:
        """Load entries, skipping blank lines. Malformed JSON raises ValueError."""
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            out.append(json.loads(raw))
        return out

    def verify(self) -> List[Dict[str, int | str]]:
        """Re-derive the hash chain and report every problem found.

Returns:
    One dict per problem:

        Returns a list of problem dicts; an empty list means the log is intact.
        Each problem: {"line": 1-based file line, "reason": str}.
        """
        problems: List[Dict[str, int | str]] = []
        if not self.path.exists():
            return problems
        prev_hash = GENESIS_PREV_HASH
        expected_seq = 1
        for lineno, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                problems.append({"line": lineno, "reason": "malformed JSON"})
                continue
            if entry.get("seq") != expected_seq:
                problems.append({"line": lineno, "reason": f"seq mismatch (expected {expected_seq})"})
            if entry.get("prev_hash") != prev_hash:
                problems.append({"line": lineno, "reason": "prev_hash does not match previous entry"})
            expected = _entry_hash(entry.get("prev_hash", GENESIS_PREV_HASH), entry)
            if entry.get("hash") != expected:
                problems.append({"line": lineno, "reason": "hash mismatch (entry modified or corrupted)"})
            prev_hash = entry.get("hash", "")
            expected_seq += 1
        return problems

    def export(self, path: Union[str, Path]) -> None:
        """Export entries as a pretty-printed JSON array."""
        Path(path).write_text(
            json.dumps(self.entries(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
