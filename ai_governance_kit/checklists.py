"""Documentation checklists keyed by risk tier.

Checklists are static guidance: a tier is not a legal determination, and a team
can record its own evidence and sign-off status. They are not

These checklists are documentation aids. They express widely recognized
principles (21 CFR Part 11 and ALCOA+) as yes/no questions so that a team
can record its own evidence and sign-off status. They are not legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ChecklistItem:
    """One auditable question."""

    id: str
    requirement: str
    guidance: str = ""
    reference: str = ""


@dataclass
class Checklist:
    """A named checklist made of items."""

    title: str
    standard: str
    purpose: str
    items: List[ChecklistItem] = field(default_factory=list)


def _item(iid: str, requirement: str, guidance: str, reference: str) -> ChecklistItem:
    return ChecklistItem(id=iid, requirement=requirement, guidance=guidance, reference=reference)


PART11_CHECKLIST = Checklist(
    title="21 CFR Part 11 Electronic Records & Electronic Signatures Checklist",
    standard="21 CFR Part 11 (US FDA)",
    purpose=(
        "Verify that electronic records and electronic signatures used in "
        "regulated contexts satisfy the core controls of 21 CFR Part 11."
    ),
    items=[
        _item(
            "P11-01",
            "Has the system been validated to ensure accuracy, reliability, and consistent intended performance?",
            "Document validation scope, test evidence, and revalidation triggers.",
            "§ 11.10(a)",
        ),
        _item(
            "P11-02",
            "Are copies of electronic records capable of producing accurate and complete outputs (human-readable and electronic form)?",
            "Confirm export formats preserve all record content and metadata.",
            "§ 11.10(b)",
        ),
        _item(
            "P11-03",
            "Are electronic records protected to enable ready retrieval throughout the retention period?",
            "Define backup, migration, and archival procedures.",
            "§ 11.10(c)",
        ),
        _item(
            "P11-04",
            "Is system access limited to authorized individuals?",
            "Role-based access control with documented user provisioning.",
            "§ 11.10(d)",
        ),
        _item(
            "P11-05",
            "Do audit trails use secure, computer-generated, time-stamped records that cannot be overwritten?",
            "Audit trail must record operator identity and date/time of actions.",
            "§ 11.10(e)",
        ),
        _item(
            "P11-06",
            "Is operational/system input (e.g., data entry) checked for accuracy before use, where required?",
            "Field validation, range checks, or independent verification.",
            "§ 11.10(f)",
        ),
        _item(
            "P11-07",
            "Are authority checks in place so only authorized individuals can use the system, sign, or alter records?",
            "Enforced permissions, not policy-only.",
            "§ 11.10(g)",
        ),
        _item(
            "P11-08",
            "Are device checks used where required to determine the validity of source data or instrument input?",
            "Relevant for interfaces and automated data capture.",
            "§ 11.10(h)",
        ),
        _item(
            "P11-09",
            "Do personnel qualifications and training records exist for system users, developers, and support staff?",
            "Training must cover the controls and procedures in place.",
            "§ 11.10(i)",
        ),
        _item(
            "P11-10",
            "Are written policies holding individuals accountable for their e-signatures documented and enforced?",
            "Anti-repudiation policy plus awareness communication.",
            "§ 11.10(j)",
        ),
        _item(
            "P11-11",
            "Are controls over system documentation (distribution, access, revision, and change control) maintained?",
            "Versioned SOPs, controlled distribution, and change records.",
            "§ 11.10(k)",
        ),
        _item(
            "P11-12",
            "Do signed electronic records display the printed name of the signer, date and time of signing, and the meaning of the signature?",
            "All elements must be subject to the same controls as the record.",
            "§ 11.50",
        ),
        _item(
            "P11-13",
            "Are electronic and handwritten signatures executed and linked to their records so signatures cannot be excised, copied, or transferred?",
            "Verify signature-record binding and non-transferability.",
            "§ 11.70",
        ),
        _item(
            "P11-14",
            "Does each individual possess a unique e-signature ID that is not reassigned, with periodic recertification?",
            "Shared accounts invalidate signature attribution.",
            "§ 11.100",
        ),
        _item(
            "P11-15",
            "Are identity verification procedures documented before an e-signature is established?",
            "Retain evidence of who verified identity and when.",
            "§ 11.100(b)",
        ),
        _item(
            "P11-16",
            "Are ID/password controls in place: uniqueness, expiration, loss management, transaction safeguards, and device testing?",
            "Covers § 11.300(a) through (d) controls.",
            "§ 11.300",
        ),
    ],
)

_ALCOA_ITEMS: List[tuple] = [
    ("A-01", "Attributable", "Every record and action traces to a specific, identified person or system account.", "Record who did what and when."),
    ("A-02", "Legible", "Records are readable and permanently understandable for their whole retention life.", "Avoid formats that become unreadable."),
    ("A-03", "Contemporaneous", "Data are recorded at the time the activity is performed.", "No back-dating or batch transcription."),
    ("A-04", "Original", "The first capture of data (or a certified true copy) is preserved.", "Raw data retain priority over transcriptions."),
    ("A-05", "Accurate", "Data are correct, complete, and reflect what actually occurred.", "Corrections preserve originals with reasons."),
    ("A-06", "Complete", "All data, including repeats, reanalysis, and metadata, are captured.", "Nothing meaningful is filtered out."),
    ("A-07", "Consistent", "Data are chronologically ordered, expected, and traceable through their sequence of use.", "Sequences make sense in time."),
    ("A-08", "Enduring", "Records are stored on durable media and last as long as needed.", "Not on sticky notes or volatile media."),
    ("A-09", "Available", "Records are retrievable for review, audit, or inspection when required.", "Accessible for the whole retention period."),
]

ALCOA_CHECKLIST = Checklist(
    title="GxP Data Integrity Checklist (ALCOA+)",
    standard="ALCOA+ data integrity principles (MHRA / WHO / FDA aligned)",
    purpose=(
        "Assess data integrity of records and systems against the ALCOA+ "
        "principles commonly referenced in GxP environments."
    ),
    items=[
        _item(iid=iid, requirement=f"{principle}: {desc}", guidance=guid, reference="ALCOA+")
        for iid, principle, desc, guid in _ALCOA_ITEMS
    ],
)


def render_markdown(checklist: Checklist, checked: Optional[Dict[str, bool]] = None) -> str:
    """Render a checklist as Markdown.

Args:
    checklist: The checklist to render.
    checked: Maps item ids to completion state;

    ``checked`` maps item ids to completion state; missing ids render as unchecked.
    """
    checked = checked or {}
    lines: List[str] = []
    lines.append(f"# {checklist.title}")
    lines.append("")
    lines.append(f"**Standard:** {checklist.standard}")
    lines.append("")
    lines.append(f"**Purpose:** {checklist.purpose}")
    lines.append("")
    lines.append("## Checklist")
    lines.append("")
    for item in checklist.items:
        mark = "[x]" if checked.get(item.id) else "[ ]"
        lines.append(f"- {mark} **{item.id} — {item.requirement}**")
        if item.guidance:
            lines.append(f"    - {item.guidance}")
        if item.reference:
            lines.append(f"    - Reference: {item.reference}")
    lines.append("")
    lines.append("## Sign-off")
    lines.append("")
    lines.append("| Role | Name | Date | Signature |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| Prepared by |  |  |  |")
    lines.append("| Reviewed by |  |  |  |")
    lines.append("| Approved by |  |  |  |")
    lines.append("")
    lines.append("_Documentation aid only; not legal advice._")
    lines.append("")
    return "\n".join(lines)
