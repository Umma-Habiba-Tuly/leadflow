"""Pure metric functions for judging lead scores against human labels.

Labels are ordered: poor < maybe < good. Scores are 0-100 integers.
No network, no database: easy to test.
"""
from typing import Dict, List, Optional, Sequence

LABELS = ["poor", "maybe", "good"]
LABEL_RANK = {label: i for i, label in enumerate(LABELS)}
GOOD_AT = 70  # score >= 70 reads as "good"
MAYBE_AT = 40  # 40-69 "maybe", below 40 "poor"


def bucket(score: int) -> str:
    if score >= GOOD_AT:
        return "good"
    if score >= MAYBE_AT:
        return "maybe"
    return "poor"


def bucket_accuracy(labels: Sequence[str], scores: Sequence[int]) -> float:
    """Share of leads whose score lands in the same box as the human label."""
    return sum(bucket(s) == l for l, s in zip(labels, scores)) / len(labels)


def majority_baseline(labels: Sequence[str]) -> float:
    """Accuracy of a model that always answers the most common label. Our score must beat this."""
    return max(labels.count(l) for l in LABELS) / len(labels)


def confusion(labels: Sequence[str], scores: Sequence[int]) -> Dict[str, Dict[str, int]]:
    """confusion[human_label][what_the_score_said] = count"""
    table = {t: {p: 0 for p in LABELS} for t in LABELS}
    for label, score in zip(labels, scores):
        table[label][bucket(score)] += 1
    return table


def pairwise_accuracy(labels: Sequence[str], scores: Sequence[int]) -> Optional[float]:
    """Of all pairs where humans ranked one lead above the other, how often did the score
    agree? 1.0 = perfect ordering, 0.5 = coin flip. Ties count as half. Ranking is what a
    client actually uses, since they work the list from the top."""
    agree, total = 0.0, 0
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            li, lj = LABEL_RANK[labels[i]], LABEL_RANK[labels[j]]
            if li == lj:
                continue
            total += 1
            hi, lo = (i, j) if li > lj else (j, i)
            if scores[hi] > scores[lo]:
                agree += 1
            elif scores[hi] == scores[lo]:
                agree += 0.5
    return agree / total if total else None


def pairwise_by_tier(labels: Sequence[str], scores: Sequence[int]) -> Dict[str, Optional[float]]:
    """Pairwise accuracy split by which two tiers are being compared.

    One blended number can hide a weak spot: a model that separates good from poor perfectly
    but can't tell good from maybe still scores ~90% overall, while a client can't tell
    their best leads from their middling ones."""
    out: Dict[str, Optional[float]] = {}
    for hi, lo in (("good", "maybe"), ("maybe", "poor"), ("good", "poor")):
        picked = [i for i, l in enumerate(labels) if l in (hi, lo)]
        out[f"{hi}>{lo}"] = pairwise_accuracy([labels[i] for i in picked], [scores[i] for i in picked])
    return out


def _average_ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(labels: Sequence[str], scores: Sequence[int]) -> Optional[float]:
    """Rank correlation between human labels and scores (-1..1). None if one side is constant."""
    a = _average_ranks([LABEL_RANK[l] for l in labels])
    b = _average_ranks(list(scores))
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    var_a = sum((x - ma) ** 2 for x in a)
    var_b = sum((y - mb) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return None
    return cov / (var_a * var_b) ** 0.5


def severe_error_indexes(labels: Sequence[str], scores: Sequence[int]) -> List[int]:
    """The mistakes that cost a client real time or money: a poor lead scoring 'good',
    or a good lead scoring 'poor'."""
    return [
        i
        for i, (label, score) in enumerate(zip(labels, scores))
        if (label == "poor" and bucket(score) == "good") or (label == "good" and bucket(score) == "poor")
    ]


def stability(runs: Sequence[Sequence[int]]) -> Optional[Dict[str, float]]:
    """How much do repeated runs on the same leads disagree? `runs` is one score list per run."""
    if len(runs) < 2:
        return None
    diffs, flips, count = 0.0, 0, 0
    for per_lead in zip(*runs):
        spread = max(per_lead) - min(per_lead)
        diffs += spread
        flips += len({bucket(s) for s in per_lead}) > 1
        count += 1
    return {"mean_score_spread": diffs / count, "bucket_flip_rate": flips / count}
