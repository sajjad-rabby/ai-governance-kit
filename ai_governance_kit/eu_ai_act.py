"""EU AI Act risk classification.

Classification follows the four tiers named in the Act:
Unacceptable (Prohibited), High, Limited, Minimal.
Prohibited, High, Limited, Minimal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

PROHIBITED = "Prohibited"
HIGH = "High"
LIMITED = "Limited"
MINIMAL = "Minimal"

_TIERS = (PROHIBITED, HIGH, LIMITED, MINIMAL)


CHOICE_MAP: Dict[int, str] = {
    1: "social_scoring",
    2: "employment",
    3: "credit_scoring",
    4: "education",
    5: "essential_services",
    6: "biometric_verification",
    7: "law_enforcement",
    8: "critical_infrastructure",
    9: "migration",
    10: "fraud_detection",
    11: "chatbot",
    12: "emotion_recognition",
    13: "deepfake_generation",
    14: "other",
}

CHOICE_LABELS: Dict[str, str] = {
    "social_scoring": "Social scoring of natural persons",
    "employment": "Employment / worker management / recruitment",
    "credit_scoring": "Credit scoring / creditworthiness of natural persons",
    "education": "Education / vocational training decisions",
    "essential_services": "Access to essential private/public services or benefits",
    "biometric_verification": "Biometric identification / verification",
    "law_enforcement": "Law enforcement use",
    "critical_infrastructure": "Safety components in critical infrastructure",
    "migration": "Migration / asylum / border control",
    "fraud_detection": "Fraud detection (financial services)",
    "chatbot": "Customer-facing chatbot / conversational assistant",
    "emotion_recognition": "Emotion recognition in workplace or education",
    "deepfake_generation": "Deepfake / synthetic content generation",
    "other": "Other / general-purpose use",
}

QUESTIONS_TEXT: Dict[str, str] = {
    "social_scoring": "Does the system evaluate or classify people based on social behaviour or personal characteristics, leading to detrimental treatment in unrelated contexts or disproportionate penalties?",
    "subliminal_manipulation": "Does the system deploy subliminal techniques or purposefully manipulative or deceptive techniques that materially distort behaviour and may cause harm?",
    "vulnerable_groups": "Does the system exploit vulnerabilities of a specific group (age, disability, social or economic situation) to materially distort behaviour in a way that may cause harm?",
    "realtime_remote_biometric": "Does the system use real-time remote biometric identification of persons in publicly accessible spaces?",
    "facial_scraping": "Does the system involve untargeted scraping of facial images from the internet or CCTV to build identification databases?",
    "rights_or_access": "Do outputs materially affect natural persons' rights, safety, livelihoods, or access to essential services?",
    "use_case": "Which category best describes the system's primary use case? Options:\n" + "\n".join(
        f"  {n}. {CHOICE_LABELS[key]}" for n, key in sorted(CHOICE_MAP.items())
    ),
}

QUESTIONS: List[Dict[str, Any]] = [
    {"key": "social_scoring", "type": "bool", "text": QUESTIONS_TEXT["social_scoring"]},
    {"key": "subliminal_manipulation", "type": "bool", "text": QUESTIONS_TEXT["subliminal_manipulation"]},
    {"key": "vulnerable_groups", "type": "bool", "text": QUESTIONS_TEXT["vulnerable_groups"]},
    {"key": "realtime_remote_biometric", "type": "bool", "text": QUESTIONS_TEXT["realtime_remote_biometric"]},
    {"key": "facial_scraping", "type": "bool", "text": QUESTIONS_TEXT["facial_scraping"]},
    {"key": "rights_or_access", "type": "bool", "text": QUESTIONS_TEXT["rights_or_access"]},
    {"key": "use_case", "type": "choice", "text": QUESTIONS_TEXT["use_case"]},
]

_PROHIBITED_KEYS = (
    "social_scoring",
    "subliminal_manipulation",
    "vulnerable_groups",
    "realtime_remote_biometric",
    "facial_scraping",
)

_HIGH_CHOICES = {
    "employment",
    "credit_scoring",
    "education",
    "essential_services",
    "biometric_verification",
    "law_enforcement",
    "critical_infrastructure",
    "migration",
}

_LIMITED_CHOICES = {
    "chatbot",
    "emotion_recognition",
    "deepfake_generation",
}

DISCLAIMER = (
    "This classification is rule-based decision support derived from public summaries of "
    "Regulation (EU) 2024/1689 (the EU AI Act). It is NOT legal advice. Tier assignments "
    "carry no legal force; consult qualified counsel for binding determinations."
)


class ClassificationError(ValueError):
    """Raised when an answers document is malformed."""


def _require_bool(answers: Dict[str, Any], key: str) -> bool:
    value = answers.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("y", "yes", "true"):
            return True
        if lowered in ("n", "no", "false", ""):
            return False
    raise ClassificationError(
        f"answer '{key}' must be a boolean (true/false), got: {value!r}"
    )


def _resolve_choice(answers: Dict[str, Any]) -> str:
    value = answers.get("use_case", "other")
    if value in CHOICE_LABELS:
        return value
    if isinstance(value, int) and value in CHOICE_MAP:
        return CHOICE_MAP[value]
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() and int(text) in CHOICE_MAP:
            return CHOICE_MAP[int(text)]
    raise ClassificationError(
        f"answer 'use_case' must be one of {sorted(CHOICE_LABELS)} or a number 1-14, got: {value!r}"
    )


def classify_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Turn raw questionnaire answers into a classification result.

Returns:
    Mapping with the tier, the triggering obligations, the normalized

    Returns a dict: tier, reasons (list of str), use_case (str key),
    answers (normalized copy), disclaimer.
    """
    if not isinstance(answers, dict):
        raise ClassificationError("answers must be a mapping of question key to value")

    normalized: Dict[str, Any] = {}
    for key in _PROHIBITED_KEYS:
        normalized[key] = _require_bool(answers, key)
    normalized["rights_or_access"] = _require_bool(answers, "rights_or_access")
    normalized["use_case"] = _resolve_choice(answers)

    reasons: List[str] = []

    if normalized["social_scoring"]:
        return _result(PROHIBITED, ["Social scoring of natural persons (Art. 5(1)(c))."], normalized)
    if normalized["subliminal_manipulation"]:
        return _result(
            PROHIBITED,
            ["Subliminal or manipulative techniques distorting behaviour (Art. 5(1)(a))."],
            normalized,
        )
    if normalized["vulnerable_groups"]:
        return _result(
            PROHIBITED,
            ["Exploiting vulnerabilities of specific groups (Art. 5(1)(b))."],
            normalized,
        )
    if normalized["realtime_remote_biometric"]:
        return _result(
            PROHIBITED,
            ["Real-time remote biometric identification in publicly accessible spaces (Art. 5(1)(h))."],
            normalized,
        )
    if normalized["facial_scraping"]:
        return _result(
            PROHIBITED,
            ["Untargeted scraping of facial images for identification databases (Art. 5(1)(e))."],
            normalized,
        )

    use = normalized["use_case"]

    if use in _HIGH_CHOICES:
        reasons.append(f"Use case '{CHOICE_LABELS[use]}' is listed in Annex III as high-risk.")
        if not normalized["rights_or_access"]:
            reasons.append(
                "Outputs appear not to materially affect rights, safety, or access; "
                "classifier stays conservative and keeps the Annex III High tier."
            )
        return _result(HIGH, reasons, normalized)

    if use == "fraud_detection":
        # Annex III 5(a) lists fraud detection as high-risk, but the Regulation
        # carves it out where the purpose is verifying transactions and
        # preventing fraud. That is the purpose this toolkit assumes, so the
        # documented exception applies and the tier drops to Minimal.
        reasons.append(
            "Fraud detection in financial services is listed in Annex III, but the "
            "exception for verifying transactions and preventing fraud applies here; "
            "classified Minimal (Art. 6(3))."
        )
        return _result(MINIMAL, reasons, normalized)

    if use in _LIMITED_CHOICES:
        if use == "chatbot":
            reasons.append("Interaction with natural persons must be disclosed (Art. 50(1)).")
        elif use == "emotion_recognition":
            reasons.append(
                "Emotion recognition in workplace/education is restricted; disclosure applies (Art. 50(3))."
            )
        else:
            reasons.append("Generated/manipulated content must be marked as artificial (Art. 50(4)).")
        return _result(LIMITED, reasons, normalized)

    reasons.append("No prohibited practice, Annex III use case, or transparency obligation matched.")
    return _result(MINIMAL, reasons, normalized)


def _result(tier: str, reasons: List[str], normalized: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tier": tier,
        "reasons": list(reasons),
        "use_case": normalized["use_case"],
        "answers": normalized,
        "disclaimer": DISCLAIMER,
    }


def classify(questionnaire: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify the default (all-no) questionnaire, or the supplied one."""
    if questionnaire is None:
        questionnaire = {q["key"]: False for q in QUESTIONS if q["type"] == "bool"}
        questionnaire["use_case"] = "other"
    return classify_answers(questionnaire)
