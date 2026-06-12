"""
Observability module for tracking costs and usage across pipeline phases.
Logs to JSONL format with timestamp, phase, model, tokens, cost, etc.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

LOG_FILE = "data/processed/observability.jsonl"
COST_TRACKING_FILE = "data/processed/cost_tracking.txt"


class ObservabilityLogger:
    def __init__(self, log_file: str = LOG_FILE):
        self.log_file = log_file
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        self.total_cost = self._read_total_cost()

    def _read_total_cost(self) -> float:
        """Read running cost total from tracking file."""
        if os.path.exists(COST_TRACKING_FILE):
            try:
                with open(COST_TRACKING_FILE) as f:
                    return float(f.read().strip())
            except (ValueError, FileNotFoundError):
                return 0.0
        return 0.0

    def _write_total_cost(self) -> None:
        """Write running cost total to tracking file."""
        with open(COST_TRACKING_FILE, "w") as f:
            f.write(str(self.total_cost))

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
            "timestamp": datetime.utcnow().isoformat(),
            "phase": phase,
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "prompt_version": prompt_version,
            "outcome": outcome,
            "metadata": metadata or {},
        }
        self.total_cost += cost
        self._write_total_cost()
        
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


logger = ObservabilityLogger()
