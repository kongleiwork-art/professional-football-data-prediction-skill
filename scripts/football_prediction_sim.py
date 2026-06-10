#!/usr/bin/env python3
"""Deterministic football score-probability helper.

Input: JSON with home/away xG or proxy inputs, Elo, venue, optional market probabilities.
Output: expected goals, 1X2 probabilities, and most likely scores.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any


LABELS_1X2 = ("homeWin", "draw", "awayWin")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fnum(data: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def has_number(data: dict[str, Any], key: str) -> bool:
    try:
        value = data.get(key)
        if value is None or value == "":
            return False
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def data_quality(team: dict[str, Any], side: str) -> dict[str, Any]:
    provenance = team.get("dataProvenance", {})
    if not isinstance(provenance, dict):
        provenance = {}

    tracked = [
        "availability",
        "lineup",
        "injuries",
        "clubMinutes",
        "clubPerformance",
        "keyPlayerImpact",
        "goalkeeper",
        "tactical",
        "setPieces",
        "penalties",
    ]
    counts = {"api": 0, "manual": 0, "estimated": 0, "missing": 0, "unknown": 0}
    notes: list[str] = []
    for field in tracked:
        meta = provenance.get(field, {})
        if isinstance(meta, str):
            source_type = meta
            confidence = "unknown"
        elif isinstance(meta, dict):
            source_type = str(meta.get("sourceType", "unknown"))
            confidence = str(meta.get("confidence", "unknown"))
        else:
            source_type = "unknown"
            confidence = "unknown"
        source_type = source_type if source_type in counts else "unknown"
        counts[source_type] += 1
        if source_type in {"estimated", "missing", "unknown"}:
            notes.append(f"{side}.{field}: {source_type}/{confidence}")

    usable = counts["api"] + counts["manual"]
    weak = counts["estimated"] + counts["missing"] + counts["unknown"]
    if weak >= 6:
        confidence = "low"
    elif weak >= 3:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "confidence": confidence,
        "sourceTypeCounts": counts,
        "notes": notes,
    }


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in probs.values())
    if total <= 0:
        return probs
    return {k: max(0.0, v) / total for k, v in probs.items()}


def temperature_scale(probs: dict[str, float], temperature: float) -> dict[str, float]:
    if abs(temperature - 1.0) < 1e-9:
        return probs
    logits = {key: math.log(max(value, 1e-12)) / temperature for key, value in probs.items()}
    max_logit = max(logits.values())
    exp_values = {key: math.exp(value - max_logit) for key, value in logits.items()}
    return normalize_probs(exp_values)


def public_consensus_adjustment(probs: dict[str, float], context: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    calibration = context.get("publicConsensusCalibration", {})
    if not isinstance(calibration, dict) or not calibration.get("enabled", False):
        return probs, {
            "enabled": False,
            "notes": ["public consensus calibration disabled or missing"],
        }

    stage = str(calibration.get("stage", "group")).lower()
    adjusted = dict(probs)
    notes: list[str] = []
    favorite = max(LABELS_1X2, key=lambda key: adjusted[key])
    favorite_prob = adjusted[favorite]

    favorite_shrink = fnum(calibration, "favoriteShrink", 0.0)
    draw_boost = fnum(calibration, "drawBoost", 0.0)
    underdog_boost = fnum(calibration, "underdogBoost", 0.0)

    if favorite_shrink <= 0 and draw_boost <= 0 and underdog_boost <= 0:
        if stage in {"group", "group_stage"}:
            if favorite_prob >= 0.72:
                favorite_shrink = 0.035
                draw_boost = 0.018
                underdog_boost = 0.017
                notes.append("group-stage heavy favorite conservative shrink from World Cup public/market upset prior")
            elif favorite_prob >= 0.60:
                favorite_shrink = 0.020
                draw_boost = 0.012
                underdog_boost = 0.008
                notes.append("group-stage favorite mild shrink")
        elif stage in {"knockout", "elimination"}:
            if favorite_prob >= 0.65:
                favorite_shrink = 0.025
                draw_boost = 0.020
                underdog_boost = 0.005
                notes.append("knockout favorite shrink: lower tempo and extra-time/penalty tail risk")
        elif stage in {"friendly", "warmup", "warm-up"}:
            if favorite_prob >= 0.68:
                favorite_shrink = 0.030
                draw_boost = 0.018
                underdog_boost = 0.012
                notes.append("friendly favorite shrink: rotation and motivation uncertainty")

    if favorite_shrink or draw_boost or underdog_boost:
        adjusted[favorite] = max(0.01, adjusted[favorite] - favorite_shrink)
        non_favorites = [key for key in LABELS_1X2 if key != favorite]
        if "draw" in non_favorites:
            adjusted["draw"] += draw_boost
            other = [key for key in non_favorites if key != "draw"]
            for key in other:
                adjusted[key] += underdog_boost
        else:
            for key in non_favorites:
                adjusted[key] += (draw_boost + underdog_boost) / len(non_favorites)

    max_favorite = fnum(calibration, "maxFavoriteProbability", 0.0)
    if max_favorite and adjusted[favorite] > max_favorite:
        overflow = adjusted[favorite] - max_favorite
        adjusted[favorite] = max_favorite
        non_favorites = [key for key in LABELS_1X2 if key != favorite]
        for key in non_favorites:
            adjusted[key] += overflow / len(non_favorites)
        notes.append(f"favorite capped at {round(max_favorite, 3)}")

    adjusted = normalize_probs(adjusted)
    return adjusted, {
        "enabled": True,
        "stage": stage,
        "favorite": favorite,
        "favoriteShrink": round(favorite_shrink, 4),
        "drawBoost": round(draw_boost, 4),
        "underdogBoost": round(underdog_boost, 4),
        "notes": notes or ["public consensus calibration enabled; no adjustment triggered"],
    }


def proxy_xg_from_shots(team: dict[str, Any], prefix: str) -> float | None:
    if prefix == "recent":
        shots_key = "recentShotsFor"
        shots_on_target_key = "recentShotsOnTargetFor"
        big_chances_key = "recentBigChancesFor"
        box_shots_key = "recentBoxShotsFor"
    elif prefix == "recentAgainst":
        shots_key = "recentShotsAgainst"
        shots_on_target_key = "recentShotsOnTargetAgainst"
        big_chances_key = "recentBigChancesAgainst"
        box_shots_key = "recentBoxShotsAgainst"
    else:
        shots_key = f"{prefix}Shots"
        shots_on_target_key = f"{prefix}ShotsOnTarget"
        big_chances_key = f"{prefix}BigChances"
        box_shots_key = f"{prefix}BoxShots"
    if not any(has_number(team, key) for key in [shots_key, shots_on_target_key, big_chances_key, box_shots_key]):
        return None

    shots = fnum(team, shots_key, 0.0)
    shots_on_target = fnum(team, shots_on_target_key, 0.0)
    big_chances = fnum(team, big_chances_key, 0.0)
    box_shots = fnum(team, box_shots_key, 0.0)
    proxy = 0.06 * shots + 0.05 * shots_on_target + 0.18 * big_chances + 0.03 * box_shots
    return clamp(proxy, 0.30, 3.20)


def regressed_goals(team: dict[str, Any], key: str, league_avg: float) -> float | None:
    if not has_number(team, key):
        return None
    goals = fnum(team, key, league_avg)
    return clamp(0.62 * goals + 0.38 * league_avg, 0.30, 3.20)


def availability_adjustment(team: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Estimate squad availability goal impact from available players and starters.

    Negative attack/defense values lower this team's own lambda or weaken its defense.
    """

    if has_number(team, "availabilityGoalAdjustment"):
        explicit = clamp(fnum(team, "availabilityGoalAdjustment", 0.0), -0.45, 0.25)
        return {
            "attack": explicit,
            "defense": explicit * 0.65,
            "notes": [f"used explicit availabilityGoalAdjustment={round(explicit, 3)}"],
        }

    notes: list[str] = []
    baseline_players = fnum(context, "baselineAvailablePlayers", 23.0)
    attack_delta = 0.0
    defense_delta = 0.0

    if has_number(team, "availablePlayers"):
        available = fnum(team, "availablePlayers", baseline_players)
        shortage = max(0.0, baseline_players - available)
        depth_penalty = clamp(shortage * 0.012, 0.0, 0.20)
        attack_delta -= depth_penalty
        defense_delta -= depth_penalty * 0.8
        notes.append(f"availablePlayers={available:g} vs baseline={baseline_players:g}")

    unavailable_starters = fnum(team, "unavailableStarters", 0.0)
    doubtful_starters = fnum(team, "doubtfulStarters", 0.0)
    if unavailable_starters or doubtful_starters:
        starter_penalty = unavailable_starters * 0.055 + doubtful_starters * 0.028
        attack_delta -= starter_penalty
        defense_delta -= starter_penalty * 0.85
        notes.append(f"starter availability penalty from out={unavailable_starters:g}, doubtful={doubtful_starters:g}")

    unavailable_attackers = fnum(team, "unavailableAttackers", 0.0)
    unavailable_defenders = fnum(team, "unavailableDefenders", 0.0)
    unavailable_midfielders = fnum(team, "unavailableMidfielders", 0.0)
    if unavailable_attackers:
        attack_delta -= unavailable_attackers * 0.045
        notes.append(f"attack availability penalty from unavailableAttackers={unavailable_attackers:g}")
    if unavailable_midfielders:
        attack_delta -= unavailable_midfielders * 0.025
        defense_delta -= unavailable_midfielders * 0.025
        notes.append(f"midfield availability penalty from unavailableMidfielders={unavailable_midfielders:g}")
    if unavailable_defenders:
        defense_delta -= unavailable_defenders * 0.045
        notes.append(f"defensive availability penalty from unavailableDefenders={unavailable_defenders:g}")

    if has_number(team, "unavailableKeyPlayerGoalImpact"):
        key_impact = clamp(fnum(team, "unavailableKeyPlayerGoalImpact", 0.0), 0.0, 0.30)
        attack_delta -= key_impact
        defense_delta -= key_impact * 0.4
        notes.append(f"key-player availability impact={round(key_impact, 3)}")

    key_attack_impact = fnum(team, "keyPlayerAttackImpact", 0.0)
    key_defense_impact = fnum(team, "keyPlayerDefenseImpact", 0.0)
    goalkeeper_impact = fnum(team, "goalkeeperImpactAdjustment", 0.0)
    if key_attack_impact:
        attack_delta += clamp(key_attack_impact, -0.35, 0.25)
        notes.append(f"keyPlayerAttackImpact={round(key_attack_impact, 3)}")
    if key_defense_impact:
        defense_delta += clamp(key_defense_impact, -0.35, 0.25)
        notes.append(f"keyPlayerDefenseImpact={round(key_defense_impact, 3)}")
    if goalkeeper_impact:
        defense_delta += clamp(goalkeeper_impact, -0.25, 0.20)
        notes.append(f"goalkeeperImpactAdjustment={round(goalkeeper_impact, 3)}")

    if has_number(team, "lineupContinuity"):
        continuity = clamp(fnum(team, "lineupContinuity", 1.0), 0.0, 1.0)
        continuity_penalty = (1.0 - continuity) * 0.12
        attack_delta -= continuity_penalty
        defense_delta -= continuity_penalty * 0.75
        notes.append(f"lineupContinuity={round(continuity, 3)}")

    if has_number(team, "regularStarterShare"):
        starter_share = clamp(fnum(team, "regularStarterShare", 0.75), 0.0, 1.0)
        starter_delta = (starter_share - 0.72) * 0.16
        attack_delta += starter_delta
        defense_delta += starter_delta * 0.65
        notes.append(f"regularStarterShare={round(starter_share, 3)}")

    if has_number(team, "clubMinutesShareLastYear"):
        minutes_share = clamp(fnum(team, "clubMinutesShareLastYear", 0.70), 0.0, 1.0)
        minutes_delta = (minutes_share - 0.68) * 0.12
        attack_delta += minutes_delta
        defense_delta += minutes_delta * 0.7
        notes.append(f"clubMinutesShareLastYear={round(minutes_share, 3)}")

    club_attack = fnum(team, "clubPerformanceAttackImpact", 0.0)
    club_defense = fnum(team, "clubPerformanceDefenseImpact", 0.0)
    if club_attack:
        attack_delta += clamp(club_attack, -0.20, 0.20)
        notes.append(f"clubPerformanceAttackImpact={round(club_attack, 3)}")
    if club_defense:
        defense_delta += clamp(club_defense, -0.20, 0.20)
        notes.append(f"clubPerformanceDefenseImpact={round(club_defense, 3)}")

    matches_14 = fnum(team, "matchesLast14Days", 0.0)
    matches_30 = fnum(team, "matchesLast30Days", 0.0)
    days_rest = fnum(team, "daysSinceLastMatch", 7.0)
    if matches_14 or matches_30 or has_number(team, "daysSinceLastMatch"):
        load_penalty = 0.0
        if days_rest < 4:
            load_penalty += (4.0 - days_rest) * 0.025
        if matches_14 > 3:
            load_penalty += (matches_14 - 3.0) * 0.018
        if matches_30 > 6:
            load_penalty += (matches_30 - 6.0) * 0.008
        if bool(team.get("extraTimeLastMatch", False)):
            load_penalty += 0.025
        load_penalty = clamp(load_penalty, 0.0, 0.18)
        attack_delta -= load_penalty
        defense_delta -= load_penalty * 0.85
        notes.append(
            f"fixtureLoad daysRest={round(days_rest, 2)}, matches14={round(matches_14, 2)}, matches30={round(matches_30, 2)}, penalty={round(load_penalty, 3)}"
        )

    if not notes:
        notes.append("no squad availability inputs; no automatic availability adjustment")

    return {
        "attack": clamp(attack_delta, -0.45, 0.20),
        "defense": clamp(defense_delta, -0.45, 0.20),
        "notes": notes,
    }


def special_factor_adjustment(context: dict[str, Any]) -> dict[str, Any]:
    factors = context.get("specialFactors", {})
    if not isinstance(factors, dict):
        factors = {}

    notes: list[str] = []
    tempo_multiplier = 1.0
    home_goal_delta = 0.0
    away_goal_delta = 0.0
    volatility_delta = 0.0

    pitch_quality = str(factors.get("pitchQuality", "normal")).lower()
    if pitch_quality in {"poor", "bad", "heavy"}:
        tempo_multiplier *= 0.94
        home_goal_delta -= 0.04
        away_goal_delta -= 0.04
        volatility_delta += 0.06
        notes.append("poor/heavy pitch lowers technical chance creation and raises error volatility")
    elif pitch_quality in {"excellent", "fast"}:
        tempo_multiplier *= 1.03
        notes.append("fast/excellent pitch slightly increases tempo")

    weather = str(factors.get("weatherSeverity", "normal")).lower()
    if weather in {"rain", "heavy_rain", "wind", "hot", "humid", "cold"}:
        if weather in {"heavy_rain", "wind"}:
            tempo_multiplier *= 0.93
            volatility_delta += 0.08
        elif weather in {"hot", "humid"}:
            tempo_multiplier *= 0.95
            volatility_delta += 0.04
        else:
            tempo_multiplier *= 0.97
            volatility_delta += 0.03
        notes.append(f"weatherSeverity={weather} affects tempo and execution")

    altitude_m = fnum(factors, "altitudeMeters", 0.0)
    if altitude_m >= 1200:
        away_goal_delta -= clamp((altitude_m - 1200.0) / 1000.0 * 0.05, 0.0, 0.12)
        tempo_multiplier *= 0.97
        notes.append(f"altitudeMeters={altitude_m:g} penalizes non-adapted away stamina")

    referee_cards = fnum(factors, "refereeCardsPerMatch", 0.0)
    if referee_cards >= 5.0:
        volatility_delta += 0.08
        notes.append(f"high card referee profile ({referee_cards:g}/match) raises red-card and set-piece volatility")
    elif 0.0 < referee_cards <= 3.2:
        volatility_delta -= 0.02
        notes.append(f"low card referee profile ({referee_cards:g}/match) lowers stoppage volatility")

    home_red_risk = fnum(factors, "homeRedCardRisk", 0.0)
    away_red_risk = fnum(factors, "awayRedCardRisk", 0.0)
    if home_red_risk:
        home_goal_delta -= clamp(home_red_risk * 0.35, 0.0, 0.12)
        away_goal_delta += clamp(home_red_risk * 0.20, 0.0, 0.08)
        volatility_delta += clamp(home_red_risk * 0.25, 0.0, 0.08)
        notes.append(f"homeRedCardRisk={round(home_red_risk, 3)}")
    if away_red_risk:
        away_goal_delta -= clamp(away_red_risk * 0.35, 0.0, 0.12)
        home_goal_delta += clamp(away_red_risk * 0.20, 0.0, 0.08)
        volatility_delta += clamp(away_red_risk * 0.25, 0.0, 0.08)
        notes.append(f"awayRedCardRisk={round(away_red_risk, 3)}")

    home_crowd = fnum(factors, "homeCrowdAdvantage", 0.0)
    if home_crowd:
        home_goal_delta += clamp(home_crowd, -0.08, 0.10)
        notes.append(f"homeCrowdAdvantage={round(home_crowd, 3)}")

    crowd_intensity = fnum(factors, "homeCrowdIntensity", 0.0)
    if crowd_intensity:
        crowd_bonus = clamp(crowd_intensity, 0.0, 1.0) * 0.06
        home_goal_delta += crowd_bonus
        volatility_delta += clamp(crowd_intensity, 0.0, 1.0) * 0.025
        notes.append(f"homeCrowdIntensity={round(crowd_intensity, 3)}")

    travel_fatigue = fnum(factors, "awayTravelFatigue", 0.0)
    if travel_fatigue:
        away_goal_delta -= clamp(travel_fatigue, 0.0, 1.0) * 0.06
        tempo_multiplier *= 1.0 - clamp(travel_fatigue, 0.0, 1.0) * 0.025
        notes.append(f"awayTravelFatigue={round(travel_fatigue, 3)}")

    motivation = str(factors.get("matchMotivation", "normal")).lower()
    if motivation in {"friendly", "rotation", "dead_rubber"}:
        tempo_multiplier *= 0.96
        volatility_delta += 0.04
        notes.append(f"matchMotivation={motivation} lowers intensity certainty")
    elif motivation in {"knockout", "must_win", "opening_match"}:
        volatility_delta += 0.03
        notes.append(f"matchMotivation={motivation} raises pressure volatility")

    return {
        "homeGoalAdjustment": round(clamp(home_goal_delta, -0.25, 0.25), 3),
        "awayGoalAdjustment": round(clamp(away_goal_delta, -0.25, 0.25), 3),
        "tempoMultiplier": round(clamp(tempo_multiplier, 0.82, 1.15), 3),
        "volatilityDelta": round(clamp(volatility_delta, -0.10, 0.25), 3),
        "notes": notes or ["no special factor inputs; no automatic special-factor adjustment"],
    }


def tactical_match_adjustment(team: dict[str, Any], opp: dict[str, Any], context: dict[str, Any], side: str) -> dict[str, Any]:
    tactical = context.get("tacticalFactors", {})
    if not isinstance(tactical, dict):
        tactical = {}

    team_prefix = "home" if side == "home" else "away"
    opp_prefix = "away" if side == "home" else "home"
    notes: list[str] = []
    goal_delta = 0.0
    volatility_delta = 0.0

    coaching = fnum(team, "inGameCoachingImpact", fnum(tactical, f"{team_prefix}InGameCoachingImpact", 0.0))
    if coaching:
        goal_delta += clamp(coaching, -0.16, 0.16)
        notes.append(f"{team_prefix}InGameCoachingImpact={round(coaching, 3)}")

    substitution = fnum(team, "benchImpact", fnum(tactical, f"{team_prefix}BenchImpact", 0.0))
    if substitution:
        goal_delta += clamp(substitution, -0.12, 0.14)
        notes.append(f"{team_prefix}BenchImpact={round(substitution, 3)}")

    pressing_adaptability = fnum(team, "pressingAdaptability", fnum(tactical, f"{team_prefix}PressingAdaptability", 0.0))
    buildup_weakness = fnum(opp, "buildupPressureWeakness", fnum(tactical, f"{opp_prefix}BuildupPressureWeakness", 0.0))
    if pressing_adaptability or buildup_weakness:
        press_edge = clamp(pressing_adaptability, 0.0, 1.0) * clamp(buildup_weakness, 0.0, 1.0) * 0.08
        goal_delta += press_edge
        volatility_delta += press_edge * 0.5
        notes.append(f"pressing adjustment edge={round(press_edge, 3)}")

    set_piece_attack = fnum(team, "setPieceAttackImpact", fnum(tactical, f"{team_prefix}SetPieceAttackImpact", 0.0))
    opp_set_piece_weakness = fnum(opp, "setPieceDefenseWeakness", fnum(tactical, f"{opp_prefix}SetPieceDefenseWeakness", 0.0))
    if set_piece_attack or opp_set_piece_weakness:
        set_piece_edge = clamp(set_piece_attack, -0.10, 0.18) + clamp(opp_set_piece_weakness, 0.0, 0.16)
        goal_delta += set_piece_edge
        volatility_delta += max(0.0, set_piece_edge) * 0.35
        notes.append(f"set-piece edge={round(set_piece_edge, 3)}")

    penalty_takers = fnum(team, "penaltyTakerReliability", fnum(tactical, f"{team_prefix}PenaltyTakerReliability", 0.76))
    penalty_pressure = fnum(tactical, "penaltyPressure", 0.0)
    penalty_frequency = fnum(tactical, "penaltyFrequency", 0.0)
    if penalty_frequency or penalty_pressure:
        penalty_edge = (clamp(penalty_takers, 0.55, 0.92) - 0.76) * clamp(penalty_frequency, 0.0, 1.0) * 0.12
        pressure_penalty = clamp(penalty_pressure, 0.0, 1.0) * 0.015
        goal_delta += penalty_edge - pressure_penalty
        volatility_delta += clamp(penalty_frequency, 0.0, 1.0) * 0.06
        notes.append(f"penalty edge={round(penalty_edge - pressure_penalty, 3)}")

    var_volatility = fnum(tactical, "varVolatility", 0.0)
    if var_volatility:
        volatility_delta += clamp(var_volatility, 0.0, 1.0) * 0.05
        notes.append(f"varVolatility={round(var_volatility, 3)}")

    return {
        "goalAdjustment": round(clamp(goal_delta, -0.30, 0.35), 3),
        "volatilityDelta": round(clamp(volatility_delta, 0.0, 0.20), 3),
        "notes": notes or [f"no {team_prefix} tactical-factor inputs; no automatic tactical adjustment"],
    }


def resolve_xg(
    team: dict[str, Any],
    direct_key: str,
    proxy_key: str,
    shot_prefix: str,
    goals_key: str,
    base_key: str,
    league_avg: float,
) -> dict[str, Any]:
    if has_number(team, direct_key):
        return {
            "value": fnum(team, direct_key, league_avg),
            "tier": "direct_xG",
            "notes": [f"used {direct_key}"],
        }
    if has_number(team, proxy_key):
        return {
            "value": fnum(team, proxy_key, league_avg),
            "tier": "proxy_xG",
            "notes": [f"used provided {proxy_key}"],
        }

    shot_proxy = proxy_xg_from_shots(team, shot_prefix)
    if shot_proxy is not None:
        return {
            "value": shot_proxy,
            "tier": "proxy_xG",
            "notes": [f"estimated from {shot_prefix} shots/SOT/big chances/box shots"],
        }

    goal_proxy = regressed_goals(team, goals_key, league_avg)
    if goal_proxy is not None:
        return {
            "value": goal_proxy,
            "tier": "goals_regressed_xG",
            "notes": [f"regressed {goals_key} toward league average"],
        }

    if has_number(team, base_key):
        return {
            "value": fnum(team, base_key, league_avg),
            "tier": "strength_prior_only",
            "notes": [f"used {base_key}; no direct/proxy recent xG inputs"],
        }

    return {
        "value": league_avg,
        "tier": "strength_prior_only",
        "notes": ["used league average; no direct/proxy recent xG inputs"],
    }


def combine_tiers(*tiers: str) -> str:
    order = ["direct_xG", "proxy_xG", "goals_regressed_xG", "strength_prior_only"]
    for tier in reversed(order):
        if tier in tiers:
            return tier
    return tiers[0] if tiers else "unknown"


def estimate_lambda(team: dict[str, Any], opp: dict[str, Any], context: dict[str, Any], side: str) -> dict[str, Any]:
    league_avg = fnum(context, "leagueAverageGoalsPerTeam", 1.35)
    recent_attack = resolve_xg(team, "recentXgFor", "proxyXgFor", "recent", "recentGoalsFor", "baseXgFor", league_avg)
    recent_defense = resolve_xg(opp, "recentXgAgainst", "proxyXgAgainst", "recentAgainst", "recentGoalsAgainst", "baseXgAgainst", league_avg)
    recent_xg_for = float(recent_attack["value"])
    season_xg_for = fnum(team, "seasonXgFor", fnum(team, "baseXgFor", recent_xg_for))
    opp_recent_xga = float(recent_defense["value"])
    opp_season_xga = fnum(opp, "seasonXgAgainst", fnum(opp, "baseXgAgainst", opp_recent_xga))
    team_elo = fnum(team, "elo", 1500)
    opp_elo = fnum(opp, "elo", 1500)

    attack = 0.62 * recent_xg_for + 0.38 * season_xg_for
    opponent_defense = 0.55 * opp_recent_xga + 0.45 * opp_season_xga
    raw = 0.55 * attack + 0.30 * opponent_defense + 0.15 * league_avg

    elo_goal_adjustment = clamp((team_elo - opp_elo) / 400.0 * 0.35, -0.35, 0.35)
    squad_adjustment = fnum(team, "squadGoalAdjustment", 0.0)
    own_availability = availability_adjustment(team, context)
    opp_availability = availability_adjustment(opp, context)
    tactical_adjustment = fnum(team, "tacticalGoalAdjustment", 0.0)
    rest_adjustment = fnum(team, "restGoalAdjustment", 0.0) - fnum(opp, "restGoalAdjustment", 0.0)

    neutral = bool(context.get("neutralVenue", False))
    home_adv = 0.0 if neutral else fnum(context, "homeAdvantageGoals", 0.12)
    venue_adjustment = home_adv if side == "home" else -home_adv * 0.55

    special = special_factor_adjustment(context)
    tactical_match = tactical_match_adjustment(team, opp, context, side)
    tempo = clamp(fnum(context, "tempoMultiplier", 1.0) * float(special["tempoMultiplier"]), 0.75, 1.25)
    special_goal_adjustment = float(special["homeGoalAdjustment"] if side == "home" else special["awayGoalAdjustment"])
    # If the opponent's defensive availability is weak (negative), this team's lambda increases.
    availability_goal_adjustment = own_availability["attack"] - opp_availability["defense"]
    lam = (
        raw
        + elo_goal_adjustment
        + squad_adjustment
        + availability_goal_adjustment
        + special_goal_adjustment
        + float(tactical_match["goalAdjustment"])
        + tactical_adjustment
        + rest_adjustment
        + venue_adjustment
    ) * tempo
    return {
        "lambda": clamp(lam, 0.20, 3.50),
        "xgInputTier": combine_tiers(str(recent_attack["tier"]), str(recent_defense["tier"])),
        "xgFallbackNotes": recent_attack["notes"] + recent_defense["notes"],
        "availabilityGoalAdjustment": round(availability_goal_adjustment, 3),
        "availabilityNotes": own_availability["notes"] + [f"opponent defense availability adjustment={round(-opp_availability['defense'], 3)}"],
        "specialFactorGoalAdjustment": round(special_goal_adjustment, 3),
        "specialFactorTempoMultiplier": special["tempoMultiplier"],
        "specialFactorVolatilityDelta": special["volatilityDelta"],
        "specialFactorNotes": special["notes"],
        "tacticalMatchGoalAdjustment": tactical_match["goalAdjustment"],
        "tacticalMatchVolatilityDelta": tactical_match["volatilityDelta"],
        "tacticalMatchNotes": tactical_match["notes"],
        "recentAttackInput": round(recent_xg_for, 3),
        "opponentDefenseInput": round(opp_recent_xga, 3),
    }


def score_matrix(home_lam: float, away_lam: float, max_goals: int, dc_rho: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson(h, home_lam) * poisson(a, away_lam)
            if dc_rho:
                if h == 0 and a == 0:
                    p *= 1 - home_lam * away_lam * dc_rho
                elif h == 0 and a == 1:
                    p *= 1 + home_lam * dc_rho
                elif h == 1 and a == 0:
                    p *= 1 + away_lam * dc_rho
                elif h == 1 and a == 1:
                    p *= 1 - dc_rho
                p = max(0.0, p)
            rows.append({"homeGoals": h, "awayGoals": a, "probability": p})

    total = sum(row["probability"] for row in rows)
    for row in rows:
        row["probability"] = row["probability"] / total if total else 0.0
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    home = sum(row["probability"] for row in rows if row["homeGoals"] > row["awayGoals"])
    draw = sum(row["probability"] for row in rows if row["homeGoals"] == row["awayGoals"])
    away = sum(row["probability"] for row in rows if row["homeGoals"] < row["awayGoals"])
    return normalize_probs({"homeWin": home, "draw": draw, "awayWin": away})


def maybe_blend(model: dict[str, float], market: dict[str, Any]) -> tuple[dict[str, float], dict[str, float] | None]:
    raw = {
        "homeWin": fnum(market, "homeWin", 0.0),
        "draw": fnum(market, "draw", 0.0),
        "awayWin": fnum(market, "awayWin", 0.0),
    }
    if sum(raw.values()) <= 0:
        odds = {
            "homeWin": fnum(market, "homeOdds", 0.0),
            "draw": fnum(market, "drawOdds", 0.0),
            "awayWin": fnum(market, "awayOdds", 0.0),
        }
        raw = {k: (1.0 / v if v > 1.0 else 0.0) for k, v in odds.items()}
    market_probs = normalize_probs(raw)
    if sum(market_probs.values()) <= 0:
        return model, None

    weight = clamp(fnum(market, "weight", 0.0), 0.0, 0.35)
    blended = {k: model[k] * (1 - weight) + market_probs[k] * weight for k in model}
    return normalize_probs(blended), market_probs


def pct(value: float) -> float:
    return round(value * 100, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: football_prediction_sim.py input.json", file=sys.stderr)
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    home = payload.get("home", {})
    away = payload.get("away", {})
    context = payload.get("context", {})
    market = payload.get("market", {})
    home_quality = data_quality(home, "home")
    away_quality = data_quality(away, "away")

    max_goals = int(fnum(context, "maxGoals", 8))
    dc_rho = clamp(fnum(context, "dixonColesRho", 0.0), -0.25, 0.25)
    home_estimate = estimate_lambda(home, away, context, "home")
    away_estimate = estimate_lambda(away, home, context, "away")
    home_lam = float(home_estimate["lambda"])
    away_lam = float(away_estimate["lambda"])
    rows = score_matrix(home_lam, away_lam, max_goals, dc_rho)
    model_probs = summarize(rows)
    calibration_temperature = clamp(fnum(context, "probabilityTemperature", 1.0), 0.70, 1.80)
    calibrated_model_probs = temperature_scale(model_probs, calibration_temperature)
    consensus_model_probs, consensus_meta = public_consensus_adjustment(calibrated_model_probs, context)
    final_probs, market_probs = maybe_blend(consensus_model_probs, market)
    top_scores = sorted(rows, key=lambda row: row["probability"], reverse=True)[:7]

    result = {
        "model": {
            "homeTeam": home.get("name", "Home"),
            "awayTeam": away.get("name", "Away"),
            "homeDataQuality": home_quality,
            "awayDataQuality": away_quality,
            "homeExpectedGoals": round(home_lam, 3),
            "awayExpectedGoals": round(away_lam, 3),
            "homeXgInputTier": home_estimate["xgInputTier"],
            "awayXgInputTier": away_estimate["xgInputTier"],
            "homeXgFallbackNotes": home_estimate["xgFallbackNotes"],
            "awayXgFallbackNotes": away_estimate["xgFallbackNotes"],
            "homeAvailabilityGoalAdjustment": home_estimate["availabilityGoalAdjustment"],
            "awayAvailabilityGoalAdjustment": away_estimate["availabilityGoalAdjustment"],
            "homeAvailabilityNotes": home_estimate["availabilityNotes"],
            "awayAvailabilityNotes": away_estimate["availabilityNotes"],
            "homeSpecialFactorGoalAdjustment": home_estimate["specialFactorGoalAdjustment"],
            "awaySpecialFactorGoalAdjustment": away_estimate["specialFactorGoalAdjustment"],
            "specialFactorTempoMultiplier": home_estimate["specialFactorTempoMultiplier"],
            "specialFactorVolatilityDelta": home_estimate["specialFactorVolatilityDelta"],
            "specialFactorNotes": home_estimate["specialFactorNotes"],
            "homeTacticalMatchGoalAdjustment": home_estimate["tacticalMatchGoalAdjustment"],
            "awayTacticalMatchGoalAdjustment": away_estimate["tacticalMatchGoalAdjustment"],
            "homeTacticalMatchNotes": home_estimate["tacticalMatchNotes"],
            "awayTacticalMatchNotes": away_estimate["tacticalMatchNotes"],
            "tacticalMatchVolatilityDelta": round(
                float(home_estimate["tacticalMatchVolatilityDelta"]) + float(away_estimate["tacticalMatchVolatilityDelta"]),
                3,
            ),
            "homeRecentAttackInput": home_estimate["recentAttackInput"],
            "awayRecentAttackInput": away_estimate["recentAttackInput"],
            "homeOpponentDefenseInput": home_estimate["opponentDefenseInput"],
            "awayOpponentDefenseInput": away_estimate["opponentDefenseInput"],
            "dixonColesRho": dc_rho,
            "probabilityTemperature": calibration_temperature,
            "maxGoals": max_goals,
        },
        "probability": {k: pct(v) for k, v in final_probs.items()},
        "rawModelProbability": {k: pct(v) for k, v in model_probs.items()},
        "calibratedModelProbability": {k: pct(v) for k, v in calibrated_model_probs.items()},
        "publicConsensusCalibratedProbability": {k: pct(v) for k, v in consensus_model_probs.items()},
        "publicConsensusCalibration": consensus_meta,
        "marketProbability": ({k: pct(v) for k, v in market_probs.items()} if market_probs else None),
        "scoreDistribution": [
            {
                "score": f"{row['homeGoals']}-{row['awayGoals']}",
                "probability": pct(row["probability"]),
            }
            for row in top_scores
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
