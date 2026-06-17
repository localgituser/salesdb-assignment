"""
Part 4 eval runner. Computes precision/recall against hand-labeled ground truth.
No LLM calls — deterministic only.

Metrics computed per field (website, type, industry, size) and per segment:
  Precision = TP / (TP + FP)   — of pipeline-filled values, what fraction are correct?
  Recall    = TP / (TP + FN)   — of ground-truth values, what fraction did we fill correctly?
  F1        = 2 * P * R / (P + R)

Website comparison: normalized (strip protocol, www, trailing slash) case-insensitive.
Other fields: exact case-insensitive match.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GROUND_TRUTH_PATH = ROOT / "evals/ground_truth.json"
ENRICHED_PATH = ROOT / "data/enriched/part4_enriched_sample.parquet"
FIELDS = ["website", "type", "industry", "size"]

SIZE_BANDS = ["1-10", "11-50", "51-200", "201-500", "501-1K", "1K-5K", "5K-10K", "10K+"]

# Confidence calibration: at this threshold, what fraction of predictions are correct?
CONFIDENCE_CALIBRATION_THRESHOLD = 0.80


def size_band_distance(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """Ordinal distance between two size bands. None if either is not in the enum."""
    if a is None or b is None:
        return None
    try:
        return abs(SIZE_BANDS.index(a) - SIZE_BANDS.index(b))
    except ValueError:
        return None


def normalize_domain(url: Optional[str]) -> Optional[str]:
    """Normalize URL to bare domain for comparison."""
    if not url or not isinstance(url, str) or not url.strip():
        return None
    d = (url.lower().strip()
         .removeprefix("https://")
         .removeprefix("http://")
         .removeprefix("www."))
    return d.split("/")[0].split("?")[0].rstrip(".") or None


def normalize_field(field: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if field == "website":
        return normalize_domain(value)
    return value.strip().lower() if isinstance(value, str) else None


def compute_metrics(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
    }


def run_eval() -> dict:
    if not GROUND_TRUTH_PATH.exists():
        print(f"ERROR: Ground truth not found at {GROUND_TRUTH_PATH}")
        sys.exit(1)

    if not ENRICHED_PATH.exists():
        print(f"ERROR: Enriched output not found at {ENRICHED_PATH}")
        sys.exit(1)

    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = json.load(f)

    if not ground_truth:
        print("ERROR: ground_truth.json is empty — hand-label records before running eval.")
        sys.exit(1)

    # Load enriched output
    con = duckdb.connect()
    enriched_df = con.execute(f"SELECT * FROM parquet_scan('{ENRICHED_PATH}')").df()
    enriched = {row["handle"]: row for _, row in enriched_df.iterrows()}

    # Per-field counters
    counters: dict[str, dict[str, int]] = {
        f: {"tp": 0, "fp": 0, "fn": 0} for f in FIELDS
    }
    # Per-segment counters
    seg_counters: dict[str, dict[str, dict[str, int]]] = {}
    # Ordinal size tracking: within-1-band counts as near-correct
    size_within_one: int = 0
    size_total_mismatches: int = 0
    size_band_distances: list[int] = []
    # Confidence calibration: at >= CONFIDENCE_CALIBRATION_THRESHOLD, what % are correct?
    calib_counters: dict[str, dict[str, int]] = {
        f: {"high_conf_correct": 0, "high_conf_total": 0} for f in FIELDS
    }

    matched = 0
    unmatched_handles = []
    mismatches: list[dict] = []

    for gt_record in ground_truth:
        handle = gt_record["handle"]
        gt_values = gt_record.get("ground_truth", {})
        segment = gt_record.get("segment", "unknown")

        if handle not in enriched:
            unmatched_handles.append(handle)
            continue
        matched += 1

        pred = enriched[handle]
        if segment not in seg_counters:
            seg_counters[segment] = {f: {"tp": 0, "fp": 0, "fn": 0} for f in FIELDS}

        for field in FIELDS:
            if field not in gt_values:
                continue  # No ground truth for this field — skip

            gt_val = normalize_field(field, gt_values[field])
            pred_val = normalize_field(field, pred.get(f"{field}_final"))

            if gt_val is None and pred_val is None:
                pass  # TN — not counted in precision/recall
            elif gt_val is None and pred_val is not None:
                counters[field]["fp"] += 1
                seg_counters[segment][field]["fp"] += 1
            elif gt_val is not None and pred_val is None:
                counters[field]["fn"] += 1
                seg_counters[segment][field]["fn"] += 1
                mismatches.append({
                    "handle": handle, "field": field,
                    "gt": gt_values[field], "pred": None, "segment": segment,
                })
            elif gt_val == pred_val:
                counters[field]["tp"] += 1
                seg_counters[segment][field]["tp"] += 1
            else:
                counters[field]["fp"] += 1
                counters[field]["fn"] += 1
                seg_counters[segment][field]["fp"] += 1
                seg_counters[segment][field]["fn"] += 1
                dist = size_band_distance(gt_values[field], pred.get(f"{field}_final")) if field == "size" else None
                mismatches.append({
                    "handle": handle, "field": field,
                    "gt": gt_values[field], "pred": pred.get(f"{field}_final"),
                    "segment": segment,
                    **({"band_distance": dist} if dist is not None else {}),
                })
                if field == "size" and gt_val is not None and pred_val is not None:
                    size_total_mismatches += 1
                    if dist is not None:
                        size_band_distances.append(dist)
                        if dist <= 1:
                            size_within_one += 1

            # Confidence calibration: track high-confidence predictions
            conf_raw = pred.get(f"{field}_confidence")
            if conf_raw is not None:
                try:
                    conf_val = float(conf_raw)
                except (TypeError, ValueError):
                    conf_val = None
                if conf_val is not None and conf_val >= CONFIDENCE_CALIBRATION_THRESHOLD:
                    if gt_val is not None and pred_val is not None:
                        calib_counters[field]["high_conf_total"] += 1
                        if gt_val == pred_val:
                            calib_counters[field]["high_conf_correct"] += 1

    # Build results
    field_metrics = {f: compute_metrics(**counters[f]) for f in FIELDS}
    seg_metrics = {
        seg: {f: compute_metrics(**seg_counters[seg][f]) for f in FIELDS}
        for seg in seg_counters
    }

    # Overall (macro-average across fields)
    overall_p = [m["precision"] for m in field_metrics.values() if m["precision"] is not None]
    overall_r = [m["recall"] for m in field_metrics.values() if m["recall"] is not None]
    macro_precision = round(sum(overall_p) / len(overall_p), 3) if overall_p else None
    macro_recall = round(sum(overall_r) / len(overall_r), 3) if overall_r else None
    if macro_precision and macro_recall and (macro_precision + macro_recall) > 0:
        macro_f1 = round(2 * macro_precision * macro_recall / (macro_precision + macro_recall), 3)
    else:
        macro_f1 = None

    avg_band_dist = round(sum(size_band_distances) / len(size_band_distances), 2) if size_band_distances else None

    # Confidence calibration summary
    calibration: dict = {}
    for field in FIELDS:
        total = calib_counters[field]["high_conf_total"]
        correct = calib_counters[field]["high_conf_correct"]
        calibration[field] = {
            "high_conf_count": total,
            "high_conf_correct": correct,
            "calibration_rate": round(correct / total, 3) if total > 0 else None,
        }

    # Source data reliability: original_correct breakdown by field × poc_segment
    all_segments = sorted(seg_counters.keys())
    source_reliability: dict = {}
    for field in FIELDS:
        col = f"{field}_original_correct"
        if col not in enriched_df.columns:
            continue
        source_reliability[field] = {}
        for seg in all_segments:
            sub = enriched_df[enriched_df["poc_segment"] == seg][col] if "poc_segment" in enriched_df.columns else enriched_df[col]
            correct = int((sub == True).sum())   # noqa: E712
            incorrect = int((sub == False).sum())  # noqa: E712
            unknown = int(sub.isna().sum())
            total = correct + incorrect
            source_reliability[field][seg] = {
                "correct": correct,
                "incorrect": incorrect,
                "unknown": unknown,
                "reliability": round(correct / total, 3) if total > 0 else None,
            }

    results = {
        "summary": {
            "ground_truth_records": len(ground_truth),
            "enriched_records_matched": matched,
            "unmatched_handles": unmatched_handles,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "macro_f1": macro_f1,
        },
        "per_field": field_metrics,
        "per_segment": seg_metrics,
        "size_ordinal": {
            "total_mismatches": size_total_mismatches,
            "within_one_band": size_within_one,
            "within_one_band_rate": round(size_within_one / size_total_mismatches, 3) if size_total_mismatches else None,
            "avg_band_distance": avg_band_dist,
        },
        "source_reliability": source_reliability,
        "calibration": calibration,
        "mismatches": mismatches,
    }

    return results


def print_report(results: dict) -> None:
    s = results["summary"]
    pf = results["per_field"]

    print("=" * 60)
    print("Part 4 Eval — Precision / Recall")
    print("=" * 60)
    print(f"Ground truth records:   {s['ground_truth_records']}")
    print(f"Matched in enriched:    {s['enriched_records_matched']}")
    if s["unmatched_handles"]:
        print(f"Unmatched handles ({len(s['unmatched_handles'])}): {s['unmatched_handles']}")
    print()

    print("Per-field metrics:")
    print(f"{'Field':<12} {'Precision':>10} {'Recall':>10} {'F1':>8} {'TP':>5} {'FP':>5} {'FN':>5}")
    print("-" * 60)
    for field in FIELDS:
        m = pf[field]
        p_str = f"{m['precision']:.3f}" if m["precision"] is not None else "   N/A"
        r_str = f"{m['recall']:.3f}" if m["recall"] is not None else "   N/A"
        f_str = f"{m['f1']:.3f}" if m["f1"] is not None else "  N/A"
        print(f"{field:<12} {p_str:>10} {r_str:>10} {f_str:>8} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5}")

    print(f"\n{'MACRO':.<12} "
          f"{str(s['macro_precision']):>10} "
          f"{str(s['macro_recall']):>10} "
          f"{str(s['macro_f1']):>8}")
    print()

    # Size ordinal breakdown
    so = results.get("size_ordinal", {})
    if so.get("total_mismatches"):
        print(f"Size ordinal (exact-match F1 understates accuracy):")
        print(f"  Mismatches within 1 band: {so['within_one_band']}/{so['total_mismatches']} "
              f"({so.get('within_one_band_rate', 0):.0%})")
        print(f"  Avg band distance on mismatches: {so.get('avg_band_distance', 'N/A')}")
        print()

    # Per-segment
    if results["per_segment"]:
        print("Per-segment website precision:")
        for seg, metrics in sorted(results["per_segment"].items()):
            wm = metrics.get("website", {})
            p = wm.get("precision")
            r = wm.get("recall")
            print(f"  {seg:<15} P={p or 'N/A'}  R={r or 'N/A'}")
        print()

    # Source data reliability
    sr = results.get("source_reliability", {})
    if sr:
        all_segs = sorted({seg for field_data in sr.values() for seg in field_data})
        print("Source data reliability (original_correct by field × segment):")
        seg_header = "  ".join(f"{s:<14}" for s in all_segs)
        print(f"  {'Field':<10}  {'Metric':<12}  {seg_header}")
        print("  " + "-" * (10 + 2 + 12 + 2 + 16 * len(all_segs)))
        for field in FIELDS:
            if field not in sr:
                continue
            correct_vals = "  ".join(
                f"{sr[field].get(s, {}).get('correct', '-'):<14}" for s in all_segs
            )
            incorrect_vals = "  ".join(
                f"{sr[field].get(s, {}).get('incorrect', '-'):<14}" for s in all_segs
            )
            rel_vals = "  ".join(
                f"{sr[field].get(s, {}).get('reliability') or 'N/A'!s:<14}" for s in all_segs
            )
            print(f"  {field:<10}  {'correct':<12}  {correct_vals}")
            print(f"  {'':10}  {'incorrect':<12}  {incorrect_vals}")
            print(f"  {'':10}  {'reliability':<12}  {rel_vals}")
        print()

    # Mismatches
    if results["mismatches"]:
        print(f"Mismatches ({len(results['mismatches'])}):")
        for mm in results["mismatches"][:10]:
            print(f"  [{mm['segment']}] {mm['handle']}")
            print(f"    {mm['field']}: expected={mm['gt']!r}  got={mm['pred']!r}")
        if len(results["mismatches"]) > 10:
            print(f"  ... and {len(results['mismatches']) - 10} more")
        print()

    # Confidence calibration
    calib = results.get("calibration", {})
    if calib:
        print(f"Confidence calibration (at >= {CONFIDENCE_CALIBRATION_THRESHOLD:.0%}):")
        print(f"{'Field':<12} {'High-conf preds':>16} {'Correct':>9} {'Calibration':>13}")
        print("-" * 54)
        for field in FIELDS:
            c = calib.get(field, {})
            total = c.get("high_conf_count", 0)
            correct = c.get("high_conf_correct", 0)
            rate = c.get("calibration_rate")
            rate_str = f"{rate:.1%}" if rate is not None else "   N/A"
            print(f"{field:<12} {total:>16} {correct:>9} {rate_str:>13}")
        print()

    # One-paragraph weakness analysis
    weak_fields = [f for f in FIELDS
                   if pf[f]["precision"] is not None and pf[f]["precision"] < 0.70]
    low_recall = [f for f in FIELDS
                  if pf[f]["recall"] is not None and pf[f]["recall"] < 0.60]

    print("Weakness analysis:")
    notes = []
    if weak_fields:
        notes.append(f"Precision is below 70% for: {', '.join(weak_fields)} — the pipeline "
                     f"is over-confidently filling wrong values in these fields.")
    if low_recall:
        notes.append(f"Recall is below 60% for: {', '.join(low_recall)} — the pipeline "
                     f"is leaving too many gaps unfilled.")
    if not weak_fields and not low_recall:
        notes.append("All fields cleared the 70% precision and 60% recall bar on this "
                     "sample. Caveat: the eval set is small; confidence intervals are wide "
                     "and the true error rate on unseen SMB records — which are harder to "
                     "find via search — is likely higher than what this sample shows.")
    print("\n".join(notes) if notes else "No clear weaknesses in this sample.")


if __name__ == "__main__":
    results = run_eval()
    print_report(results)
    # Write results for reference
    out_path = ROOT / "data/enriched/eval_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")
