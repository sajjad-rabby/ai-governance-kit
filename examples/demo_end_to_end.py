"""End-to-end tour of ai-governance-kit. Runs fully offline; no API keys.

    python examples/demo_end_to_end.py

It builds a model card, scores a risk register, classifies a use case under
the EU AI Act, renders a compliance checklist, and writes a tamper-evident
audit log — then proves the log detects tampering.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_governance_kit import (  # noqa: E402
    AuditLog,
    ModelCard,
    Register,
    classify_answers,
    render_markdown,
    PART11_CHECKLIST,
)


def rule(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="govkit-demo-"))

    # -- 1. Model card ------------------------------------------------------
    rule("STEP 1 - MODEL CARD (YAML -> Markdown)")
    card = ModelCard.load(str(REPO_ROOT / "examples" / "model_card.yaml"))
    markdown = card.render()
    print(markdown[:600])
    print(f"...")
    print(f"[card rendered from YAML: {len(markdown.splitlines())} lines]")

    # YAML round-trip: card -> YAML -> card must be lossless.
    yaml_path = workdir / "card.yaml"
    yaml_path.write_text(card.to_yaml(), encoding="utf-8")
    assert ModelCard.load(str(yaml_path)).to_dict() == card.to_dict()
    print("[YAML round-trip preserved every field]")

    # -- 2. Risk register ---------------------------------------------------
    rule("STEP 2 - RISK REGISTER (NIST AI RMF)")
    register = Register.load_json(REPO_ROOT / "examples" / "risk_register.json")
    print(f"{'ID':<8} {'SCORE':>5}  {'BAND':<9} {'RMF':<8} TITLE")
    for risk in register.sorted_by_score():
        print(f"{risk.id:<8} {risk.score:>5}  {risk.band:<9} "
              f"{risk.ai_rmf_function:<8} {risk.title}")
    summary = register.summary()
    print()
    print(f"Total {summary['total']} - Critical {summary['Critical']}, "
          f"High {summary['High']}, Medium {summary['Medium']}, Low {summary['Low']}")

    # JSON -> CSV -> JSON must be lossless.
    csv_path = register.save_csv(workdir / "register.csv")
    reloaded = Register.load_csv(csv_path)
    assert reloaded.to_json() == register.to_json()
    print("[CSV round-trip preserved every risk and mitigation]")

    # -- 3. EU AI Act classification ---------------------------------------
    rule("STEP 3 - EU AI ACT TRIAGE")
    scenarios = [
        ("Resume screening model (employment)", {
            "use_case": "employment",
            "rights_or_access": True,
        }),
        ("Customer support chatbot", {"use_case": "chatbot"}),
        ("Employee emotion monitoring", {"use_case": "emotion_recognition"}),
        ("Card-payment fraud screening", {"use_case": "fraud_detection"}),
        ("Social media recommendation feed", {"use_case": "other"}),
    ]
    for label, answers in scenarios:
        result = classify_answers(answers)
        print(f"  {result['tier']:<12} <- {label}")
        for reason in result["reasons"]:
            print(f"                 {reason}")

    # A prohibited practice outranks every other consideration.
    prohibited = classify_answers({"use_case": "employment", "social_scoring": True})
    print(f"  {prohibited['tier']:<12} <- employment + social scoring "
          "(prohibited practice wins)")

    # -- 4. Compliance checklist -------------------------------------------
    rule("STEP 4 - 21 CFR PART 11 CHECKLIST (first 8 items)")
    checklist_md = render_markdown(PART11_CHECKLIST, {"P11-05": True})
    shown = 0
    for line in checklist_md.splitlines():
        if not line.startswith("- ["):
            continue
        print(line)
        shown += 1
        if shown == 8:
            break
    print(f"... ({len(PART11_CHECKLIST.items)} items total)")

    # -- 5. Audit log -------------------------------------------------------
    rule("STEP 5 - TAMPER-EVIDENT AUDIT LOG")
    audit_path = workdir / "governance.jsonl"
    log = AuditLog(audit_path)

    for event, payload in [
        ("register.reviewed", {"risks": len(register.risks)}),
        ("card.published", {"name": card.name, "version": card.version}),
        ("release.approved", {"approver": "model-risk-board"}),
    ]:
        entry = log.append(event, payload)
        print(f"  appended seq={entry['seq']} "
              f"hash={entry['hash'][:16]}...  ({event})")

    assert log.verify() == []
    print("[chain verified intact]")

    # Now forge an entry the way a bad actor would: rewrite a signed fact.
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["payload"]["approver"] = "not-the-board"
    lines[1] = json.dumps(forged, sort_keys=True)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = log.verify()
    print(f"[after tampering: {len(problems)} problem(s) detected]")
    for problem in problems:
        print(f"    line {problem['line']}: {problem['reason']}")

    rule("DEMO COMPLETE")
    print(f"artefacts written to: {workdir}")
    print("Every step above ran offline with no API keys and no network access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
