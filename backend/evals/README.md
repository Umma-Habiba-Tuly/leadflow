# Evals: is the AI lead score any good?

An eval is a fixed set of leads with human answers. Run it, get numbers, change something
(prompt, model), run again, and see whether the numbers moved.

```bash
cd backend && source .venv/bin/activate
python -m evals.scoring_eval                                   # dev set (30 leads)
python -m evals.scoring_eval --dataset evals/holdout.json      # held-out set (20 leads)
python -m evals.scoring_eval --repeat 2                        # also measures run-to-run stability
python -m evals.scoring_eval --model <other-model> --label "trying another model"
```

Each run is saved in `evals/results/` and compared with the previous run on the same dataset.
Calls the real model, so it needs `GEMINI_API_KEY`. Only synthetic data is sent.

## Labels

- **good**: right niche, right place, a plausible need for the offer, and reachable
- **maybe**: right niche/place but weak or unclear need, thin data, or no email found
- **poor**: wrong niche, wrong place, or no plausible need

Score buckets: 70+ reads as good, 40-69 maybe, below 40 poor.

## What the numbers mean

| Metric | Meaning |
|---|---|
| Pairwise accuracy | Of lead pairs a human ranked, how often the score agrees. 50% is a coin flip. Ranking is what a client uses. |
| By tier | Same, split good>maybe / maybe>poor / good>poor, so one weak tier can't hide in the average |
| Bucket accuracy | Share landing in the human's box. Compare with the "always guess the majority" baseline printed next to it |
| Spearman | Rank correlation, 1.0 is perfect |
| Severe errors | Poor scored good, or good scored poor: the mistakes that cost a client time |
| Stability | With `--repeat`: do the same leads get the same scores each time |

## Read results with care

- **Small sets are noisy.** On 20 leads, one lead is 5 percentage points. Treat changes of a
  few points as noise.
- **`dataset.json` and `holdout.json` are synthetic and labelled by one person.** They catch
  obvious breakage (wrong niche scored high) and regressions. They do not tell you what your
  clients would pick.
- **`holdout.json` stopped being clean** once prompt v2.1 was tuned after seeing its failures.
  Tune on one set, judge on another, and write a fresh held-out set when this one is used up.
- Don't edit labels to make the model look right.

## Use your own leads (this is the eval that matters)

1. Export real leads, add a `label` column filled in by someone who knows the client's taste,
   plus `niche`, `location`, `offer`. Aim for 30+, with a fair number of `maybe`.
2. `python -m evals.import_csv my_labels.csv` then
   `python -m evals.scoring_eval --dataset evals/mine.json`

## History (gemini-3.1-flash-lite)

| Prompt | Dev: pairwise / bucket / Spearman | Holdout: pairwise / bucket / Spearman |
|---|---|---|
| v1 | 94% / 77% / 0.88 | 87% / 65% / 0.77 |
| v2 (rubric) | 94% / 87% / 0.87 | 85% / 60% / 0.72, 1 severe error |
| v2.1 (current) | 94% / 83% / 0.92 | 91% / 65% / 0.85, 1 severe error |

v2 broke things in two ways the holdout exposed: it invented a rating criterion that the offer
didn't state, and it treated a missing Google rating as uncertainty even when the offer didn't
depend on it. v2.1 fixed both. The "maybe" tier is still the weakest.
