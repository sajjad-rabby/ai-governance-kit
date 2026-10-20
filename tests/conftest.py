"""Shared fixtures for the ai-governance-kit test suite."""

from __future__ import annotations

import pytest

from ai_governance_kit.model_card import ModelCard
from ai_governance_kit.risk_register import Register, Risk


@pytest.fixture
def sample_risks() -> list:
    """Four risks spanning every severity band."""
    return [
        Risk(
            id="R-001",
            title="Training data provenance undocumented",
            description="No record of which datasets trained the model.",
            ai_rmf_function="Map",
            category="Data governance",
            severity=4,
            likelihood=4,
            mitigations=["Record dataset lineage", "Publish a data statement"],
            owner="Data team",
        ),
        Risk(
            id="R-002",
            title="No drift monitoring in production",
            description="Accuracy decay would go unnoticed.",
            ai_rmf_function="Measure",
            category="Monitoring",
            severity=5,
            likelihood=3,
            mitigations=["Schedule weekly drift checks"],
            owner="MLOps",
        ),
        Risk(
            id="R-003",
            title="Third-party model terms unclear",
            description="Upstream licence may forbid our use.",
            ai_rmf_function="Govern",
            category="Legal",
            severity=3,
            likelihood=2,
            mitigations=["Obtain written permission"],
            owner="Legal",
        ),
        Risk(
            id="R-004",
            title="Minor UI copy issue",
            description="A tooltip truncates on small screens.",
            ai_rmf_function="Manage",
            category="Usability",
            severity=1,
            likelihood=1,
            mitigations=["Widen the tooltip"],
            owner="Frontend",
        ),
    ]


@pytest.fixture
def register(sample_risks) -> Register:
    return Register(sample_risks)


@pytest.fixture
def card() -> ModelCard:
    return ModelCard(
        name="churn-classifier",
        developer="Example Corp",
        intended_use="Rank accounts for a human-reviewed retention campaign.",
        version="2.1.0",
        license="Proprietary",
        summary="Gradient-boosted trees over 90 days of account activity.",
        out_of_scope_uses=["Credit decisions", "Automated account closure"],
        training_data={"rows": 210_000, "window": "2024-01 to 2025-06"},
        evaluation_results=[
            {"split": "holdout", "roc_auc": 0.87, "n": 20_000},
            {"split": "temporal", "roc_auc": 0.82, "n": 20_000},
        ],
        limitations="Degrades on accounts with fewer than 3 events.",
        ethical_considerations="Never used to deny service; ranking only.",
        contact="ml@example.com",
    )
