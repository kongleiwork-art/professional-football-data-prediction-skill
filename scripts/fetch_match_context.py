#!/usr/bin/env python3
"""Fetch free/free-tier match context into the simulator JSON shape.

Supported:
  - Open-Meteo geocoding/weather: no key required.
  - football-data.org: optional FOOTBALL_DATA_API_TOKEN.
  - The Odds API: optional THE_ODDS_API_KEY.

The script degrades gracefully when keys or coverage are missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def source(name: str, status: str, url: str, notes: str) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "url": url,
        "retrievedAt": now_iso(),
        "notes": notes,
    }


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def classify_weather(temp_c: float | None, wind_kph: float | None, precipitation_mm: float | None) -> str:
    if precipitation_mm is not None and precipitation_mm >= 8:
        return "heavy_rain"
    if precipitation_mm is not None and precipitation_mm >= 1:
        return "rain"
    if wind_kph is not None and wind_kph >= 35:
        return "wind"
    if temp_c is not None and temp_c >= 30:
        return "hot"
    if temp_c is not None and temp_c <= 3:
        return "cold"
    return "normal"


def fetch_weather(venue: str, match_date: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not venue:
        return {}, [source("Open-Meteo", "missing", "", "venue not provided")]

    sources: list[dict[str, str]] = []
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": venue, "count": 1, "language": "en", "format": "json"}
    )
    try:
        geo = get_json(geocode_url)
    except Exception as exc:  # noqa: BLE001
        return {}, [source("Open-Meteo Geocoding", "error", geocode_url, str(exc))]

    results = geo.get("results") or []
    if not results:
        return {}, [source("Open-Meteo Geocoding", "missing", geocode_url, "no geocoding result")]

    place = results[0]
    lat = place.get("latitude")
    lon = place.get("longitude")
    altitude = place.get("elevation") or 0
    sources.append(source("Open-Meteo Geocoding", "ok", geocode_url, f"matched {place.get('name', venue)}"))

    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,precipitation_sum,wind_speed_10m_max",
            "timezone": "UTC",
            "start_date": match_date,
            "end_date": match_date,
        }
    )
    try:
        forecast = get_json(forecast_url)
    except Exception as exc:  # noqa: BLE001
        return {"altitudeMeters": altitude}, sources + [source("Open-Meteo Forecast", "error", forecast_url, str(exc))]

    daily = forecast.get("daily") or {}
    temp_values = daily.get("temperature_2m_max") or []
    precip_values = daily.get("precipitation_sum") or []
    wind_values = daily.get("wind_speed_10m_max") or []
    temp_c = temp_values[0] if temp_values else None
    precipitation_mm = precip_values[0] if precip_values else None
    wind_kph = wind_values[0] if wind_values else None
    weather = classify_weather(temp_c, wind_kph, precipitation_mm)
    sources.append(source("Open-Meteo Forecast", "ok", forecast_url, f"weatherSeverity={weather}"))
    return {
        "weatherSeverity": weather,
        "altitudeMeters": altitude,
        "temperatureMaxC": temp_c,
        "precipitationMm": precipitation_mm,
        "windMaxKph": wind_kph,
    }, sources


def fetch_football_data(home: str, away: str, match_date: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        return {}, [source("football-data.org", "missing", "https://www.football-data.org/", "FOOTBALL_DATA_API_TOKEN not set")]

    url = "https://api.football-data.org/v4/matches?" + urllib.parse.urlencode({"dateFrom": match_date, "dateTo": match_date})
    try:
        payload = get_json(url, {"X-Auth-Token": token})
    except Exception as exc:  # noqa: BLE001
        return {}, [source("football-data.org", "error", url, str(exc))]

    home_l = home.lower()
    away_l = away.lower()
    for match in payload.get("matches", []):
        h = (match.get("homeTeam") or {}).get("name", "")
        a = (match.get("awayTeam") or {}).get("name", "")
        if home_l in h.lower() and away_l in a.lower():
            return {
                "competition": (match.get("competition") or {}).get("name", ""),
                "date": match.get("utcDate", match_date),
                "status": match.get("status", ""),
            }, [source("football-data.org", "ok", url, "matched fixture")]

    return {}, [source("football-data.org", "missing", url, "fixture not found in available competitions")]


def fetch_odds(home: str, away: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    key = os.getenv("THE_ODDS_API_KEY")
    if not key:
        return {}, [source("The Odds API", "missing", "https://the-odds-api.com/", "THE_ODDS_API_KEY not set")]

    url = "https://api.the-odds-api.com/v4/sports/soccer/odds?" + urllib.parse.urlencode(
        {"apiKey": key, "regions": "eu,uk,us", "markets": "h2h", "oddsFormat": "decimal"}
    )
    try:
        payload = get_json(url)
    except Exception as exc:  # noqa: BLE001
        return {}, [source("The Odds API", "error", url, str(exc))]

    home_l = home.lower()
    away_l = away.lower()
    for event in payload if isinstance(payload, list) else []:
        if home_l not in str(event.get("home_team", "")).lower() or away_l not in str(event.get("away_team", "")).lower():
            continue
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                prices = {outcome.get("name", "").lower(): outcome.get("price") for outcome in market.get("outcomes", [])}
                return {
                    "homeOdds": prices.get(str(event.get("home_team", "")).lower()),
                    "awayOdds": prices.get(str(event.get("away_team", "")).lower()),
                    "drawOdds": prices.get("draw"),
                    "weight": 0.2,
                }, [source("The Odds API", "ok", url, f"matched bookmaker={bookmaker.get('title', '')}")]

    return {}, [source("The Odds API", "missing", url, "fixture odds not found")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--time", default="")
    parser.add_argument("--venue", default="")
    parser.add_argument("--competition", default="")
    parser.add_argument("--neutral", action="store_true")
    args = parser.parse_args()

    weather, weather_sources = fetch_weather(args.venue, args.date)
    fixture, fixture_sources = fetch_football_data(args.home, args.away, args.date)
    odds, odds_sources = fetch_odds(args.home, args.away)

    context = {
        "neutralVenue": bool(args.neutral),
        "homeAdvantageGoals": 0.0 if args.neutral else 0.12,
        "leagueAverageGoalsPerTeam": 1.35,
        "tempoMultiplier": 1.0,
        "specialFactors": {
            "weatherSeverity": weather.get("weatherSeverity", "normal"),
            "altitudeMeters": weather.get("altitudeMeters", 0),
        },
    }
    market = {"homeOdds": None, "drawOdds": None, "awayOdds": None, "weight": 0}
    market.update({k: v for k, v in odds.items() if v is not None})

    result = {
        "match": {
            "homeTeam": args.home,
            "awayTeam": args.away,
            "date": fixture.get("date", args.date),
            "time": args.time,
            "competition": fixture.get("competition", args.competition),
            "venue": args.venue,
            "homeNeutralAway": "neutral" if args.neutral else "home",
        },
        "home": {"name": args.home},
        "away": {"name": args.away},
        "context": context,
        "market": market,
        "sources": fixture_sources + weather_sources + odds_sources,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
