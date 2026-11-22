import json

import pytest

from app.services.llm import LLMError, LLMRateLimited
from evals import metrics
from evals.dataset import DEFAULT_PATH, cases_from_csv, load_dataset, parse_dataset
from evals.scoring_eval import evaluate, format_report, latest_previous

# ---------- metrics: prove the ruler is straight before measuring anything with it ----------


@pytest.mark.parametrize("score,expected", [(0, "poor"), (39, "poor"), (40, "maybe"), (69, "maybe"), (70, "good"), (100, "good")])
def test_bucket_boundaries(score, expected):
    assert metrics.bucket(score) == expected


LABELS = ["good", "good", "maybe", "maybe", "poor", "poor"]


def test_pairwise_accuracy_perfect_reversed_and_constant():
    assert metrics.pairwise_accuracy(LABELS, [90, 80, 60, 50, 20, 10]) == 1.0
    assert metrics.pairwise_accuracy(LABELS, [10, 20, 50, 60, 80, 90]) == 0.0
    assert metrics.pairwise_accuracy(LABELS, [50] * 6) == 0.5  # ties = coin flip
    assert metrics.pairwise_accuracy(["good", "good"], [90, 10]) is None  # no ordered pairs to judge


def test_pairwise_ignores_order_within_the_same_label():
    # Two "good" leads in either order is not an error.
    assert metrics.pairwise_accuracy(["good", "good", "poor"], [60, 90, 10]) == 1.0


def test_bucket_accuracy_baseline_and_confusion():
    # good->good ok, good->poor (miss!), maybe ok, maybe ok, poor->poor ok, poor->good (miss!)
    scores = [90, 20, 60, 60, 20, 90]
    assert metrics.bucket_accuracy(LABELS, scores) == pytest.approx(4 / 6)
    assert metrics.majority_baseline(LABELS) == pytest.approx(2 / 6)
    table = metrics.confusion(LABELS, scores)
    assert table["good"] == {"poor": 1, "maybe": 0, "good": 1}
    assert table["poor"] == {"poor": 1, "maybe": 0, "good": 1}
    assert table["maybe"]["maybe"] == 2


def test_severe_errors_are_only_the_costly_ones():
    scores = [90, 20, 60, 60, 20, 90]
    assert metrics.severe_error_indexes(LABELS, scores) == [1, 5]
    # A good lead scored "maybe" is a miss, but not a severe one.
    assert metrics.severe_error_indexes(["good"], [55]) == []


def test_spearman():
    assert metrics.spearman(LABELS, [90, 80, 60, 50, 20, 10]) > 0.95
    assert metrics.spearman(LABELS, [10, 20, 50, 60, 80, 90]) < -0.95
    assert metrics.spearman(LABELS, [50] * 6) is None


def test_average_ranks_handle_ties():
    assert metrics._average_ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_stability():
    assert metrics.stability([[80, 20]]) is None
    same = metrics.stability([[80, 20], [80, 20]])
    assert same == {"mean_score_spread": 0.0, "bucket_flip_rate": 0.0}
    jumpy = metrics.stability([[80, 20], [60, 20]])  # first lead moves 20 pts and flips good->maybe
    assert jumpy["mean_score_spread"] == 10.0 and jumpy["bucket_flip_rate"] == 0.5


# ---------- dataset ----------


def test_shipped_dataset_is_sound():
    cases = load_dataset(DEFAULT_PATH)
    assert len(cases) >= 25
    assert len({c.id for c in cases}) == len(cases)
    for label in metrics.LABELS:
        assert sum(c.label == label for c in cases) >= 5, f"too few '{label}' cases to measure anything"
    assert len({c.campaign for c in cases}) >= 3  # not just one offer
    assert all(c.offer and c.niche and c.location for c in cases)
    # Prompt-injection traps must be present, and must be labelled poor.
    traps = [c for c in cases if "ignore all" in c.name.lower() or "system note" in c.name.lower()]
    assert len(traps) >= 2 and all(c.label == "poor" for c in traps)


def _base():
    return {
        "campaigns": {"a": {"niche": "n", "location": "l", "offer": "o"}},
        "cases": [{"id": "1", "campaign": "a", "name": "X", "label": "good"}],
    }


def test_parse_dataset_rejects_mistakes_loudly():
    assert len(parse_dataset(_base())) == 1
    for mutate in (
        lambda d: d["cases"][0].update(label="great"),  # typo in label would silently skew metrics
        lambda d: d["cases"][0].update(campaign="zzz"),
        lambda d: d["cases"][0].update(name="  "),
        lambda d: d["cases"].append(dict(d["cases"][0])),  # duplicate id
        lambda d: d["campaigns"]["a"].pop("offer"),
        lambda d: d.update(cases=[]),
    ):
        d = _base()
        mutate(d)
        with pytest.raises(ValueError):
            parse_dataset(d)


def test_csv_import_groups_campaigns_and_validates():
    csv_text = (
        "name,label,niche,location,offer,website,rating,review_count,email,note\n"
        "A Dental,good,dentist,Austin,SEO,https://a.example,4.1,50,a@a.example,great fit\n"
        "B Dental,poor,dentist,Austin,SEO,,,,,\n"
        "C Cafe,maybe,cafe,Dallas,Reviews,,3.5,10,,\n"
    )
    data = cases_from_csv(csv_text)
    assert len(data["campaigns"]) == 2  # same niche+location+offer share one campaign
    cases = parse_dataset(data)
    assert [c.has_email for c in cases] == [True, False, False]
    assert cases[0].rating == 4.1 and cases[1].rating is None and cases[2].review_count == 10
    with pytest.raises(ValueError):
        cases_from_csv(csv_text.replace(",good,", ",awesome,"))


# ---------- the runner, with stand-in "models" of known quality ----------


class Stub:
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def generate_json(self, system, prompt, schema):
        self.calls += 1
        return self.fn(prompt, self.calls)


CASES = load_dataset(DEFAULT_PATH)
LABEL_OF = {c.name: c.label for c in CASES}


def _label_in(prompt):
    return next(label for name, label in LABEL_OF.items() if f"name: {name}\n" in prompt)


def _answer(score):
    return {"score": score, "reason": "stub"}


def no_sleep(_):
    pass


def test_a_perfect_scorer_gets_perfect_marks():
    stub = Stub(lambda p, n: _answer({"good": 85, "maybe": 55, "poor": 10}[_label_in(p)]))
    r = evaluate(CASES, stub, sleep=no_sleep)
    assert r["pairwise_accuracy"] == 1.0 and r["bucket_accuracy"] == 1.0
    assert r["spearman"] > 0.95 and r["severe_errors"] == []


def test_a_coin_flip_scorer_is_exposed():
    r = evaluate(CASES, Stub(lambda p, n: _answer(50)), sleep=no_sleep)
    assert r["pairwise_accuracy"] == 0.5
    assert r["bucket_accuracy"] == pytest.approx(r["confusion"]["maybe"]["maybe"] / len(CASES))
    assert r["spearman"] is None


def test_a_backwards_scorer_scores_zero_and_every_big_miss_is_reported():
    stub = Stub(lambda p, n: _answer({"good": 5, "maybe": 55, "poor": 95}[_label_in(p)]))
    r = evaluate(CASES, stub, sleep=no_sleep)
    assert r["pairwise_accuracy"] == 0.0
    expected = sum(c.label in ("good", "poor") for c in CASES)
    assert len(r["severe_errors"]) == expected


def test_one_failing_lead_does_not_sink_the_run():
    def fn(prompt, n):
        if "name: Bright Smile Dental\n" in prompt:
            raise LLMError("boom")
        return _answer({"good": 85, "maybe": 55, "poor": 10}[_label_in(prompt)])

    r = evaluate(CASES, Stub(fn), sleep=no_sleep)
    assert r["n_scored"] == len(CASES) - 1
    assert [e["id"] for e in r["errors"]] == ["dent-01"]
    assert r["pairwise_accuracy"] == 1.0


def test_rate_limit_backs_off_then_recovers():
    sleeps = []

    def fn(prompt, n):
        if n <= 2:
            raise LLMRateLimited("slow")
        return _answer(60)

    r = evaluate(CASES[:1], Stub(fn), sleep=sleeps.append)
    assert r["n_scored"] == 1 and r["errors"] == []
    assert sleeps == [15, 30]  # waits longer each time


def test_everything_failing_raises_instead_of_reporting_fake_metrics():
    def fn(prompt, n):
        raise LLMError("down")

    with pytest.raises(RuntimeError, match="down"):
        evaluate(CASES[:3], Stub(fn), sleep=no_sleep)


def test_repeat_measures_stability_and_metrics_use_the_first_run():
    def fn(prompt, n):
        base = {"good": 85, "maybe": 55, "poor": 10}[_label_in(prompt)]
        return _answer(base if n <= len(CASES) else base - 10)  # second pass is 10 lower

    r = evaluate(CASES, Stub(fn), repeat=2, sleep=no_sleep)
    assert r["stability"]["mean_score_spread"] == 10.0
    assert r["pairwise_accuracy"] == 1.0  # first run only
    assert r["per_case"][0]["scores"] == [85, 75]


# ---------- report and history ----------


def test_report_shows_key_numbers_baseline_and_change_vs_previous():
    stub = Stub(lambda p, n: _answer({"good": 85, "maybe": 55, "poor": 10}[_label_in(p)]))
    r = evaluate(CASES, stub, sleep=no_sleep)
    text = format_report(r, {"metrics": {"pairwise_accuracy": 0.80, "bucket_accuracy": 1.0}})
    assert "Pairwise ranking accuracy : 100%" in text and "+20 pts" in text
    assert "baseline" in text and "No severe errors." in text and "Confusion" in text


def test_latest_previous_matches_by_dataset(tmp_path):
    (tmp_path / "20240101-000000_m.json").write_text(json.dumps({"meta": {"dataset_hash": "AAA"}, "metrics": {"x": 1}}))
    (tmp_path / "20240102-000000_m.json").write_text(json.dumps({"meta": {"dataset_hash": "BBB"}, "metrics": {"x": 2}}))
    (tmp_path / "20240103-000000_m.json").write_text("not json")
    assert latest_previous(tmp_path, "AAA")["metrics"]["x"] == 1
    assert latest_previous(tmp_path, "BBB")["metrics"]["x"] == 2
    assert latest_previous(tmp_path, "ZZZ") is None


def test_pairwise_by_tier_exposes_a_weak_spot_the_blended_number_hides():
    labels = ["good", "good", "maybe", "maybe", "poor", "poor"]
    scores = [95, 95, 95, 95, 5, 5]  # splits good/poor perfectly, can't tell good from maybe
    tiers = metrics.pairwise_by_tier(labels, scores)
    assert tiers == {"good>maybe": 0.5, "maybe>poor": 1.0, "good>poor": 1.0}
    # 10 of 12 ordered pairs are fine (the 4 good-vs-maybe pairs tie), so the blended number
    # still looks healthy at 83% while one tier is a coin flip.
    assert metrics.pairwise_accuracy(labels, scores) == pytest.approx(10 / 12)


def test_holdout_is_valid_and_does_not_leak_into_the_dev_set():
    from evals.dataset import DEFAULT_PATH as DEV

    holdout = load_dataset(DEV.parent / "holdout.json")
    dev = load_dataset(DEV)
    assert len(holdout) >= 15
    for label in metrics.LABELS:
        assert sum(c.label == label for c in holdout) >= 4
    # If a business appears in both sets, the "unseen" test is not unseen.
    assert not ({c.name for c in holdout} & {c.name for c in dev})
    assert not ({c.id for c in holdout} & {c.id for c in dev})
    assert "law" in {c.campaign for c in holdout}  # a niche the dev set never saw
