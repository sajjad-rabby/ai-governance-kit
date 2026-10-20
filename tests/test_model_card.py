"""Tests for the model card builder and the bundled YAML subset parser."""

from __future__ import annotations

import pytest

from ai_governance_kit.model_card import ModelCard
from ai_governance_kit.yaml_min import YAMLError, dumps, load_file, loads

CARD_YAML = """
name: churn-classifier
version: 2.1.0
developer: Example Corp
license: Proprietary
summary: Gradient-boosted trees over 90 days of activity.
intended_use: Rank accounts for a human-reviewed retention campaign.
out_of_scope_uses:
  - Credit decisions
  - Automated account closure
training_data:
  rows: 210000
  window: 2024-01 to 2025-06
limitations: Degrades on accounts with fewer than 3 events.
ethical_considerations: Ranking only; never used to deny service.
contact: ml@example.com
"""


class TestModelCardValidation:
    def test_requires_name(self):
        with pytest.raises(ValueError):
            ModelCard(name="", developer="d", intended_use="u")

    def test_requires_developer(self):
        with pytest.raises(ValueError):
            ModelCard(name="n", developer="", intended_use="u")

    def test_requires_intended_use(self):
        with pytest.raises(ValueError):
            ModelCard(name="n", developer="d", intended_use="")


class TestModelCardRoundTrip:
    def test_load_from_yaml(self, tmp_path):
        path = tmp_path / "card.yaml"
        path.write_text(CARD_YAML, encoding="utf-8")
        card = ModelCard.load(str(path))
        assert card.name == "churn-classifier"
        assert card.developer == "Example Corp"
        assert card.out_of_scope_uses == ["Credit decisions", "Automated account closure"]

    def test_to_yaml_round_trips(self, tmp_path, card):
        path = tmp_path / "out.yaml"
        path.write_text(card.to_yaml(), encoding="utf-8")
        reloaded = ModelCard.load(str(path))
        assert reloaded.to_dict() == card.to_dict()

    def test_from_dict_ignores_unknown_keys(self):
        built = ModelCard.from_dict(
            {"name": "n", "developer": "d", "intended_use": "u", "unknown": 1}
        )
        assert built.name == "n"

    def test_load_rejects_non_mapping(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError):
            ModelCard.load(str(path))


class TestModelCardRender:
    def test_renders_title_and_metadata(self, card):
        md = card.render()
        assert md.startswith("# Model Card: churn-classifier")
        assert "**Version:** 2.1.0" in md
        assert "**Developer:** Example Corp" in md
        assert "**License:** Proprietary" in md

    def test_renders_sections_when_present(self, card):
        md = card.render()
        for heading in (
            "## Summary",
            "## Intended Use",
            "## Out-of-Scope Uses",
            "## Training Data",
            "## Evaluation Results",
            "## Limitations",
            "## Ethical Considerations",
        ):
            assert heading in md

    def test_omits_empty_optional_sections(self):
        minimal = ModelCard(name="n", developer="d", intended_use="u")
        md = minimal.render()
        assert "## Summary" not in md
        assert "## Limitations" not in md
        assert "## Intended Use" in md

    def test_evaluation_table_uses_union_of_keys(self):
        card = ModelCard(
            name="n", developer="d", intended_use="u",
            evaluation_results=[{"split": "a", "auc": 0.9}, {"split": "b", "f1": 0.8}],
        )
        md = card.render()
        assert "| split | auc | f1 |" in md

    def test_evaluation_table_handles_missing_cells(self):
        card = ModelCard(
            name="n", developer="d", intended_use="u",
            evaluation_results=[{"split": "a", "auc": 0.9}, {"split": "b"}],
        )
        assert "| b |  |" in card.render()

    def test_evaluation_keys_fallback_when_no_entries(self):
        card = ModelCard(name="n", developer="d", intended_use="u")
        assert card._evaluation_keys() == ["result"]

    def test_lists_out_of_scope_uses(self, card):
        assert "- Credit decisions" in card.render()

    def test_training_data_rendered_as_bullets(self, card):
        assert "- **rows:** 210000" in card.render()

    def test_save_markdown_writes_file(self, card, tmp_path):
        out = tmp_path / "card.md"
        card.save_markdown(str(out))
        assert out.read_text(encoding="utf-8").startswith("# Model Card:")


class TestYamlSubset:
    def test_parses_scalars(self):
        assert loads("a: 1\nb: text\nc: true\nd: 1.5\n") == {
            "a": 1, "b": "text", "c": True, "d": 1.5
        }

    def test_parses_null(self):
        assert loads("a: null\nb: ~\n") == {"a": None, "b": None}

    def test_parses_block_list(self):
        assert loads("items:\n  - one\n  - two\n") == {"items": ["one", "two"]}

    def test_parses_flow_list(self):
        assert loads("items: [one, two]\n") == {"items": ["one", "two"]}

    def test_parses_nested_mapping(self):
        assert loads("a:\n  b:\n    c: 1\n") == {"a": {"b": {"c": 1}}}

    def test_strips_comments(self):
        assert loads("a: 1  # note\n") == {"a": 1}

    def test_empty_document_is_none(self):
        assert loads("") is None

    def test_bare_scalar_document(self):
        assert loads("just a scalar\n") == "just a scalar"

    def test_quotes_preserved(self):
        assert loads("a: '1'\n") == {"a": "1"}

    def test_dump_load_round_trip(self):
        original = {"name": "x", "count": 3, "flag": True, "items": ["a", "b"]}
        assert loads(dumps(original)) == original

    def test_nested_dump_round_trip(self):
        original = {"outer": {"inner": {"leaf": 7}}, "list": [1, 2]}
        assert loads(dumps(original)) == original

    def test_dumps_emits_trailing_newline(self):
        assert dumps({"a": 1}).endswith("\n")

    def test_tab_indentation_rejected(self):
        with pytest.raises(YAMLError):
            loads("a:\n\tb: 1\n")

    def test_line_without_colon_inside_mapping_rejected(self):
        with pytest.raises(YAMLError):
            loads("a: 1\nnot a key value line\n")

    def test_load_file(self, tmp_path):
        path = tmp_path / "x.yaml"
        path.write_text("a: 1\n", encoding="utf-8")
        assert load_file(str(path)) == {"a": 1}

    def test_load_file_missing_raises(self, tmp_path):
        with pytest.raises(OSError):
            load_file(str(tmp_path / "nope.yaml"))

    def test_dump_needs_quotes_for_ambiguous_strings(self):
        text = dumps({"a": "1"})
        assert loads(text) == {"a": "1"}
