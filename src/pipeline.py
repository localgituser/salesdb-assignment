"""
Phase 4 PoC enrichment pipeline.
Cascade: rules → search → Haiku verify → Sonnet fallback.
"""

import logging
import sys

from src.gate import (
    GateFailure,
    check_batch_quality,
    check_cascade_health,
    check_phase4_entry,
    enforce,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

BATCH_PATH = "data/processed/sample_audit.parquet"
ENRICHED_PATH = "data/enriched/poc_enriched_sample.parquet"


def run_phase4() -> None:
    print("=== Phase 4 entry gates ===")
    try:
        enforce(check_phase4_entry(), "phase4_entry")
    except GateFailure as e:
        logger.error(str(e))
        sys.exit(1)

    print("=== Batch quality gates ===")
    try:
        enforce(check_batch_quality(BATCH_PATH), "batch_quality")
    except GateFailure as e:
        logger.error(str(e))
        sys.exit(1)

    # TODO: Stage 1 — deterministic rules (regex, domain reconstruction, blocklist reclassification)
    # TODO: Stage 2 — targeted search/lookup
    # TODO: Stage 3 — Haiku verification of search match
    # TODO: Stage 4 — Sonnet resolution for ambiguous/conflicting cases only
    # Each stage writes enriched records to ENRICHED_PATH with status + stage_resolved + confidence fields.

    print("=== Cascade health gates ===")
    try:
        enforce(check_cascade_health(ENRICHED_PATH), "cascade_health")
    except GateFailure as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Phase 4 complete.")


if __name__ == "__main__":
    run_phase4()
