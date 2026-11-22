"""Turn your own labelled leads (CSV) into an eval dataset.

    python -m evals.import_csv my_labels.csv                  # writes evals/mine.json
    python -m evals.scoring_eval --dataset evals/mine.json    # score it

Required columns: name, label (good/maybe/poor), niche, location, offer
Optional columns: website, address, rating, review_count, email, note
"""
import json
import sys
from pathlib import Path

from evals.dataset import cases_from_csv


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        sys.exit(__doc__)
    source = Path(argv[0])
    data = cases_from_csv(source.read_text(encoding="utf-8-sig"))  # raises with a clear message if a label is wrong
    out = Path(__file__).parent / "mine.json"
    out.write_text(json.dumps(data, indent=2))
    print(f"Wrote {len(data['cases'])} cases in {len(data['campaigns'])} campaign(s) to {out}")


if __name__ == "__main__":
    main()
