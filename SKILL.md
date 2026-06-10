---
name: professional-football-data-prediction
description: Use this skill to produce realistic, data-grounded football match predictions with verified public data, reproducible Poisson/Dixon-Coles/Elo-style reasoning, market-probability sanity checks, score distributions, tactical matchup simulation, and uncertainty reporting.
---

# Professional Football Data Prediction

Use this Skill when the user wants a football match prediction optimized for accuracy, not hype. The output must be grounded in timestamped data, transparent assumptions, reproducible probability logic, and football-specific tactical reasoning.

Do not present invented numbers as facts. If current data cannot be verified, mark it missing and widen uncertainty.

## Reference Approach

Model the match like a lightweight football analytics workflow inspired by open-source projects and public datasets:

- `soccerdata`: multi-source football data collection from FBref, Club Elo, Football-Data.co.uk, Understat, Sofascore, WhoScored, and related sources.
- `penaltyblog`: Poisson, bivariate Poisson, Dixon-Coles, Bayesian, Elo/Massey/Colley-style football modelling.
- `worldfootballR`: FBref, Understat, Transfermarkt, Fotmob extraction patterns.
- `football-data.co.uk`: historical results, match stats, and odds CSVs for backtesting and market checks.

For deeper analytics, read `docs/专业数据分析参考.md`. It maps StatsBomb Open Data, socceraction/VAEP, soccer_xg, penaltyblog, goalmodel, kloppy, and mplsoccer concepts into this skill's prediction fields.

Prefer the concepts above; do not claim an exact package was run unless it was actually run.

## Core Workflow

Always work in this order:

1. Define the fixture and prediction timestamp.
2. Gather current public data and record source names, URLs when available, dates, and freshness.
3. Separate confirmed facts from model assumptions.
4. Build a data table covering fixture, form, xG/xGA or proxy xG, Elo/rankings, squad news, tactics, special match factors, rest/travel/weather, and market odds when available.
5. Convert squad availability into explicit goal adjustments from available players, unavailable starters, doubtful starters, positional absences, and key-player impact.
6. Convert special match factors into explicit adjustments for goals, tempo, volatility, and confidence.
7. Estimate expected goals for both teams from xG form or the xG fallback ladder, opponent defensive quality, Elo gap, venue, rest, squad availability, special factors, and tactical pace.
8. Generate win/draw/loss and score probabilities with a Poisson or Dixon-Coles-style score matrix. Use `scripts/football_prediction_sim.py` when numeric inputs are available.
9. Calibrate probabilities with held-out or walk-forward results when available; otherwise report calibration as missing.
10. Calibrate or sanity-check the model against market-implied probabilities if reliable odds are available; explain any large disagreement.
11. Convert probability drivers into 0-100 team parameters.
12. Simulate tactical match scripts: game state, pressing, transitions, set pieces, fatigue, red-card states, and substitution risk.
13. Output probabilities, score distribution, high-threat sequences, predicted goal chains, and uncertainty.

When the user asks for more professional data analysis, add one or more layers from `docs/专业数据分析参考.md`: shot-level xG, VAEP/action value, set-piece profile, low-score calibration, or visual evidence.

## Required Data Inputs

Prioritize current, verifiable match data:

- Fixture: teams, date, kickoff time, venue, competition, stage, home/neutral status.
- Team strength: Elo/ClubElo, FIFA ranking for national teams, league strength, season baseline.
- Recent form: last 5 to 10 matches with goals for/against, xG/xGA, shots, shots on target, shots conceded, big chances, box shots.
- Attack and defense quality: non-penalty xG, proxy xG when official xG is missing, set-piece xG, open-play chance creation, box entries, shot quality.
- Squad state: available players, unavailable players, unavailable starters, doubtful starters, positional absences, injuries, suspensions, probable XI, formation, rotation risk, goalkeeper availability.
- Player state: key attackers, creators, defenders, goalkeeper shot-stopping and distribution.
- Tactical profile: build-up style, pressing height, transition speed, rest-defense, set-piece threat, main attack zones.
- Special factors: referee cards, red-card risk, pitch quality, weather, altitude, crowd pressure, table pressure, knockout incentives, rest days, travel, schedule congestion.
- Market check: closing or current 1X2 odds when available, converted to vig-free implied probabilities.

If a field is unavailable, write `missing` and reduce certainty for dependent conclusions.

## Data Source Priority

Use the best available sources for the specific competition:

1. Official competition/team sources for fixture, venue, squads, suspensions, and kickoff time.
2. FBref/StatsBomb-style tables, Understat, FotMob, Sofascore, WhoScored, Opta-derived reports for xG, shots, and player form.
3. ClubElo or FIFA ranking for team-strength priors.
4. Football-Data.co.uk or Kaggle/open historical CSVs for results, odds, and backtesting.
5. Reputable news wires or club reporters for injuries and expected lineups.
6. Social media only as low-confidence context unless confirmed elsewhere.

Record source freshness. Treat lineup news older than 48 hours and injury news older than 7 days as stale unless reconfirmed.

## Modelling Rules

### Squad Availability

Do not treat injury news as a vague note. Convert it into a small explicit goal adjustment before estimating `lambda`.

Collect these fields when possible:

- `availablePlayers`: players expected to be available from the match squad or camp list.
- `baselineAvailablePlayers`: normal matchday/camp baseline, usually 23 unless the competition differs.
- `unavailableStarters`: expected starters ruled out.
- `doubtfulStarters`: expected starters uncertain.
- `unavailableAttackers`, `unavailableMidfielders`, `unavailableDefenders`: positional absence counts.
- `unavailableKeyPlayerGoalImpact`: manual 0.00-0.30 estimate for an elite player absence.
- `keyPlayerAttackImpact`: signed goal adjustment for named attackers/creators being available or missing.
- `keyPlayerDefenseImpact`: signed goal adjustment for named defenders/midfield screen players being available or missing.
- `goalkeeperImpactAdjustment`: signed defensive goal adjustment for goalkeeper availability/form.
- `lineupContinuity`: 0-1 estimate of how close the XI is to the normal first-choice structure.
- `regularStarterShare`: share of expected XI who are regular starters for club or national team.
- `clubMinutesShareLastYear`: expected XI's recent club-minute reliability over the last year.
- `clubPerformanceAttackImpact` / `clubPerformanceDefenseImpact`: signed adjustments from club form, role, and level.
- `daysSinceLastMatch`, `matchesLast14Days`, `matchesLast30Days`, `extraTimeLastMatch`: fixture load and recovery.

### Tactical Management, Set Pieces, Penalties

Add a tactical-match layer when evidence exists:

- `inGameCoachingImpact`: signed goal adjustment for coach game management, tactical flexibility, and halftime/substitution patterns.
- `benchImpact`: signed adjustment for substitute quality and role fit.
- `pressingAdaptability`: ability to change pressing height/triggers during the match.
- `buildupPressureWeakness`: opponent vulnerability to pressing and forced turnovers.
- `setPieceAttackImpact`: attacking set-piece routines, aerial targets, blockers, second-ball structure.
- `setPieceDefenseWeakness`: defensive set-piece marking, goalkeeper command, second-ball protection.
- `penaltyTakerReliability`: likely penalty taker's conversion reliability under pressure.
- `penaltyFrequency`, `penaltyPressure`, `varVolatility`: match-level penalty/VAR environment.

These factors should influence lambda, volatility, and event flow. Do not write “good coach” or “set pieces strong” without explaining which phase changes: halftime shape, pressing trigger, corner routine, free-kick delivery, penalty taker, or VAR/handball risk.

Default heuristic:

```text
depth_penalty = max(0, baselineAvailablePlayers - availablePlayers) * 0.012 goals
starter_penalty = unavailableStarters * 0.055 + doubtfulStarters * 0.028
attacker_penalty = unavailableAttackers * 0.045
midfielder_penalty = unavailableMidfielders * 0.025 to attack and defense
defender_penalty = unavailableDefenders * 0.045 to defensive stability
continuity_penalty = (1 - lineupContinuity) * 0.12
```

Apply attacking absences mostly to the team's own lambda. Apply defensive absences mostly by increasing the opponent's lambda. Keep total automatic availability adjustment bounded unless an elite-player absence is clearly documented.

### Expected Goals

Estimate `home_lambda` and `away_lambda` before creating probabilities.

When direct recent xG/xGA is missing, do not jump straight to a vague conservative estimate. Use this fallback ladder and label the chosen tier:

1. **Tier A - direct xG**: recent non-penalty xG/xGA from FBref, Understat, FotMob, Sofascore, WhoScored, Opta-derived reports, or official technical reports.
2. **Tier B - proxy xG**: estimate chance quality from per-match shots, shots on target, big chances, box shots, set-piece shots, and opponent strength. Mark the field as `proxy_xG`.
3. **Tier C - regressed goals**: combine recent goals for/against with league or national-team average goals and opponent strength. Mark the field as `goals_regressed_xG`.
4. **Tier D - strength prior**: use Elo/ranking, squad availability, market odds, venue, and tactical matchup only. Mark the field as `strength_prior_only` and keep confidence low.

Recommended proxy xG heuristic when only shot data exists:

```text
proxy_xG_for = 0.06 * shots
             + 0.05 * shots_on_target
             + 0.18 * big_chances
             + 0.03 * box_shots
```

Use per-match averages. Cap proxy outputs to a realistic range, usually 0.3 to 3.2 per team. Adjust downward if the shot sample came against weak opposition; adjust upward only with clear evidence of high-quality chances.

Use this structure when data exists:

```text
base_team_attack = weighted recent non-penalty xG for + season attack baseline
opponent_defense_adjustment = opponent xGA / league average
strength_adjustment = Elo/ranking gap converted to a small goal adjustment
venue_adjustment = home advantage, neutral venue, travel, altitude, weather
squad_adjustment = missing starters, goalkeeper change, rotation, minutes load
tactical_adjustment = pace, press resistance, transition exposure, set-piece mismatch
lambda = bounded expected goals, usually 0.2 to 3.5
```

Use conservative weights unless a competition-specific backtest supports different ones:

- 40% recent xG form
- 25% season or tournament baseline
- 15% opponent defensive xGA
- 10% Elo/ranking strength prior
- 10% squad, venue, rest, weather, and tactical adjustments

For national teams with sparse recent data, increase Elo/ranking and squad-strength priors and lower confidence.

### Special Match Factors

Every prediction must include a special-factor layer. These factors should affect goal expectation, tempo, volatility, or confidence rather than being buried only in uncertainty.

Collect these fields when possible:

- `pitchQuality`: excellent, normal, poor, heavy.
- `weatherSeverity`: normal, rain, heavy_rain, wind, hot, humid, cold.
- `altitudeMeters`: venue altitude.
- `refereeCardsPerMatch`: referee yellow/red-card profile when assigned.
- `homeRedCardRisk` / `awayRedCardRisk`: team discipline risk from recent cards, tactical fouling, emotional pressure, referee profile.
- `homeCrowdAdvantage`: additional venue/crowd pressure beyond ordinary home advantage.
- `homeCrowdIntensity`: 0-1 estimate of atmosphere intensity from home crowd, opening match, rivalry, stadium size, and ticketing context.
- `awayTravelFatigue`: 0-1 estimate from travel distance, time zones, altitude adaptation, and short turnaround.
- `matchMotivation`: friendly, rotation, dead_rubber, opening_match, knockout, must_win.

Default effects:

```text
poor/heavy pitch: lower tempo and technical chance quality; raise error volatility
heavy rain/wind: lower shot/pass quality; raise set-piece and goalkeeper-error volatility
hot/humid weather: lower late-game pressing and transition recovery
high-card referee: raise red-card, penalty, set-piece, and match-state volatility
high red-card risk team: slightly lower own lambda, slightly raise opponent tail outcomes
altitude: penalize non-adapted away stamina and late defensive recovery
friendly/rotation: lower intensity certainty, increase substitution noise
opening/knockout/must-win: raise pressure volatility and game-state sensitivity
```

If no reliable source confirms a factor, mark it missing or assumed. Do not invent referee assignments, pitch problems, or weather.

### Probability Engine

- Use an independent Poisson score matrix as the default baseline.
- Apply Dixon-Coles-style low-score correlation when calibrated data exists, especially for 0-0, 1-0, 0-1, and 1-1.
- Run at least a deterministic score matrix up to 8 goals or a 20,000+ Monte Carlo equivalent.
- Output win/draw/loss probabilities summing to 100.
- Output 3 to 7 most likely exact scores; their probabilities do not need to sum to 100.
- Avoid extreme probabilities unless multiple independent data categories support them.
- If market odds exist, convert to implied probabilities, remove vig, and compare against the model. Blend only if the market is liquid and current; otherwise use it as a sanity check.

### Calibration Discipline

Before finalizing:

- Check whether the favorite probability is plausible relative to xG gap, Elo gap, venue, and squad news.
- If historical predictions/results exist, run a held-out or walk-forward calibration check with Brier score, log loss, and expected calibration error.
- Use temperature scaling to soften or sharpen probabilities only when fit on past matches, not on the match being predicted.
- Apply public-consensus calibration only as a conservative prior when no local backtest is available: World Cup favorites, public models, and markets often overstate heavy favorites, understate draw/upset tails, and miss rotation/match-state variance.
- If model and market differ by more than 8 percentage points on any outcome, explain why.
- State model confidence as high, medium, or low based on data completeness and source agreement.
- Mention sample window, data cutoff time, and missing variables.

Open-source calibration patterns to emulate:

- Walk-forward out-of-sample backtests, as seen in World Cup prediction repos with separate backtest and calibration scripts.
- Football probability scoring, as exposed by `goalmodel`-style `score_predictions()` functions: Brier, log loss, ranked probability scores.
- Prior/predictive checks before validation, as used in Bayesian football prediction projects.

Use `scripts/calibrate_probabilities.py predictions.csv` when a CSV of past predictions and outcomes is available.

Use `scripts/backtest_predictions.py data/historical_predictions_template.csv` after matches finish to track result accuracy, exact-score accuracy, Brier, log loss, and total-goals error. Keep appending predictions before kickoff and final scores after full time.

### Public Consensus Calibration

Use `publicConsensusCalibration` to adjust model probabilities toward historically observed prediction-to-result gaps:

- Group-stage heavy favorites: shrink favorite probability slightly and add draw/upset tail.
- Friendlies/warmups: shrink favorite probability for rotation and motivation uncertainty.
- Knockouts: shrink regulation-time favorite probability for lower tempo, extra-time, penalty, and game-state tails.
- If local backtest data exists, prefer it over these defaults.
- Always report this as a calibration prior, not as a verified truth for the current match.

## Team Parameters

Translate evidence into 0 to 100 parameters for both teams:

- attackStrength
- defensiveStability
- transitionSpeed
- pressingIntensity
- possessionControl
- setPieceThreat
- goalkeeperImpact
- staminaProfile
- tacticalCoherence
- volatility

Each important parameter must cite the evidence or assumption that moved it.

## Tactical Simulation

High-threat sequences are not random storytelling. Derive them from the model:

- Higher `lambda` means more and better chance chains.
- High transitionSpeed plus opponent weak rest-defense creates counterattack sequences.
- High pressingIntensity plus opponent poor build-up creates turnovers and second attacks.
- High setPieceThreat plus opponent aerial weakness creates set-piece and second-ball sequences.
- Strong in-game coaching creates second-half script changes: pressing height, fullback role, midfield box, striker pairing, or earlier substitutions.
- Strong set-piece edge creates corner/free-kick/second-ball sequences and increases low-open-play scoring paths.
- Penalty and VAR risk should appear as volatility, not as a guaranteed goal.
- Fatigue, game state, and substitutions should change the second-half script.
- Most high-threat sequences should not be goals.

## Required Output Structure

Use these exact sections:

1. 数据输入摘要
2. 模型假设与数据质量
3. 球队参数建模
4. 胜平负概率
5. 比分分布
6. 关键战术对位
7. 高威胁回合预测
8. 进球链路拆解
9. 不确定性因素

## High-Threat Event Format

Each high-threat sequence must use this format:

```text
第 18-22 分钟｜主队｜中路渗透｜威胁等级 72/100
发起：后腰在中圈右侧接中卫出球，对方第一道压迫没有形成包夹。
推进：8 号位向右肋移动形成接应，边锋内收占据半空间，边后卫外侧套上拉宽防线。
关键动作：前腰背身回做，后腰第一时间直塞打中卫与边后卫之间的通道。
防守反应：客队中卫横移补位，后腰回追慢半拍，门将站位靠近近角。
终结：禁区右侧小角度射门，被门将封出。
成立原因：主队右路推进速度高于客队边路回防速度，且客队双后腰保护禁区弧顶不够及时。
```

Goal sequences must also include:

```text
进球方式：倒三角回传 / 肋部直塞 / 边路传中 / 高位逼抢二次进攻 / 定位球二点
预期进球质量：高 / 中 / 低
防守失误点：边后卫失位 / 中卫被带出 / 后腰漏人 / 门将视线受阻
```

## Consistency Checks

Before final output, verify:

- Data source dates and model timestamp are visible.
- Confirmed facts and assumptions are separated.
- Probabilities sum to 100.
- Expected goals are consistent with score distribution.
- Score distribution matches the event-flow story.
- Every predicted goal has a full chain from initiation to finish.
- Missing lineup, injury, odds, or xG data is reflected in uncertainty.
- Special factors are listed as confirmed, missing, or assumptions and reflected in lambda/tempo/volatility.
- No fabricated source, stat, lineup, or injury is presented as verified.
