#!/usr/bin/env python3
"""Backtest stored football predictions against final scores.

Input CSV columns:
  matchDate,homeTeam,awayTeam,predictedHomeGoals,predictedAwayGoals,
  homeWin,draw,awayWin,actualHomeGoals,actualAwayGoals,result

`result` may be omitted when actual scores exist. Probabilities can be
0-1 or 0-100; the script normalizes them.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


LABELS = ("homeWin", "draw", "awayWin")


def fnum(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, "")
        if value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize(probs: dict[str, float]) -> dict[str, float]:
    if max(probs.values() or [0.0]) > 1.0:
        probs = {key: value / 100.0 for key, value in probs.items()}
    total = sum(max(0.0, probs[key]) for key in LABELS)
    if total <= 0:
        return {key: 1.0 / 3.0 for key in LABELS}
    return {key: max(0.0, probs[key]) / total for key in LABELS}


def result_from_row(row: dict[str, str]) -> str | None:
    result = (row.get("result") or "").strip().upper()
    mapping = {"H": "homeWin", "HOME": "homeWin", "1": "homeWin", "D": "draw", "DRAW": "draw", "0": "draw", "A": "awayWin", "AWAY": "awayWin", "2": "awayWin"}
    if result in mapping:
        return mapping[result]

    if row.get("actualHomeGoals", "") == "" or row.get("actualAwayGoals", "") == "":
        return None
    home_goals = fnum(row, "actualHomeGoals")
    away_goals = fnum(row, "actualAwayGoals")
    if home_goals > away_goals:
        return "homeWin"
    if home_goals < away_goals:
        return "awayWin"
    return "draw"


def predicted_result(probs: dict[str, float]) -> str:
    return max(LABELS, key=lambda key: probs[key])


def predicted_score(row: dict[str, str]) -> tuple[int, int] | None:
    if row.get("predictedHomeGoals", "") == "" or row.get("predictedAwayGoals", "") == "":
        return None
    return (round(fnum(row, "predictedHomeGoals")), round(fnum(row, "predictedAwayGoals")))


def actual_score(row: dict[str, str]) -> tuple[int, int] | None:
    if row.get("actualHomeGoals", "") == "" or row.get("actualAwayGoals", "") == "":
        return None
    return (int(fnum(row, "actualHomeGoals")), int(fnum(row, "actualAwayGoals")))


def brier(probs: dict[str, float], actual: str) -> float:
    return sum((probs[key] - (1.0 if key == actual else 0.0)) ** 2 for key in LABELS)


def log_loss(probs: dict[str, float], actual: str) -> float:
    return -math.log(max(probs[actual], 1e-12))


def bucket_key(row: dict[str, str]) -> str:
    return (row.get("competition") or "all").strip() or "all"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"matches": 0}
    n = len(rows)
    exact_scores = sum(1 for row in rows if row["exactScoreHit"])
    result_hits = sum(1 for row in rows if row["resultHit"])
    total_goals_mae = sum(row["totalGoalsAbsError"] for row in rows if row["totalGoalsAbsError"] is not None)
    total_goal_rows = sum(1 for row in rows if row["totalGoalsAbsError"] is not None)
    return {
        "matches": n,
        "resultAccuracy": round(result_hits / n, 4),
        "exactScoreAccuracy": round(exact_scores / n, 4),
        "avgBrier": round(sum(row["brier"] for row in rows) / n, 6),
        "avgLogLoss": round(sum(row["logLoss"] for row in rows) / n, 6),
        "totalGoalsMAE": round(total_goals_mae / total_goal_rows, 4) if total_goal_rows else None,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: backtest_predictions.py historical_predictions.csv", file=sys.stderr)
        return 2

    scored: list[dict[str, Any]] = []
    with Path(sys.argv[1]).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            actual = result_from_row(raw)
            if actual is None:
                continue
            probs = normalize({key: fnum(raw, key) for key in LABELS})
            pred = predicted_result(probs)
            pred_score = predicted_score(raw)
            act_score = actual_score(raw)
            total_goals_abs_error = None
            exact_score_hit = False
            if pred_score and act_score:
                total_goals_abs_error = abs(sum(pred_score) - sum(act_score))
                exact_score_hit = pred_score == act_score
            scored.append(
                {
                    "competition": bucket_key(raw),
                    "resultHit": pred == actual,
                    "exactScoreHit": exact_score_hit,
                    "brier": brier(probs, actual),
                    "logLoss": log_loss(probs, actual),
                    "totalGoalsAbsError": total_goals_abs_error,
                }
            )

    by_competition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        by_competition[row["competition"]].append(row)

    output = {
        "overall": summarize(scored),
        "byCompetition": {competition: summarize(items) for competition, items in sorted(by_competition.items())},
        "notes": [
            "Rows without final result are ignored.",
            "Use this after matches finish, then feed the same CSV to calibrate_probabilities.py for temperature calibration.",
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
