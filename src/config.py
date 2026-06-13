"""Typed loader for config/project.yaml — single source of truth for project parameters.

Usage:
    from src.config import CONFIG
    CONFIG.budget.total_usd          # 10.00
    CONFIG.gap_tiers.high_gap_max    # 0.10
    CONFIG.market.enrichable_size_bands  # frozenset of size band strings
    CONFIG.market.subregion_label    # "state"
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "project.yaml"


class Budget(BaseModel):
    total_usd: float
    per_phase_usd: Dict[str, float]


class ModelPricing(BaseModel):
    input: float
    output: float


class Models(BaseModel):
    classification: str
    judgment: str
    pricing_per_mtok: Dict[str, ModelPricing]


class GapTiers(BaseModel):
    high_gap_max: float
    moderate_gap_max: float

    def classify(self, ratio: float) -> str:
        if ratio < self.high_gap_max:
            return "HIGH_GAP"
        if ratio < self.moderate_gap_max:
            return "MODERATE_GAP"
        return "ADEQUATE"


class GeographyTiering(BaseModel):
    tier_a_min: int
    tier_b_min: int

    def tier(self, n: int) -> str:
        if n >= self.tier_a_min:
            return "A"
        if n >= self.tier_b_min:
            return "B"
        return "C"


class Cascade(BaseModel):
    batch_min: int
    batch_max: int
    stage4_cost_signal: float
    confidence_threshold: float
    confidence_calibration_target: float


class Eval(BaseModel):
    ground_truth_size_min: int
    ground_truth_size_max: int
    spot_check_n_per_gap: int


class EnrichmentRules(BaseModel):
    platform_blocklist: List[str]

    @property
    def platform_blocklist_set(self) -> FrozenSet[str]:
        return frozenset(self.platform_blocklist)


class Comparator(BaseModel):
    source: str
    vintage: int
    path: str


class MarketDataset(BaseModel):
    parquet: str
    sample: str
    primary_key: str


class MarketComparators(BaseModel):
    employer: Optional[Comparator] = None
    nonemployer: Optional[Comparator] = None


class Market(BaseModel):
    name: str
    subregion_label: str
    dataset: MarketDataset
    comparators: MarketComparators
    enrichable_size_bands: List[str]
    excluded_subregions: List[str] = Field(default_factory=list)
    excluded_territories: List[str] = Field(default_factory=list)

    @property
    def enrichable_size_bands_set(self) -> FrozenSet[str]:
        return frozenset(self.enrichable_size_bands)


class ProjectConfig(BaseModel):
    budget: Budget
    models: Models
    gap_tiers: GapTiers
    geography_tiering: GeographyTiering
    cascade: Cascade
    eval: Eval
    enrichment_rules: EnrichmentRules
    market: Market


@lru_cache(maxsize=1)
def load_config(path: Path = CONFIG_PATH) -> ProjectConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    active = raw["market"]["active"]
    if active not in raw["markets"]:
        raise ValueError(f"market.active='{active}' not found under markets")

    flattened = {
        "budget": raw["budget"],
        "models": raw["models"],
        "gap_tiers": raw["gap_tiers"],
        "geography_tiering": raw["geography_tiering"],
        "cascade": raw["cascade"],
        "eval": raw["eval"],
        "enrichment_rules": raw["enrichment_rules"],
        "market": raw["markets"][active],
    }
    return ProjectConfig(**flattened)


CONFIG = load_config()
