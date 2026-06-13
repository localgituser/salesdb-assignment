"""
Observability module for tracking costs and usage across pipeline phases.
Logs to JSONL format with timestamp, phase, model, tokens, cost, etc.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOG_FILE = "data/processed/observability.jsonl"
COST_TRACKING_FILE = "data/processed/cost_tracking.json"


class ObservabilityLogger:
    def __init__(self, log_file: str = LOG_FILE):
        self.log_file = log_file
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        self.total_cost = self._read_total_cost()

    def _read_cost_data(self) -> Dict:
        if os.path.exists(COST_TRACKING_FILE):
            try:
                with open(COST_TRACKING_FILE) as f:
                    return json.load(f)
            except (ValueError, json.JSONDecodeError, FileNotFoundError):
                pass
        return {"total_cost": 0.0, "phases": {}, "last_updated": ""}

    def _read_total_cost(self) -> float:
        return self._read_cost_data()["total_cost"]

    def _write_total_cost(self, phase: str, cost_delta: float) -> None:
        data = self._read_cost_data()
        data["total_cost"] = round(data["total_cost"] + cost_delta, 10)
        data["phases"][phase] = round(data["phases"].get(phase, 0.0) + cost_delta, 10)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(COST_TRACKING_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def log_call(
        self,
        phase: str,
        model: str,
        tokens: int,
        cost: float,
        prompt_version: str,
        outcome: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a single LLM call to JSONL."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "prompt_version": prompt_version,
            "outcome": outcome,
            "metadata": metadata or {},
        }
        self.total_cost += cost
        self._write_total_cost(phase, cost)

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_phase_cost(self, phase: str) -> float:
        """Sum costs for a given phase."""
        if not os.path.exists(self.log_file):
            return 0.0

        total = 0.0
        with open(self.log_file) as f:
            for line in f:
                entry = json.loads(line)
                if entry["phase"] == phase:
                    total += entry["cost"]
        return total

    def check_budget(self, phase: str, budget: float) -> bool:
        """Check if phase cost is within budget."""
        return self.get_phase_cost(phase) <= budget

    @classmethod
    def sync_from_jsonl(cls, log_file: str = LOG_FILE) -> None:
        """Rebuild cost_tracking.json from scratch by scanning observability.jsonl.
        Use for initialization and recovery when cost_tracking.json is missing or stale."""
        if not os.path.exists(log_file):
            return

        total = 0.0
        phases: Dict[str, float] = {}
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                cost = entry.get("cost", 0.0)
                phase = entry.get("phase", "unknown")
                total += cost
                phases[phase] = round(phases.get(phase, 0.0) + cost, 10)

        data = {
            "total_cost": round(total, 10),
            "phases": phases,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        Path(COST_TRACKING_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(COST_TRACKING_FILE, "w") as f:
            json.dump(data, f, indent=2)


logger = ObservabilityLogger()
