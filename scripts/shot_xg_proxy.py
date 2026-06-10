#!/usr/bin/env python3
"""Estimate simple shot-level xG from event-like CSV data.

Input CSV columns:
  team,distance,angle,bodyPart,assistType,underPressure,isBigChance

This is a transparent proxy, not a trained xG model. Use it when shot-level
data exists but a calibrated xG model is not available.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def fnum(row: dict[str, str], key: str, default: float) -> float:
    try:
        value = row.get(key, "")
        if value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def shot_xg(row: dict[str, str]) -> float:
    distance = max(1.0, fnum(row, "distance", 18.0))
    angle = max(0.01, min(1.57, fnum(row, "angle", 0.55)))
    body_part = str(row.get("bodyPart", "foot")).lower()
    assist_type = str(row.get("assistType", "open_play")).lower()

    logit = -1.85
    logit += -0.085 * distance
    logit += 1.25 * angle

    if body_part in {"head", "header"}:
        logit -= 0.35
    elif body_part in {"other"}:
        logit -= 0.55

    if assist_type in {"through_ball", "cutback"}:
        logit += 0.40
    elif assist_type in {"cross", "corner"}:
        logit -= 0.10
    elif assist_type in {"rebound", "fast_break"}:
        logit += 0.25

    if truthy(row.get("underPressure")):
        logit -= 0.25
    if truthy(row.get("isBigChance")):
        logit += 0.85

    return round(max(0.01, min(0.85, sigmoid(logit))), 4)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: shot_xg_proxy.py shots.csv", file=sys.stderr)
        return 2

    totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"shots": 0, "xg": 0.0})
    with Path(sys.argv[1]).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            team = row.get("team") or "unknown"
            value = shot_xg(row)
            totals[team]["shots"] += 1
            totals[team]["xg"] += value

    output = {
        team: {
            "shots": data["shots"],
            "xg": round(data["xg"], 4),
            "xgPerShot": round(data["xg"] / data["shots"], 4) if data["shots"] else 0,
        }
        for team, data in sorted(totals.items())
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
