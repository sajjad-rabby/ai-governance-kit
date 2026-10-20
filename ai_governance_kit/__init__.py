"""EU AI Act classification, risk registers, and tamper-evident audit logging.

Modules:
- eu_ai_act: risk classification and the obligations it triggers
- risk_register: risk entries, bands, and JSON/CSV/Markdown output
- model_card: documentation card for a classified system
- checklists: documentation checklists per risk tier
- audit_log: append-only hash-chained audit log
- cli: the ``govkit`` command-line entry point

- yaml_min: a minimal, dependency-free YAML parser and dumper
- model_card: build and render model cards as Markdown from YAML
- risk_register: NIST AI RMF risk register (CSV/JSON) with a Markdown report
- eu_ai_act: rule-based EU AI Act risk-tier classifier
- checklists: 21 CFR Part 11 and GxP ALCOA+ checklists
- audit_log: tamper-evident hash-chained JSONL audit log
- cli: the ``govkit`` command-line entry point
"""

from . import audit_log
from . import checklists
from . import eu_ai_act
from . import model_card
from . import risk_register
from . import yaml_min

from .audit_log import AuditLog
from .checklists import ALCOA_CHECKLIST, PART11_CHECKLIST, render_markdown
from .eu_ai_act import QUESTIONS, QUESTIONS_TEXT, classify, classify_answers
from .model_card import ModelCard
from .risk_register import Register, Risk, band_for
from .yaml_min import YAMLError, load, load_file, loads

__version__ = "0.1.0"

__all__ = [
    "ALCOA_CHECKLIST",
    "AuditLog",
    "ModelCard",
    "PART11_CHECKLIST",
    "QUESTIONS",
    "QUESTIONS_TEXT",
    "Register",
    "Risk",
    "YAMLError",
    "audit_log",
    "band_for",
    "checklists",
    "classify",
    "classify_answers",
    "cli",
    "eu_ai_act",
    "load",
    "load_file",
    "loads",
    "model_card",
    "render_markdown",
    "risk_register",
    "yaml_min",
]
