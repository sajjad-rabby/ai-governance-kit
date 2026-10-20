"""Tests for the NIST AI RMF risk register."""

from __future__ import annotations

import json

import pytest

from ai_governance_kit.risk_register import (
    AI_RMF_FUNCTIONS,
    MITIGATION_SEPARATOR,
    Register,
    Risk,
    RiskError,
    band_for,
)


class TestBandFor:
    def test_documented_boundaries(self):
        """The documented contract is Low <5, Medium 5-11, High 12-19, Critical 20-25."""
        assert band_for(0) == "Low"
        assert band_for(4) == "Low"
        assert band_for(5) == "Medium"
        assert band_for(11) == "Medium"
        assert band_for(12) == "High"
        assert band_for(19) == "High"
        assert band_for(20) == "Critical"
        assert band_for(25) == "Critical"

    def test_rejects_out_of_range(self):
        with pytest.raises(RiskError):
            band_for(-1)
        with pytest.raises(RiskError):
            band_for(26)

    def test_rejects_non_int(self):
        with pytest.raises(RiskError):
            band_for(4.5)  # type: ignore[arg-type]
        with pytest.raises(RiskError):
            band_for(True)  # type: ignore[arg-type]


class TestRiskValidation:
    def test_valid_risk_scores(self, sample_risks):
        assert sample_risks[0].score == 16
        assert sample_risks[3].score == 1

    def test_bands_reachable_from_severity_likelihood(self):
        assert Risk(
            id="X", title="t", description="d", ai_rmf_function="Map",
            category="c", severity=4, likelihood=1,
        ).band == "Low"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("id", ""),
            ("title", ""),
            ("description", "  "),
            ("ai_rmf_function", "NotAFunction"),
            ("severity", 0),
            ("likelihood", 6),
            ("severity", True),
        ],
    )
    def test_invalid_fields_rejected(self, field, value):
        kwargs = dict(
            id="X", title="t", description="d", ai_rmf_function="Map",
            category="c", severity=3, likelihood=3,
        )
        kwargs[field] = value
        with pytest.raises(RiskError):
            Risk(**kwargs)

    def test_mitigations_must_be_strings(self):
        with pytest.raises(RiskError):
            Risk(
                id="X", title="t", description="d", ai_rmf_function="Map",
                category="c", severity=3, likelihood=3, mitigations=[1, 2],
            )

    def test_roundtrip_dict(self, sample_risks):
        risk = sample_risks[0]
        assert Risk.from_dict(risk.to_dict()).to_dict() == risk.to_dict()

    def test_from_dict_missing_field(self):
        with pytest.raises(RiskError) as exc:
            Risk.from_dict({"id": "X"})
        assert "missing required field" in str(exc.value)


class TestRegister:
    def test_sorted_by_score_descending(self, register):
        scores = [r.score for r in register.sorted_by_score()]
        assert scores == sorted(scores, reverse=True)

    def test_duplicate_ids_rejected(self, sample_risks):
        reg = Register()
        reg.add(sample_risks[0])
        with pytest.raises(RiskError):
            reg.add(sample_risks[0])

    def test_get_returns_none_when_missing(self, register):
        assert register.get("R-999") is None

    def test_summary_counts_every_band(self, register):
        # scores are 16, 15, 6, 1 -> High, High, Medium, Low
        summary = register.summary()
        assert summary["total"] == 4
        assert summary["Critical"] == 0
        assert summary["High"] == 2
        assert summary["Medium"] == 1
        assert summary["Low"] == 1
        assert sum(summary[b] for b in ("Critical", "High", "Medium", "Low")) == 4

    def test_by_band_keys(self, register):
        assert set(register.by_band()) == {"Critical", "High", "Medium", "Low"}

    def test_json_roundtrip(self, register, tmp_path):
        path = register.save_json(tmp_path / "reg.json")
        assert Register.load_json(path).to_json() == register.to_json()

    def test_csv_roundtrip_preserves_mitigations(self, register, tmp_path):
        path = register.save_csv(tmp_path / "reg.csv")
        reloaded = Register.load_csv(path)
        assert len(reloaded.risks) == 4
        assert reloaded.get("R-001").mitigations == [
            "Record dataset lineage",
            "Publish a data statement",
        ]

    def test_csv_mitigation_separator_joins(self, register, tmp_path):
        text = register.to_csv()
        # R-001 is the only risk with more than one mitigation.
        assert text.count(MITIGATION_SEPARATOR) == 1

    def test_csv_header_has_expected_columns(self, register):
        header = register.to_csv().splitlines()[0]
        assert header.split(",")[:3] == ["id", "title", "description"]

    def test_load_json_rejects_bad_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RiskError):
            Register.load_json(path)

    def test_load_json_rejects_non_array(self, tmp_path):
        path = tmp_path / "obj.json"
        path.write_text(json.dumps({"id": "X"}), encoding="utf-8")
        with pytest.raises(RiskError):
            Register.load_json(path)

    def test_markdown_groups_by_rmf_function(self, register):
        md = register.render_markdown("Demo Register")
        assert md.startswith("# Demo Register")
        for function in AI_RMF_FUNCTIONS:
            assert f"## {function}" in md
        assert "R-001" in md
        assert "Total risks: 4" in md

    def test_markdown_lists_mitigations(self, register):
        assert "- Record dataset lineage" in register.render_markdown()

    def test_markdown_omits_absent_function_sections(self, register):
        md = register.render_markdown()
        for risk in register.risks:
            assert risk.ai_rmf_function in md


class TestEmptyRegister:
    def test_empty_is_valid(self):
        reg = Register()
        assert reg.risks == []
        assert reg.summary()["total"] == 0

    def test_empty_markdown_still_renders(self):
        assert "Total risks: 0" in Register().render_markdown()
