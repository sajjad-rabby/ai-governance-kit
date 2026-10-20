"""Command-line interface for the governance kit.

Every subcommand runs fully offline.
    card       render a model card (YAML -> Markdown)
    register   summarise / render a NIST AI RMF risk register
    classify   classify a use case under the EU AI Act
    checklist  render a 21 CFR Part 11 or ALCOA+ checklist
    audit      append to / verify a hash-chained audit log

Every subcommand runs fully offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .audit_log import AuditLog
from .checklists import ALCOA_CHECKLIST, PART11_CHECKLIST, render_markdown
from .eu_ai_act import DISCLAIMER, QUESTIONS, QUESTIONS_TEXT, classify_answers
from .model_card import ModelCard
from .risk_register import Register, RiskError

EXIT_OK = 0
EXIT_ERROR = 1


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _write_or_stdout(text: str, out: Optional[str]) -> None:
    """Write ``text`` to ``out`` or stdout. ``-`` means stdout."""
    if out is None or out == "-":
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    else:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")


# -- card ---------------------------------------------------------------------

def cmd_card(args: argparse.Namespace) -> int:

    """Implement cmd card.
    Returns:
        Process exit code; non-zero when the card cannot be read.
    """
    try:
        card = ModelCard.load(args.input)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a message
        return _fail(str(exc))

    if args.to_yaml:
        _write_or_stdout(card.to_yaml(), args.output)
        return EXIT_OK
    _write_or_stdout(card.render(), args.output)
    return EXIT_OK


# -- register ----------------------------------------------------------------

def cmd_register(args: argparse.Namespace) -> int:

    """Implement cmd register.
    Returns:
        Process exit code; non-zero when the register cannot be written.
    """
    try:
        register = Register.load_json(args.path)
    except (RiskError, OSError) as exc:
        return _fail(str(exc))

    if args.format == "markdown":
        _write_or_stdout(register.render_markdown(args.title), args.output)
    elif args.format == "csv":
        _write_or_stdout(register.to_csv(), args.output)
    else:  # json
        _write_or_stdout(register.to_json(), args.output)
    return EXIT_OK


def cmd_register_summary(args: argparse.Namespace) -> int:

    """Implement cmd register summary.
    Returns:
        Process exit code; non-zero when the register cannot be read.
    """
    try:
        register = Register.load_json(args.path)
    except (RiskError, OSError) as exc:
        return _fail(str(exc))

    if args.json:
        print(json.dumps(register.summary(), indent=2))
        return EXIT_OK

    print(f"{'ID':<10} {'SCORE':>5}  {'BAND':<9} {'RMF':<8} TITLE")
    for risk in register.sorted_by_score():
        print(
            f"{risk.id:<10} {risk.score:>5}  {risk.band:<9} "
            f"{risk.ai_rmf_function:<8} {risk.title}"
        )
    print()
    summary = register.summary()
    print(
        "Total {total} — Critical {critical}, High {high}, "
        "Medium {medium}, Low {low}".format(
            total=summary["total"],
            critical=summary["Critical"],
            high=summary["High"],
            medium=summary["Medium"],
            low=summary["Low"],
        )
    )
    return EXIT_OK


# -- classify ----------------------------------------------------------------

def _parse_bool(text: str) -> bool:
    return text.strip().lower() in ("y", "yes", "true", "1")


def cmd_classify(args: argparse.Namespace) -> int:
    """Classify a use case under the EU AI Act.

    Returns:
        Process exit code; non-zero when required arguments are missing.
    """
    bool_keys = (
        "social_scoring",
        "subliminal_manipulation",
        "vulnerable_groups",
        "realtime_remote_biometric",
        "facial_scraping",
        "rights_or_access",
    )
    answers: Dict[str, Any] = {}
    for key in bool_keys:
        value = getattr(args, key, None)
        if value is not None:
            answers[key] = _parse_bool(value)
    if args.use_case is not None:
        answers["use_case"] = args.use_case

    try:
        result = classify_answers(answers)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a message
        return _fail(str(exc))

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return EXIT_OK

    print(f"Tier: {result['tier']}")
    print(f"Use case: {result['use_case']}")
    print()
    print("Reasons:")
    for reason in result["reasons"]:
        print(f"  - {reason}")
    print()
    print(DISCLAIMER)
    return EXIT_OK


def cmd_questions(_: argparse.Namespace) -> int:

    """Implement cmd questions.
    Args:
        _: Unused argparse namespace, kept for a uniform handler signature.

    Returns:
        Process exit code: 0 on success.
    """
    for question in QUESTIONS:
        if question["type"] == "bool":
            print(f"[bool]  {question['key']}")
        else:
            print(f"[choice] {question['key']}")
        print()
        print(f"  {question['text']}")
        print()
    print(DISCLAIMER)
    return EXIT_OK


# -- checklist ---------------------------------------------------------------

def cmd_checklist(args: argparse.Namespace) -> int:
    """Render a 21 CFR Part 11 or ALCOA+ checklist.

    Returns:
        Process exit code: 0 on success.
    """
    checklist = ALCOA_CHECKLIST if args.standard == "alcoa" else PART11_CHECKLIST

    checked: Dict[str, bool] = {}
    if args.checked:
        for item_id in args.checked.split(","):
            key = item_id.strip()
            if key:
                checked[key] = True

    _write_or_stdout(render_markdown(checklist, checked), args.output)
    return EXIT_OK


# -- audit -------------------------------------------------------------------

def cmd_audit_append(args: argparse.Namespace) -> int:
    """Append an event to the hash-chained audit log.

    Returns:
        Process exit code; non-zero when the event cannot be recorded.
    """
    payload: Dict[str, Any] = {}
    if args.payload:
        try:
            loaded = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            return _fail(f"--payload is not valid JSON: {exc}")
        if not isinstance(loaded, dict):
            return _fail("--payload must be a JSON object")
        payload = loaded

    log = AuditLog(args.path)
    problems = log.verify()
    if problems:
        return _fail(
            "refusing to append: existing log failed verification "
            f"({len(problems)} problem(s)); first: {problems[0]['reason']}"
        )

    try:
        entry = log.append(args.event, payload)
    except (OSError, ValueError) as exc:
        return _fail(str(exc))
    print(f"appended seq={entry['seq']} hash={entry['hash'][:16]}...")
    return EXIT_OK


def cmd_audit_verify(args: argparse.Namespace) -> int:
    """Verify the hash-chained audit log.

    Returns:
        Process exit code: 0 when intact, non-zero when verification fails.
    """
    log = AuditLog(args.path)
    try:
        problems = log.verify()
    except (OSError, ValueError) as exc:
        return _fail(str(exc))

    if problems:
        print(f"FAILED: {len(problems)} problem(s) found")
        for problem in problems:
            print(f"  line {problem['line']}: {problem['reason']}")
        return EXIT_ERROR

    entries = log.entries()
    print(f"OK: {len(entries)} entr(ies), chain intact")
    return EXIT_OK


# -- parser ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the full ``govkit`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="govkit",
        description="AI governance tooling: model cards, risk registers, "
        "EU AI Act triage, compliance checklists, audit logs.",
    )
    parser.add_argument("--version", action="version", version=f"govkit {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    # card
    card = sub.add_parser("card", help="render a model card")
    card.add_argument("--input", required=True, help="model card YAML file")
    card.add_argument("--output", help="output file ('-' for stdout)")
    card.add_argument("--to-yaml", action="store_true", help="normalize to YAML instead of Markdown")
    card.set_defaults(func=cmd_card)

    # register
    register = sub.add_parser("register", help="render a risk register")
    register.add_argument("--path", required=True, help="register JSON file")
    register.add_argument(
        "--format", choices=("json", "csv", "markdown"), default="markdown"
    )
    register.add_argument("--title", default="AI Risk Register", help="Markdown report title")
    register.add_argument("--output", help="output file ('-' for stdout)")
    register.set_defaults(func=cmd_register)

    summary = sub.add_parser("register-summary", help="print risks sorted by score")
    summary.add_argument("--path", required=True, help="register JSON file")
    summary.add_argument("--json", action="store_true", help="emit band counts as JSON")
    summary.set_defaults(func=cmd_register_summary)

    # classify
    classify = sub.add_parser("classify", help="classify a use case under the EU AI Act")
    classify.add_argument(
        "--use-case", help="use-case key or number 1-14 (see `govkit questions`)"
    )
    for key in (
        "social_scoring",
        "subliminal_manipulation",
        "vulnerable_groups",
        "realtime_remote_biometric",
        "facial_scraping",
        "rights_or_access",
    ):
        classify.add_argument(f"--{key.replace('_', '-')}", help="yes/no")
    classify.add_argument("--json", action="store_true", help="emit the full result as JSON")
    classify.set_defaults(func=cmd_classify)

    questions = sub.add_parser("questions", help="print the classification questionnaire")
    questions.set_defaults(func=cmd_questions)

    # checklist
    checklist = sub.add_parser("checklist", help="render a compliance checklist")
    checklist.add_argument("--standard", choices=("part11", "alcoa"), default="part11")
    checklist.add_argument("--checked", help="comma-separated item ids to tick off")
    checklist.add_argument("--output", help="output file ('-' for stdout)")
    checklist.set_defaults(func=cmd_checklist)

    # audit
    audit = sub.add_parser("audit", help="append to / verify an audit log")
    audit_sub = audit.add_subparsers(dest="audit_command", metavar="action")
    append = audit_sub.add_parser("append", help="append one event")
    append.add_argument("--path", required=True, help="JSONL audit log path")
    append.add_argument("--event", required=True, help="event type")
    append.add_argument("--payload", help="JSON object payload")
    append.set_defaults(func=cmd_audit_append)

    verify = audit_sub.add_parser("verify", help="verify the hash chain")
    verify.add_argument("--path", required=True, help="JSONL audit log path")
    verify.set_defaults(func=cmd_audit_verify)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # `govkit audit` with no action is a usage error, not a silent success.
    if args.command == "audit" and not getattr(args, "audit_command", None):
        print("error: 'govkit audit' needs an action (append or verify)", file=sys.stderr)
        return EXIT_ERROR

    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_OK

    try:
        return int(args.func(args))
    except BrokenPipeError:  # e.g. piping into `head`
        return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
