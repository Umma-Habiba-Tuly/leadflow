"""Measure how well AI lead scoring agrees with human labels.

    python -m evals.scoring_eval                 # one pass over the dataset
    python -m evals.scoring_eval --repeat 2      # also measures run-to-run stability
    python -m evals.scoring_eval --model gemini-3.5-flash-lite

Every run is saved under evals/results/ and compared with the previous run on the same
dataset, so you can see whether a prompt or model change helped or hurt.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.db.models import Campaign, Lead
from app.services import scoring
from app.services.llm import GeminiClient, LLMClient, LLMError, LLMRateLimited
from evals import metrics
from evals.dataset import DEFAULT_PATH, Case, load_dataset

RESULTS_DIR = Path(__file__).parent / "results"


def to_orm(case: Case) -> Tuple[Campaign, Lead]:
    """Build the same objects production scores, without touching a database."""
    campaign = Campaign(id=0, workspace_id=0, name="eval", niche=case.niche, location=case.location, offer=case.offer)
    lead = Lead(
        id=0, workspace_id=0, campaign_id=0, name=case.name, website=case.website, address=case.address,
        rating=case.rating, review_count=case.review_count, email="x@example.com" if case.has_email else None,
    )
    return campaign, lead


def score_case(llm: LLMClient, case: Case, retries: int = 3, pause: float = 15, sleep: Callable = time.sleep):
    """Returns (ScoreResult or None, error message or None). Backs off when rate limited."""
    campaign, lead = to_orm(case)
    for attempt in range(retries + 1):
        try:
            return scoring.score_lead(llm, campaign, lead), None
        except LLMRateLimited:
            if attempt == retries:
                return None, "rate limited"
            sleep(pause * (attempt + 1))
        except LLMError as exc:
            return None, str(exc)
    return None, "unknown"


def evaluate(cases: List[Case], llm: LLMClient, repeat: int = 1, delay: float = 0.0, sleep: Callable = time.sleep) -> dict:
    """Score every case `repeat` times and compute metrics from the FIRST run (what production
    would have seen). Extra runs only feed the stability number."""
    runs: List[Dict[str, Optional[int]]] = []
    reasons: Dict[str, str] = {}
    errors: List[dict] = []
    for run_index in range(repeat):
        scores: Dict[str, Optional[int]] = {}
        for case in cases:
            result, error = score_case(llm, case, sleep=sleep)
            scores[case.id] = result.score if result else None
            if result and run_index == 0:
                reasons[case.id] = result.reason
            if error:
                errors.append({"id": case.id, "run": run_index + 1, "error": error})
            if delay:
                sleep(delay)
        runs.append(scores)

    first = runs[0]
    scored = [c for c in cases if first[c.id] is not None]
    if not scored:
        raise RuntimeError(f"No case could be scored. First error: {errors[0]['error'] if errors else 'unknown'}")
    labels = [c.label for c in scored]
    values = [first[c.id] for c in scored]

    complete = [c for c in cases if all(r[c.id] is not None for r in runs)]
    stab = metrics.stability([[r[c.id] for c in complete] for r in runs]) if repeat > 1 and complete else None

    return {
        "n_cases": len(cases),
        "n_scored": len(scored),
        "errors": errors,
        "bucket_accuracy": metrics.bucket_accuracy(labels, values),
        "majority_baseline": metrics.majority_baseline(labels),
        "pairwise_accuracy": metrics.pairwise_accuracy(labels, values),
        "pairwise_by_tier": metrics.pairwise_by_tier(labels, values),
        "spearman": metrics.spearman(labels, values),
        "confusion": metrics.confusion(labels, values),
        "severe_errors": [
            {"id": scored[i].id, "name": scored[i].name, "label": labels[i], "score": values[i], "reason": reasons.get(scored[i].id, "")}
            for i in metrics.severe_error_indexes(labels, values)
        ],
        "stability": stab,
        "per_case": [
            {"id": c.id, "label": c.label, "scores": [r[c.id] for r in runs], "reason": reasons.get(c.id, "")} for c in cases
        ],
    }


# ---------- reporting ----------


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def format_report(result: dict, previous: Optional[dict] = None) -> str:
    def delta(key: str) -> str:
        if not previous or previous["metrics"].get(key) is None or result.get(key) is None:
            return ""
        d = (result[key] - previous["metrics"][key]) * 100
        return f"   ({d:+.0f} pts vs previous run)" if abs(d) >= 0.5 else "   (same as previous run)"

    lines = [
        f"Scored {result['n_scored']}/{result['n_cases']} leads" + (f", {len(result['errors'])} errors" if result["errors"] else ""),
        "",
        f"Pairwise ranking accuracy : {_pct(result['pairwise_accuracy'])}{delta('pairwise_accuracy')}   (50% = coin flip)",
        f"Bucket accuracy           : {_pct(result['bucket_accuracy'])}{delta('bucket_accuracy')}   (always-guess-majority baseline: {_pct(result['majority_baseline'])})",
        "  by tier                 : " + "   ".join(f"{k} {_pct(v)}" for k, v in result["pairwise_by_tier"].items()),
        f"Spearman rank correlation : {'n/a' if result['spearman'] is None else format(result['spearman'], '.2f')}   (1.0 = perfect)",
    ]
    if result["stability"]:
        s = result["stability"]
        lines.append(f"Stability across runs     : avg score spread {s['mean_score_spread']:.1f} pts, bucket flips on {_pct(s['bucket_flip_rate'])} of leads")
    lines += ["", "Confusion (rows = human label, columns = what the score said):", f"{'':8}{'poor':>7}{'maybe':>7}{'good':>7}"]
    for true in metrics.LABELS:
        row = result["confusion"][true]
        lines.append(f"{true:8}" + "".join(f"{row[p]:>7}" for p in metrics.LABELS))
    if result["severe_errors"]:
        lines += ["", f"SEVERE errors ({len(result['severe_errors'])}): poor scored as good, or good scored as poor"]
        for e in result["severe_errors"]:
            lines.append(f"  [{e['score']:>3}] human={e['label']:5} {e['name'][:48]}\n        {e['reason'][:150]}")
    else:
        lines += ["", "No severe errors."]
    for e in result["errors"][:5]:
        lines.append(f"  error: {e['id']} (run {e['run']}): {e['error']}")
    return "\n".join(lines)


def _fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def latest_previous(out_dir: Path, dataset_hash: str) -> Optional[dict]:
    for path in sorted(out_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        if data.get("meta", {}).get("dataset_hash") == dataset_hash:
            return data
    return None


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--repeat", type=int, default=1, help="score every lead this many times (>=2 measures stability)")
    parser.add_argument("--model", default=None, help="override LLM_MODEL for this run")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds to wait between calls (free-tier friendliness)")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--label", default="", help="short note saved with this run, e.g. 'tightened prompt'")
    args = parser.parse_args(argv)

    cases = load_dataset(args.dataset)
    model = args.model or settings.llm_model
    llm = GeminiClient(settings.gemini_api_key, model)
    print(f"Evaluating {len(cases)} leads with {model} (repeat={args.repeat}) ...\n")

    result = evaluate(cases, llm, repeat=args.repeat, delay=args.delay)

    dataset_hash = _fingerprint(args.dataset.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    previous = latest_previous(args.out_dir, dataset_hash)
    print(format_report(result, {"metrics": previous["metrics"]} if previous else None))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    record = {
        "meta": {
            "timestamp": stamp, "model": model, "repeat": args.repeat, "label": args.label,
            "dataset_hash": dataset_hash, "prompt_hash": _fingerprint(scoring.SYSTEM_PROMPT),
        },
        "metrics": {k: result[k] for k in ("n_cases", "n_scored", "bucket_accuracy", "majority_baseline", "pairwise_accuracy", "pairwise_by_tier", "spearman", "confusion", "stability")},
        "severe_errors": result["severe_errors"],
        "per_case": result["per_case"],
        "errors": result["errors"],
    }
    path = args.out_dir / f"{stamp}_{model}.json"
    path.write_text(json.dumps(record, indent=2))
    print(f"\nSaved: {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    main()
