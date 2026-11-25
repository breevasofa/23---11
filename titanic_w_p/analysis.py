"""Reproducible, single-feature analysis of seaborn's Titanic data."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
TARGETS = {
    "Вариант 1": ("survived", "age"),
    "Вариант 2": ("survived", "sex"),
}
# These fields repeat information already present in the retained columns.
DUPLICATES = {
    "alive": "survived",
    "class": "pclass",
    "embark_town": "embarked",
    "who": "sex + age",
    "adult_male": "sex + age",
    "alone": "sibsp + parch",
}
CATEGORICAL = {"pclass", "sex", "sibsp", "parch", "embarked", "deck"}
AGE_EDGES = [0, 5, 12, 18, 30, 45, 60, np.inf]


def load_data() -> tuple[pd.DataFrame, str]:
    """Use seaborn first; retain a local copy for offline Codespaces runs."""
    try:
        import seaborn as sns

        data = sns.load_dataset("titanic")
        source = 'seaborn.load_dataset("titanic")'
    except (ImportError, OSError, ConnectionError):
        data = pd.read_csv(HERE / "titanic.csv")
        source = "titanic.csv (official seaborn-data snapshot)"
    assert data.shape == (891, 15), data.shape
    return data, source


def make_sets(data: pd.DataFrame, targets: tuple[str, str]) -> tuple[list[str], list[str]]:
    w = list(targets)
    p = [column for column in data if column not in w and column not in DUPLICATES]
    assert len(w) == 2 and len(p) == 7 and not (set(w) & set(p))
    assert len(set(p)) == len(p)
    return w, p


def folds(y: np.ndarray, binary: bool, seed: int = 42) -> list[np.ndarray]:
    """Five repeatable folds; binary outcomes are stratified."""
    rng = np.random.default_rng(seed)
    groups = [np.where(y == value)[0] for value in np.unique(y)] if binary else [np.arange(len(y))]
    result = [[] for _ in range(5)]
    for group in groups:
        for i, index in enumerate(rng.permutation(group)):
            result[i % 5].append(int(index))
    return [np.asarray(sorted(part), dtype=int) for part in result]


def buckets(values: pd.Series, feature: str, fare_edges: np.ndarray | None = None) -> pd.Series:
    """Convert one predictor to categories without using the outcome."""
    if feature == "age":
        result = pd.cut(values, AGE_EDGES, include_lowest=True).astype(str)
    elif feature == "fare":
        if fare_edges is None:
            fare_edges = np.unique(np.quantile(values.dropna(), [0.2, 0.4, 0.6, 0.8]))
        result = pd.Series(np.searchsorted(fare_edges, values.to_numpy(dtype=float), side="right"), index=values.index).astype(str)
    elif feature in CATEGORICAL:
        result = values.astype(str)
    else:
        raise ValueError(feature)
    return result.where(values.notna(), "missing")


def predictive_gain(data: pd.DataFrame, target: str, feature: str) -> float:
    """Out-of-fold reduction in squared error over the training-mean baseline.

    For 0/1 outcomes this is the reduction in Brier score. A negative value
    means the single feature predicts worse than the baseline.
    """
    frame = data[[target, feature]].dropna(subset=[target]).reset_index(drop=True)
    y = (frame[target].eq("female").astype(float) if target == "sex"
         else frame[target].astype(float)).to_numpy()
    is_binary = target != "age"
    prediction = np.empty(len(y), dtype=float)
    baseline = np.empty(len(y), dtype=float)
    for test in folds(y, is_binary):
        train = np.setdiff1d(np.arange(len(y)), test)
        mean = float(y[train].mean())
        edges = None
        if feature == "fare":
            edges = np.unique(np.quantile(frame.loc[train, feature].dropna(), [0.2, 0.4, 0.6, 0.8]))
        train_key = buckets(frame.loc[train, feature], feature, edges)
        test_key = buckets(frame.loc[test, feature], feature, edges)
        stats = pd.DataFrame({"key": train_key.to_numpy(), "y": y[train]}).groupby("key").y.agg(["sum", "count"])
        # Five baseline observations prevent tiny groups from dominating.
        lookup = ((stats["sum"] + 5 * mean) / (stats["count"] + 5)).to_dict()
        prediction[test] = test_key.map(lookup).fillna(mean).to_numpy()
        baseline[test] = mean
    return float(1 - np.sum((y - prediction) ** 2) / np.sum((y - baseline) ** 2))


def group_summary(data: pd.DataFrame, target: str, feature: str) -> pd.DataFrame:
    frame = data[[target, feature]].dropna(subset=[target]).copy()
    y = frame[target].eq("female").astype(float) if target == "sex" else frame[target].astype(float)
    keys = buckets(frame[feature], feature)
    result = pd.DataFrame({"group": keys, "y": y}).groupby("group").y.agg(["count", "mean"])
    return result.sort_index()


def run(data: pd.DataFrame) -> dict:
    output = {"n_rows": len(data), "missing": data.isna().sum().to_dict(), "variants": {}}
    for name, targets in TARGETS.items():
        w, p = make_sets(data, targets)
        rows = []
        for target in w:
            for feature in p:
                rows.append({"target": target, "feature": feature,
                             "gain": predictive_gain(data, target, feature),
                             "observed_n": int(data[[target, feature]].dropna().shape[0])})
        output["variants"][name] = {"W": w, "P": p, "ranking": rows}
    return output


if __name__ == "__main__":
    data, source = load_data()
    results = run(data)
    results["source_used"] = source
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, variant in results["variants"].items():
        print(f"\n{name}: W={variant['W']}; P={variant['P']}")
        table = pd.DataFrame(variant["ranking"])
        for target in variant["W"]:
            print(f"\n{target} (n={data[target].notna().sum()}):")
            print(table[table.target == target].sort_values("gain", ascending=False).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
