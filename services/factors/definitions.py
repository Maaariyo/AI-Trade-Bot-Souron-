"""Load and validate definitions.yaml and presets.yaml."""

import hashlib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml

HERE = Path(__file__).parent
DEFINITIONS_PATH = HERE / "definitions.yaml"
PRESETS_PATH = HERE / "presets.yaml"

Direction = Literal["higher", "lower"]
AppliesTo = Literal["all", "non_financial", "financial", "bank"]
Normalise = Literal["rank", "absolute"]
FinancialType = Literal["NONE", "BANK", "NBFC"]


@dataclass(frozen=True)
class FactorDef:
    key: str
    family: str
    direction: Direction
    applies_to: AppliesTo
    formula: str
    normalise: Normalise = "rank"

    def applies(self, financial_type: str) -> bool:
        if self.applies_to == "all":
            return True
        if self.applies_to == "non_financial":
            return financial_type == "NONE"
        if self.applies_to == "financial":
            return financial_type in ("BANK", "NBFC")
        return financial_type == "BANK"


@dataclass(frozen=True)
class Definitions:
    families: tuple[str, ...]
    factors: tuple[FactorDef, ...]
    fields: dict[str, tuple[str, ...]]
    financial_types: dict[str, tuple[str, ...]]
    sha256: str

    def by_key(self) -> dict[str, FactorDef]:
        return {f.key: f for f in self.factors}


@dataclass(frozen=True)
class Gates:
    min_median_value_crore: float = 5
    min_mcap_crore: float = 500
    min_quarters: int = 8
    exclude_gsm: bool = True
    exclude_asm: bool = False
    min_price_observations: int = 20


@dataclass(frozen=True)
class Presets:
    presets: dict[str, dict[str, float]]
    default: str
    gates: Gates
    agent_weights: dict[str, float]
    coverage_min: float
    min_group_size: int
    extra: dict[str, Any] = field(default_factory=dict)


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(f"definitions: {msg}")


@cache
def load_definitions(path: Path = DEFINITIONS_PATH) -> Definitions:
    raw_text = path.read_bytes()
    raw = yaml.safe_load(raw_text)
    families = tuple(raw["families"])
    factors: list[FactorDef] = []
    seen: set[str] = set()
    for f in raw["factors"]:
        defn = FactorDef(
            key=f["key"],
            family=f["family"],
            direction=f["direction"],
            applies_to=f["applies_to"],
            formula=f["formula"],
            normalise=f.get("normalise", "rank"),
        )
        _check(defn.key not in seen, f"duplicate factor {defn.key}")
        _check(defn.family in families, f"{defn.key}: unknown family {defn.family}")
        _check(defn.direction in ("higher", "lower"), f"{defn.key}: bad direction")
        _check(
            defn.applies_to in ("all", "non_financial", "financial", "bank"),
            f"{defn.key}: bad applies_to",
        )
        _check(defn.normalise in ("rank", "absolute"), f"{defn.key}: bad normalise")
        seen.add(defn.key)
        factors.append(defn)
    for fam in families:
        _check(any(f.family == fam for f in factors), f"family {fam} has no factors")
    return Definitions(
        families=families,
        factors=tuple(factors),
        fields={k: tuple(v) for k, v in raw["fields"].items()},
        financial_types={k: tuple(v) for k, v in raw["financial_types"].items()},
        sha256=hashlib.sha256(raw_text).hexdigest(),
    )


@cache
def load_presets(path: Path = PRESETS_PATH) -> Presets:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    families = load_definitions().families
    presets = {name: {k: float(v) for k, v in w.items()} for name, w in raw["presets"].items()}
    for name, weights in presets.items():
        _check(set(weights) == set(families), f"preset {name} must weight every family")
        _check(all(0 <= v <= 10 for v in weights.values()), f"preset {name}: weights are 0-10")
    _check(raw["default_preset"] in presets, "default_preset is not a preset")
    return Presets(
        presets=presets,
        default=raw["default_preset"],
        gates=Gates(**raw["gates"]),
        agent_weights={k: float(v) for k, v in raw["agent_weights"].items()},
        coverage_min=float(raw["coverage_min"]),
        min_group_size=int(raw["min_group_size"]),
    )


def classify_financial_type(industry: str | None, sector: str | None) -> FinancialType:
    """BANK, NBFC or NONE from the classification text (definitions.yaml rules)."""
    rules = load_definitions().financial_types
    for text in (industry, sector):
        if not text:
            continue
        lowered = text.lower()
        for kind in ("BANK", "NBFC"):
            if any(word in lowered for word in rules.get(kind, ())):
                return kind
    return "NONE"
