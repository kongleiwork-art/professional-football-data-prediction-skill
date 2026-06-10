#!/usr/bin/env python3
"""Evaluate and temperature-calibrate 1X2 football probabilities.

Input CSV columns:
  homeWin,draw,awayWin,result

`result` must be one of H/D/A, home/draw/away, or 1/0/2.
The script reports multiclass Brier, log loss, ECE, and the best
temperature from a small grid search.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


LABELS = ("homeWin", "draw", "awayWin")
RESULT_MAP = {
    "H": "homeWin",
    "HOME": "homeWin",
    "1": "homeWin",
    "D": "draw",
    "DRAW": "draw",
    "0": "draw",
    "A": "awayWin",
    "AWAY": "awayWin",
    "2": "awayWin",
}


def normalize(row: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, row[key]) for key in LABELS)
    if total <= 0:
        return {key: 1.0 / 3.0 for key in LABELS}
    return {key: max(0.0, row[key]) / total for key in LABELS}


def temperature_scale(probs: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    logits = {key: math.log(max(probs[key], 1e-12)) / temperature for key in LABELS}
    max_logit = max(logits.values())
    exp_values = {key: math.exp(logits[key] - max_logit) for key in LABELS}
    return normalize(exp_values)


def brier(rows: list[tuple[dict[str, float], str]]) -> float:
    total = 0.0
    for probs, actual in rows:
        total += sum((probs[key] - (1.0 if key == actual else 0.0)) ** 2 for key in LABELS)
    return total / len(rows)


def log_loss(rows: list[tuple[dict[str, float], str]]) -> float:
    return -sum(math.log(max(probs[actual], 1e-12)) for probs, actual in rows) / len(rows)


def ece(rows: list[tuple[dict[str, float], str]], bins: int = 10) -> float:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for probs, actual in rows:
        predicted = max(LABELS, key=lambda key: probs[key])
        confidence = probs[predicted]
        correct = 1 if predicted == actual else 0
        idx = min(bins - 1, int(confidence * bins))
        buckets[idx].append((confidence, correct))

    total = len(rows)
    score = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        avg_confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(item[1] for item in bucket) / len(bucket)
        score += len(bucket) / total * abs(accuracy - avg_confidence)
    return score


def load_rows(path: Path) -> list[tuple[dict[str, float], str]]:
    rows: list[tuple[dict[str, float], str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            actual_raw = str(raw.get("result", "")).strip().upper()
            actual = RESULT_MAP.get(actual_raw)
            if not actual:
                raise ValueError(f"unknown result value: {raw.get('result')!r}")
            probs = normalize({key: float(raw.get(key, 0.0) or 0.0) for key in LABELS})
            rows.append((probs, actual))
    if not rows:
        raise ValueError("no calibration rows found")
    return rows


def metrics(rows: list[tuple[dict[str, float], str]]) -> dict[str, float]:
    return {
        "brier": round(brier(rows), 6),
        "logLoss": round(log_loss(rows), 6),
        "ece": round(ece(rows), 6),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: calibrate_probabilities.py predictions.csv", file=sys.stderr)
        return 2

    rows = load_rows(Path(sys.argv[1]))
    candidates = [round(0.70 + i * 0.02, 2) for i in range(56)]
    scaled_results: list[tuple[float, list[tuple[dict[str, float], str]], dict[str, float]]] = []
    for temperature in candidates:
        scaled = [(temperature_scale(probs, temperature), actual) for probs, actual in rows]
        scaled_results.append((temperature, scaled, metrics(scaled)))

    best = min(scaled_results, key=lambda item: item[2]["logLoss"])
    result: dict[str, Any] = {
        "rows": len(rows),
        "raw": metrics(rows),
        "bestTemperature": best[0],
        "calibrated": best[2],
        "notes": [
            "temperature > 1 softens overconfident probabilities",
            "temperature < 1 sharpens underconfident probabilities",
            "choose calibration only from walk-forward or held-out matches",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
