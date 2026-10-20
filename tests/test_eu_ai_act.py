"""Tests for the EU AI Act risk-tier classifier."""

from __future__ import annotations

import pytest

from ai_governance_kit.eu_ai_act import (
    CHOICE_LABELS,
    CHOICE_MAP,
    DISCLAIMER,
    HIGH,
    LIMITED,
    MINIMAL,
    PROHIBITED,
    QUESTIONS,
    QUESTIONS_TEXT,
    ClassificationError,
    classify,
    classify_answers,
)

ALL_FALSE = {
    "social_scoring": False,
    "subliminal_manipulation": False,
    "vulnerable_groups": False,
    "realtime_remote_biometric": False,
    "facial_scraping": False,
    "rights_or_access": False,
}


class TestProhibitedPractices:
    @pytest.mark.parametrize(
        "key",
        [
            "social_scoring",
            "subliminal_manipulation",
            "vulnerable_groups",
            "realtime_remote_biometric",
            "facial_scraping",
        ],
    )
    def test_each_prohibited_flag_wins_over_everything(self, key):
        answers = dict(ALL_FALSE, **{key: True}, use_case="chatbot")
        result = classify_answers(answers)
        assert result["tier"] == PROHIBITED
        assert any("Art. 5" in reason for reason in result["reasons"])

    def test_prohibited_outranks_high_risk_use_case(self):
        answers = dict(ALL_FALSE, social_scoring=True, use_case="employment")
        assert classify_answers(answers)["tier"] == PROHIBITED


class TestHighRisk:
    @pytest.mark.parametrize(
        "use_case",
        [
            "employment",
            "credit_scoring",
            "education",
            "essential_services",
            "biometric_verification",
            "law_enforcement",
            "critical_infrastructure",
            "migration",
        ],
    )
    def test_annex_iii_use_cases_are_high(self, use_case):
        result = classify_answers(dict(ALL_FALSE, use_case=use_case))
        assert result["tier"] == HIGH
        assert any("Annex III" in reason for reason in result["reasons"])

    def test_high_tier_held_even_without_rights_impact(self):
        result = classify_answers(dict(ALL_FALSE, rights_or_access=False, use_case="employment"))
        assert result["tier"] == HIGH
        assert any("conservative" in reason for reason in result["reasons"])

    def test_rights_impact_removes_the_conservatism_note(self):
        result = classify_answers(dict(ALL_FALSE, rights_or_access=True, use_case="employment"))
        assert result["tier"] == HIGH
        assert not any("conservative" in reason for reason in result["reasons"])


class TestFraudDetectionException:
    def test_fraud_detection_is_minimal(self):
        result = classify_answers(dict(ALL_FALSE, use_case="fraud_detection"))
        assert result["tier"] == MINIMAL

    def test_fraud_detection_cites_the_exception(self):
        """Regression: the exception branch used to be unreachable code."""
        result = classify_answers(dict(ALL_FALSE, use_case="fraud_detection"))
        assert any("Art. 6(3)" in reason for reason in result["reasons"])


class TestLimited:
    @pytest.mark.parametrize("use_case", ["chatbot", "emotion_recognition", "deepfake_generation"])
    def test_transparency_use_cases(self, use_case):
        result = classify_answers(dict(ALL_FALSE, use_case=use_case))
        assert result["tier"] == LIMITED
        assert any("Art. 50" in reason for reason in result["reasons"])

    def test_chatbot_cites_disclosure(self):
        result = classify_answers(dict(ALL_FALSE, use_case="chatbot"))
        assert "disclosed" in result["reasons"][0]


class TestMinimal:
    def test_other_use_case_is_minimal(self):
        assert classify_answers(dict(ALL_FALSE, use_case="other"))["tier"] == MINIMAL

    def test_default_classification_is_minimal(self):
        assert classify()["tier"] == MINIMAL


class TestChoiceResolution:
    def test_string_key(self):
        assert classify_answers(dict(ALL_FALSE, use_case="employment"))["use_case"] == "employment"

    def test_integer_choice_number(self):
        assert classify_answers(dict(ALL_FALSE, use_case=2))["use_case"] == "employment"

    def test_stringified_choice_number(self):
        assert classify_answers(dict(ALL_FALSE, use_case="2"))["use_case"] == "employment"

    def test_missing_use_case_defaults_to_other(self):
        assert classify_answers(dict(ALL_FALSE))["use_case"] == "other"

    def test_unknown_use_case_rejected(self):
        with pytest.raises(ClassificationError):
            classify_answers(dict(ALL_FALSE, use_case="teleportation"))

    def test_out_of_range_number_rejected(self):
        with pytest.raises(ClassificationError):
            classify_answers(dict(ALL_FALSE, use_case=99))

    def test_every_choice_number_has_a_label_shown_in_the_question(self):
        use_case_text = QUESTIONS_TEXT["use_case"]
        for number, key in CHOICE_MAP.items():
            assert key in CHOICE_LABELS, key
            assert CHOICE_LABELS[key] in use_case_text, key

    def test_choice_numbers_are_contiguous_from_one(self):
        assert sorted(CHOICE_MAP) == list(range(1, len(CHOICE_MAP) + 1))


class TestAnswerNormalization:
    @pytest.mark.parametrize("raw", ["y", "yes", "YES", " true ", "True"])
    def test_truthy_strings(self, raw):
        assert classify_answers(dict(ALL_FALSE, use_case="other", social_scoring=raw))["tier"] == PROHIBITED

    @pytest.mark.parametrize("raw", ["n", "no", "false", "", "  "])
    def test_falsy_strings(self, raw):
        result = classify_answers(dict(ALL_FALSE, use_case="other", social_scoring=raw))
        assert result["tier"] == MINIMAL

    def test_missing_flags_default_to_false(self):
        result = classify_answers({"use_case": "other"})
        assert result["answers"]["facial_scraping"] is False

    def test_garbage_value_rejected(self):
        with pytest.raises(ClassificationError):
            classify_answers(dict(ALL_FALSE, use_case="other", social_scoring="maybe"))

    def test_non_mapping_rejected(self):
        with pytest.raises(ClassificationError):
            classify_answers(["not", "a", "dict"])  # type: ignore[arg-type]


class TestResultShape:
    def test_result_contains_every_documented_key(self):
        result = classify_answers(dict(ALL_FALSE, use_case="chatbot"))
        assert set(result) == {"tier", "reasons", "use_case", "answers", "disclaimer"}

    def test_disclaimer_present_and_non_empty(self):
        result = classify_answers(dict(ALL_FALSE, use_case="other"))
        assert result["disclaimer"] == DISCLAIMER
        assert "NOT legal advice" in result["disclaimer"]

    def test_answers_are_normalized_in_result(self):
        result = classify_answers(dict(ALL_FALSE, use_case=2, rights_or_access="yes"))
        assert result["answers"]["use_case"] == "employment"
        assert result["answers"]["rights_or_access"] is True

    def test_reasons_is_never_empty(self):
        for use_case in ("other", "chatbot", "employment", "fraud_detection"):
            result = classify_answers(dict(ALL_FALSE, use_case=use_case))
            assert result["reasons"], use_case


class TestQuestionnaireDefinition:
    def test_question_keys_are_unique(self):
        keys = [q["key"] for q in QUESTIONS]
        assert len(keys) == len(set(keys))

    def test_all_questions_have_text(self):
        for question in QUESTIONS:
            assert question["text"].strip()

    def test_bool_and_choice_types_present(self):
        types = {q["type"] for q in QUESTIONS}
        assert types == {"bool", "choice"}

    def test_single_choice_question(self):
        assert sum(1 for q in QUESTIONS if q["type"] == "choice") == 1
