"""Risk register entries and banded risk scoring.

Score is likelihood x severity on 1-5 scales, banded as:
Low: 1 <= score <= 4
Medium: 5 <= score <= 9
High: 10 <= score <= 15
Critical: 20 <= score <= 25
  Low:      score < 5
  Medium:   5 <= score <= 11
  High:     12 <= score <= 19
  Critical: 20 <= score <= 25
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

AI_RMF_FUNCTIONS = ("Govern", "Map", "Measure", "Manage")

_LOW_MAX = 4
_MEDIUM_MAX = 11
_HIGH_MAX = 19

MITIGATION_SEPARATOR = " | "


class RiskError(ValueError):
    """Raised when a risk record is invalid."""


def band_for(score: int) -> str:
    """Return the risk band for a severity*likelihood score."""
    if isinstance(score, bool) or not isinstance(score, int):
        raise RiskError(f"score must be an int, got {type(score).__name__}")
    if score < 0 or score > 25:
        raise RiskError(f"score {score} outside valid range 0-25")
    if score <= _LOW_MAX:
        return "Low"
    if score <= _MEDIUM_MAX:
        return "Medium"
    if score <= _HIGH_MAX:
        return "High"
    return "Critical"


@dataclass
class Risk:
    """A single risk entry in the AI RMF register."""

    id: str
    title: str
    description: str
    ai_rmf_function: str
    category: str
    severity: int
    likelihood: int
    mitigations: List[str] = field(default_factory=list)
    owner: str = "Unassigned"
    status: str = "Open"

    def __post_init__(self) -> None:
        """Validate the risk scores assigned at construction time.

        Raises:
            ValueError: when likelihood or severity falls outside 1-5.
        """
        self.validate()

    def validate(self) -> None:
        """Check every field required by the risk-register schema.

        Raises:
            RiskError: when a required field is missing or out of range.
        """
        if not isinstance(self.id, str) or not self.id.strip():
            raise RiskError("risk id must be a non-empty string")
        if not isinstance(self.title, str) or not self.title.strip():
            raise RiskError(f"risk {self.id}: title must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise RiskError(f"risk {self.id}: description must be a non-empty string")
        if self.ai_rmf_function not in AI_RMF_FUNCTIONS:
            raise RiskError(
                f"risk {self.id}: ai_rmf_function must be one of "
                f"{', '.join(AI_RMF_FUNCTIONS)}; got {self.ai_rmf_function!r}"
            )
        for name in ("severity", "likelihood"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise RiskError(f"risk {self.id}: {name} must be an int 1-5; got {value!r}")
        if not isinstance(self.mitigations, list) or not all(
            isinstance(item, str) for item in self.mitigations
        ):
            raise RiskError(f"risk {self.id}: mitigations must be a list of strings")

    @property
    def score(self) -> int:
        """severity * likelihood."""
        return self.severity * self.likelihood

    @property
    def band(self) -> str:
        """Return the qualitative band for this risk.

        Returns:
            One of ``low``, ``medium``, ``high`` or ``critical``.
        """
        return band_for(self.score)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible mapping including the derived band.

        Returns:
            JSON-compatible mapping including the derived band.
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "ai_rmf_function": self.ai_rmf_function,
            "category": self.category,
            "severity": self.severity,
            "likelihood": self.likelihood,
            "mitigations": list(self.mitigations),
            "owner": self.owner,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Risk":
        """Reconstruct a :class:`Risk` from a mapping.

        Args:
            data: Mapping as produced by :meth:`to_dict`.

        Returns:
            The reconstructed :class:`Risk`.

        Raises:
            KeyError: when a required field is absent.
        """
        if not isinstance(data, dict):
            raise RiskError("risk record must be a mapping")
        try:
            return cls(
                id=data["id"],
                title=data["title"],
                description=data["description"],
                ai_rmf_function=data["ai_rmf_function"],
                category=data["category"],
                severity=data["severity"],
                likelihood=data["likelihood"],
                mitigations=list(data.get("mitigations", [])),
                owner=data.get("owner", "Unassigned"),
                status=data.get("status", "Open"),
            )
        except KeyError as exc:
            raise RiskError(f"risk record missing required field: {exc.args[0]}") from exc
        except TypeError as exc:
            raise RiskError(f"invalid risk record: {exc}") from exc


class Register:
    """An ordered collection of risks backed by JSON (and optionally CSV)."""

    def __init__(self, risks: Optional[Iterable[Risk]] = None) -> None:
        """Create a register, copying the initial risks.

        Args:
            risks: Initial risks, copied into the register.
        """
        self.risks: List[Risk] = list(risks) if risks else []
        self._validate_unique_ids()

    @staticmethod
    def _validate_unique_ids(risks: Optional[Iterable[Risk]] = None) -> None:
        target = list(risks) if risks is not None else None
        if target is None:
            return
        seen: set[str] = set()
        for risk in target:
            if risk.id in seen:
                raise RiskError(f"duplicate risk id: {risk.id}")
            seen.add(risk.id)

    def _check_unique_on_add(self, risk: Risk) -> None:
        if any(existing.id == risk.id for existing in self.risks):
            raise RiskError(f"duplicate risk id: {risk.id}")

    def add(self, risk: Risk) -> Risk:
        """Add a risk, enforcing unique ids."""
        self._check_unique_on_add(risk)
        self.risks.append(risk)
        return risk

    def get(self, risk_id: str) -> Optional[Risk]:
        """Find a risk by its identifier.

        Args:
            risk_id: Identifier to find.

        Returns:
            The matching :class:`Risk`, or ``None`` when absent.
        """
        for risk in self.risks:
            if risk.id == risk_id:
                return risk
        return None

    def sorted_by_score(self) -> List[Risk]:
        """Risks ordered by descending score, then id for determinism."""
        return sorted(self.risks, key=lambda r: (-r.score, r.id))

    def by_band(self) -> Dict[str, List[Risk]]:
        """Group risks by their qualitative band.

        Returns:
            Mapping of band name to the risks in it.
        """
        bands: Dict[str, List[Risk]] = {"Critical": [], "High": [], "Medium": [], "Low": []}
        for risk in self.sorted_by_score():
            bands[risk.band].append(risk)
        return bands

    def summary(self) -> Dict[str, int]:
        """Summarize risk counts by band.

        Returns:
            Mapping of band name to how many risks it contains.
        """
        counts = {band: 0 for band in ("Critical", "High", "Medium", "Low")}
        for risk in self.risks:
            counts[risk.band] += 1
        counts["total"] = len(self.risks)
        return counts

    def to_json(self) -> str:
        """Serialize the register to indented JSON.

        Returns:
            Indented JSON with sorted keys.
        """
        return json.dumps(
            [risk.to_dict() for risk in self.risks],
            indent=2,
            ensure_ascii=False,
        ) + "\n"

    def save_json(self, path: str | Path) -> Path:
        """Write the register to a JSON file.

        Args:
            path: Destination file.

        Returns:
            The path that was written.
        """
        path = Path(path)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load_json(cls, path: str | Path) -> "Register":
        """Load a register from a JSON file.

        Args:
            path: JSON file to read.

        Returns:
            A populated :class:`RiskRegister`.
        """
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RiskError(f"{path}: invalid JSON ({exc})") from exc
        if not isinstance(data, list):
            raise RiskError(f"{path}: expected a JSON array of risk records")
        risks = [Risk.from_dict(item) for item in data]
        register = cls()
        for risk in risks:
            register._check_unique_on_add(risk)
            register.risks.append(risk)
        return register

    def to_csv(self) -> str:
        """Return the register as a CSV string.

Useful

        Mirrors :meth:`save_csv` but returns the text instead of writing it,
        so callers can stream it to stdout or embed it elsewhere.
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "title",
                "description",
                "ai_rmf_function",
                "category",
                "severity",
                "likelihood",
                "score",
                "band",
                "mitigations",
                "owner",
                "status",
            ]
        )
        for risk in self.risks:
            writer.writerow(
                [
                    risk.id,
                    risk.title,
                    risk.description,
                    risk.ai_rmf_function,
                    risk.category,
                    risk.severity,
                    risk.likelihood,
                    risk.score,
                    risk.band,
                    MITIGATION_SEPARATOR.join(risk.mitigations),
                    risk.owner,
                    risk.status,
                ]
            )
        return buffer.getvalue()

    def save_csv(self, path: str | Path) -> Path:
        """Write the register to a CSV file.

        Args:
            path: Destination file.

        Returns:
            The path that was written.
        """
        path = Path(path)
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(self.to_csv())
        return path

    @classmethod
    def load_csv(cls, path: str | Path) -> "Register":
        """Load a register from a CSV file.

        Args:
            path: CSV file to read.

        Returns:
            A populated :class:`RiskRegister`.
        """
        path = Path(path)
        risks: List[Risk] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                mitigations_raw = row.get("mitigations", "") or ""
                mitigations = (
                    [part for part in mitigations_raw.split(MITIGATION_SEPARATOR) if part]
                    if "mitigations" in row
                    else []
                )
                risk = Risk(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    ai_rmf_function=row["ai_rmf_function"],
                    category=row["category"],
                    severity=int(row["severity"]),
                    likelihood=int(row["likelihood"]),
                    mitigations=mitigations,
                    owner=row.get("owner") or "Unassigned",
                    status=row.get("status") or "Open",
                )
                risks.append(risk)
        register = cls()
        for risk in risks:
            register._check_unique_on_add(risk)
            register.risks.append(risk)
        return register

    def render_markdown(self, title: str = "AI Risk Register") -> str:
        """Markdown report grouped by NIST AI RMF function, sorted by score."""
        lines: List[str] = [f"# {title}", ""]
        summary = self.summary()
        lines.append(
            "Total risks: {total} - Critical: {critical}, High: {high}, "
            "Medium: {medium}, Low: {low}".format(
                total=summary["total"],
                critical=summary["Critical"],
                high=summary["High"],
                medium=summary["Medium"],
                low=summary["Low"],
            )
        )
        lines.append("")
        for function in AI_RMF_FUNCTIONS:
            function_risks = [r for r in self.sorted_by_score() if r.ai_rmf_function == function]
            if not function_risks:
                continue
            lines.append(f"## {function}")
            lines.append("")
            for risk in function_risks:
                lines.append(f"### {risk.id} — {risk.title}")
                lines.append("")
                lines.append(f"- **Band:** {risk.band} (score {risk.score})")
                lines.append(f"- **Category:** {risk.category}")
                lines.append(f"- **Severity:** {risk.severity}/5  **Likelihood:** {risk.likelihood}/5")
                lines.append(f"- **Owner:** {risk.owner}")
                lines.append(f"- **Status:** {risk.status}")
                lines.append("")
                lines.append(risk.description)
                lines.append("")
                if risk.mitigations:
                    lines.append("**Mitigations:**")
                    lines.append("")
                    for mitigation in risk.mitigations:
                        lines.append(f"- {mitigation}")
                    lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def save_markdown(self, path: str | Path, title: str = "AI Risk Register") -> Path:
        """Save the register as a Markdown report.

        Args:
            path: Destination file.
            title: Heading placed above the table.

        Returns:
            The path that was written.
        """
        path = Path(path)
        path.write_text(self.render_markdown(title), encoding="utf-8")
        return path
