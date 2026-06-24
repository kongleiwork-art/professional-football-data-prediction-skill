---
name: professional-football-data-prediction
description: Use this skill to produce realistic, data-grounded football match predictions with verified public data, reproducible Poisson/Dixon-Coles/Elo-style reasoning, scenario-weighted match-state simulation, market-probability sanity checks, score distributions, tactical matchup analysis, post-match calibration, and uncertainty reporting.
---

# Professional Football Data Prediction

Use this Skill when the user wants a football match prediction optimized for accuracy, not hype. The output must be grounded in timestamped data, transparent assumptions, reproducible probability logic, football-specific tactical reasoning, and explicit post-match learning rules.

Do not present invented numbers as facts. If current data cannot be verified, mark it `missing` and widen uncertainty.

## Reference Approach

Model the match like a lightweight football analytics workflow inspired by open-source projects and public datasets:

- `soccerdata`: multi-source football data collection from FBref, Club Elo, Football-Data.co.uk, Understat, Sofascore, WhoScored, and related sources.
- `penaltyblog`: Poisson, bivariate Poisson, Dixon-Coles, Bayesian, Elo/Massey/Colley-style football modelling.
- `worldfootballR`: FBref, Understat, Transfermarkt, Fotmob extraction patterns.
- `football-data.co.uk`: historical results, match stats, and odds CSVs for backtesting and market checks.

For deeper analytics, read `docs/专业数据分析参考.md`.
For dynamic match-state and post-match learning, read `docs/赛后复盘与动态校准规则.md`.

Prefer the concepts above; do not claim an exact package was run unless it was actually run.

## Core Workflow

Always work in this order:

1. Define the fixture and prediction timestamp.
2. Gather current public data and record source names, URLs when available, dates, and freshness.
3. Separate confirmed facts from model assumptions.
4. Build a data table covering fixture, form, xG/xGA or proxy xG, Elo/rankings, squad news, tactics, special match factors, rest/travel/weather, and market odds when available.
5. Convert squad availability into explicit goal adjustments.
6. Classify the previous match performance as finishing variance, chance-creation problem, lineup problem, tactical problem, or opponent-specific problem.
7. Convert special match factors into explicit adjustments for goals, tempo, volatility, and confidence.
8. Estimate base expected goals for both teams from xG form or the xG fallback ladder, opponent defensive quality, Elo gap, venue, rest, squad availability, special factors, and tactical pace.
9. Build at least three game-state branches: no early goal, favorite scores early, underdog scores early.
10. Generate weighted win/draw/loss and score probabilities with a Poisson or Dixon-Coles-style score matrix. Use `scripts/football_prediction_sim.py` when numeric inputs are available.
11. Calibrate probabilities with held-out or walk-forward results when available; otherwise report calibration as missing.
12. Sanity-check the model against market-implied probabilities if reliable odds are available; do not let small exact-score price differences mechanically override the tactical model.
13. Convert probability drivers into 0-100 team parameters.
14. Simulate tactical match scripts: game state, pressing, transitions, set pieces, fatigue, red-card states, and substitution risk.
15. Output probabilities, score distribution, score-tail mass, tactical sequences, confidence layers, and uncertainty.
16. After full time, preserve the original model, market-adjusted model, and final recommendation, then classify the error type before changing any rule.

For free/free-tier API ingestion, use `scripts/fetch_match_context.py`. Treat API output as input context, not final prediction.

## Required Data Inputs

Prioritize current, verifiable match data:

- Fixture: teams, date, kickoff time, venue, competition, stage, home/neutral status.
- Team strength: Elo/ClubElo, FIFA ranking for national teams, league strength, season baseline.
- Recent form: last 5 to 10 matches with goals for/against, xG/xGA, shots, shots on target, shots conceded, big chances, box shots.
- Attack and defense quality: non-penalty xG, proxy xG, set-piece xG, open-play chance creation, box entries, shot quality.
- Squad state: available players, unavailable players, unavailable starters, doubtful starters, positional absences, injuries, suspensions, probable XI, formation, rotation risk, goalkeeper availability.
- Player state: key attackers, creators, defenders, goalkeeper shot-stopping and distribution.
- Tactical profile: build-up style, pressing height, transition speed, rest-defense, set-piece threat, main attack zones.
- Special factors: referee cards, red-card risk, pitch quality, weather, altitude, crowd pressure, table pressure, knockout incentives, rest days, travel, schedule congestion.
- Match-state factors: early-goal probability, favorite rebound signal, must-win pressure, bench depth, late-goal incentives.
- Market check: current 1X2, handicap, total-goals, and exact-score odds when available, converted to vig-free implied probabilities.

If a field is unavailable, write `missing` and reduce certainty for dependent conclusions.

## Data Source Priority

1. Official competition/team sources for fixture, venue, squads, suspensions, and kickoff time.
2. FBref/StatsBomb-style tables, Understat, FotMob, Sofascore, WhoScored, Opta-derived reports for xG, shots, and player form.
3. ClubElo or FIFA ranking for team-strength priors.
4. Football-Data.co.uk or open historical CSVs for results, odds, and backtesting.
5. Reputable news wires or club reporters for injuries and expected lineups.
6. Social media only as low-confidence context unless confirmed elsewhere.

Record source freshness. Treat lineup news older than 48 hours and injury news older than 7 days as stale unless reconfirmed.

## Modelling Rules

### Squad Availability

Do not treat injury news as a vague note. Convert it into a small explicit goal adjustment before estimating `lambda`.

Collect when possible:

- `availablePlayers`, `baselineAvailablePlayers`
- `unavailableStarters`, `doubtfulStarters`
- `unavailableAttackers`, `unavailableMidfielders`, `unavailableDefenders`
- `unavailableKeyPlayerGoalImpact`
- `keyPlayerAttackImpact`, `keyPlayerDefenseImpact`
- `goalkeeperImpactAdjustment`
- `lineupContinuity`, `regularStarterShare`, `clubMinutesShareLastYear`
- `clubPerformanceAttackImpact`, `clubPerformanceDefenseImpact`
- `daysSinceLastMatch`, `matchesLast14Days`, `matchesLast30Days`, `extraTimeLastMatch`

Default heuristic:

```text
depth_penalty = max(0, baselineAvailablePlayers - availablePlayers) * 0.012 goals
starter_penalty = unavailableStarters * 0.055 + doubtfulStarters * 0.028
attacker_penalty = unavailableAttackers * 0.045
midfielder_penalty = unavailableMidfielders * 0.025 to attack and defense
defender_penalty = unavailableDefenders * 0.045 to defensive stability
continuity_penalty = (1 - lineupContinuity) * 0.12
```

Apply attacking absences mostly to the team's own lambda. Apply defensive absences mostly by increasing the opponent's lambda. Keep total automatic adjustment bounded unless an elite-player absence is clearly documented.

### Expected Goals

Estimate `home_lambda` and `away_lambda` before creating probabilities.

Use this fallback ladder and label the chosen tier:

1. **Tier A - direct xG**
2. **Tier B - proxy xG**
3. **Tier C - regressed goals**
4. **Tier D - strength prior**

Recommended proxy xG when only shot data exists:

```text
proxy_xG_for = 0.06 * shots
             + 0.05 * shots_on_target
             + 0.18 * big_chances
             + 0.03 * box_shots
```

Use per-match averages. Cap proxy outputs to a realistic range, usually 0.3 to 3.2 per team.

Default weights unless competition-specific backtests support different ones:

- 40% recent xG form
- 25% season or tournament baseline
- 15% opponent defensive xGA
- 10% Elo/ranking strength prior
- 10% squad, venue, rest, weather, and tactical adjustments

For national teams with sparse data, increase Elo/ranking and squad-strength priors and lower confidence.

### Previous-Match Regression Discipline

Do not directly project one match into the next match.

Classify the previous performance:

```text
finishingVariance
chanceCreationProblem
lineupProblem
tacticalProblem
opponentSpecificProblem
```

Rules:

- Poor finishing with normal chance creation should not heavily reduce the next base attack estimate.
- Low shots, low box entries, and repeated buildup failure may justify a structural downgrade.
- One match cannot erase the season/tournament baseline.
- Require at least two similar matches before treating a tactical problem as a short-term trend.

### Elite-Team Rebound Signal

Use:

```text
eliteTeamReboundSignal: 0.00-1.00
```

Only activate it when evidence supports all or most of the following:

- the favorite underperformed in the previous match;
- squad and tactical structure remain intact;
- the next match carries response or must-win pressure;
- the new opponent is more vulnerable than the previous opponent;
- bench depth supports sustained pressure.

The signal may restore a small portion of base attack and increase 3+, 4+, and 5+ goal tails. It must never be treated as a guaranteed bounce-back.

### Match-State Scenario Tree

Do not rely on one static lambda path. At minimum create:

#### Scenario A: no goal in first 15 minutes

Use base lambda and the original tactical plan.

#### Scenario B: favorite scores in first 15 minutes

The underdog may raise its block, increase forward numbers, and concede transition space. Increase the favorite's upper-tail probability according to strength gap, bench depth, and the underdog's defensive recovery.

#### Scenario C: underdog scores in first 15 minutes

The favorite raises possession and attacking numbers. Increase draw, comeback, both-teams-to-score, and open-game tails.

Recommended fields:

```text
earlyGoalHazardFirst15
favoriteEarlyLeadProbability
underdogEarlyLeadProbability
earlyLeadTailMultiplier
lateGoalTailMultiplier
```

Aggregate the final score matrix by scenario weights.

### Special Match Factors

Collect when possible:

- `pitchQuality`
- `weatherSeverity`
- `altitudeMeters`
- `refereeCardsPerMatch`
- `homeRedCardRisk`, `awayRedCardRisk`
- `homeCrowdAdvantage`, `homeCrowdIntensity`
- `awayTravelFatigue`
- `matchMotivation`

These factors should change lambda, tempo, volatility, or confidence. Do not invent them.

### Tail-Risk Rules

Poisson baselines may understate state-dependent blowouts. Increase upper-tail mass when evidence supports:

- favorite scores early;
- underdog must chase the game;
- large bench-depth gap;
- opponent goalkeeper, center-back, or stamina weakness;
- red-card, penalty, VAR, own-goal, or goalkeeper-error volatility;
- goal-difference or qualification incentive remains late in the match.

Always output:

```text
scoreTail3Plus
scoreTail4Plus
scoreTail5Plus
tailRiskLevel: low | medium | high
```

### Probability Engine

- Use an independent Poisson score matrix as the default baseline.
- Apply Dixon-Coles-style low-score correlation when calibrated data exists.
- Run a deterministic matrix to at least 8 goals or a 20,000+ Monte Carlo equivalent.
- Output win/draw/loss probabilities summing to 100.
- Output 3 to 7 most likely exact scores.
- Avoid extreme probabilities unless several independent data categories support them.
- Report the aggregate probability of the core score pool, not only individual scores.

### Confidence Layers

Report separately:

```text
outcomeConfidence
totalGoalsConfidence
scorelineConcentration
tailRiskLevel
```

High confidence in the winner does not imply high confidence in one exact score.
Exact-score parlays must never be described as stable, conservative, or high probability.

### Market Calibration

If reliable odds exist:

1. Convert odds to implied probability.
2. Remove vig.
3. Compare against the model.
4. Blend only when the market is liquid and current.
5. Explain any disagreement larger than 8 percentage points.

For exact scores:

```text
impliedProbability = 1 / odds
relativeGap = abs(p1 - p2) / max(p1, p2)
```

Rules:

- If `relativeGap <= 8%`, the market has not clearly separated the two scores.
- Do not replace the model's preferred score only because one price is slightly shorter.
- Changing the core score requires at least two independent supporting signals.
- Preserve both `modelRank` and `marketRank`.
- Record whether the market improved or worsened the final choice after the match.

Market odds are a calibrator, not an automatic exact-score selector.

### Calibration Discipline

Before finalizing:

- Check favorite probability against xG gap, Elo gap, venue, squad news, and scenario tails.
- Use held-out or walk-forward calibration when historical predictions exist.
- Use temperature scaling only when fitted on past matches.
- Mention sample window, data cutoff time, missing variables, and model confidence.
- Preserve `preMarketModel`, `marketAdjustedModel`, and `finalRecommendation`.

Use:

```bash
python3 scripts/calibrate_probabilities.py predictions.csv
python3 scripts/backtest_predictions.py data/historical_predictions_template.csv
```

### Post-Match Error Classification

After full time, assign one or more labels:

```text
result_direction_error
exact_score_error
total_goals_error
favorite_tail_underestimated
early_goal_scenario_missed
market_override_error
lineup_update_missed
tactical_matchup_error
random_event_tail
```

Do not change global weights after one match. Treat a new idea as a candidate rule until the same error appears in at least 5 comparable matches and improves walk-forward metrics.

## Team Parameters

Translate evidence into 0 to 100 parameters:

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

High-threat sequences are not random storytelling:

- Higher lambda creates more and better chance chains.
- High transition speed plus weak rest-defense creates counterattacks.
- High pressing intensity plus poor buildup creates turnovers and second attacks.
- High set-piece threat plus aerial weakness creates set-piece and second-ball sequences.
- Strong in-game coaching changes the second-half script.
- Penalty and VAR risk should appear as volatility, not a guaranteed goal.
- Fatigue, game state, and substitutions should change the second-half script.
- Most high-threat sequences should not be goals.

## Required Output Structure

Use these sections:

1. 数据输入摘要
2. 模型假设与数据质量
3. 上一场表现归因与反弹信号
4. 球队参数建模
5. 基础期望进球与比赛状态分支
6. 胜平负概率
7. 总进球与尾部概率
8. 比分分布与比分池集中度
9. 市场校准与模型排序对比
10. 关键战术对位
11. 高威胁回合预测
12. 进球链路拆解
13. 不确定性因素

## High-Threat Event Format

```text
第 18-22 分钟｜主队｜中路渗透｜威胁等级 72/100
发起：后腰在中圈右侧接中卫出球，对方第一道压迫没有形成包夹。
推进：8 号位向右肋移动形成接应，边锋内收占据半空间，边后卫外侧套上拉宽防线。
关键动作：前腰背身回做，后腰第一时间直塞打中卫与边后卫之间的通道。
防守反应：客队中卫横移补位，后腰回追慢半拍，门将站位靠近近角。
终结：禁区右侧小角度射门，被门将封出。
成立原因：主队右路推进速度高于客队边路回防速度。
```

Goal sequences must also include:

```text
进球方式：倒三角回传 / 肋部直塞 / 边路传中 / 高位逼抢二次进攻 / 定位球二点
预期进球质量：高 / 中 / 低
防守失误点：边后卫失位 / 中卫被带出 / 后腰漏人 / 门将视线受阻
所属情景：无早球 / 强队早球 / 弱队早球 / 红牌尾部 / 随机事件尾部
```

## Consistency Checks

Before final output, verify:

- Data source dates and model timestamp are visible.
- Confirmed facts and assumptions are separated.
- Probabilities sum to 100.
- Base expected goals are consistent with the weighted scenario matrix.
- Previous-match underperformance is classified, not blindly extrapolated.
- Early-goal branches are included.
- 3+, 4+, and 5+ score tails are visible.
- Outcome confidence and exact-score confidence are separate.
- Score distribution matches the event-flow story.
- Market exact-score gaps are large enough before overriding the model.
- `preMarketModel`, `marketAdjustedModel`, and `finalRecommendation` are preserved.
- Missing lineup, injury, odds, or xG data is reflected in uncertainty.
- No fabricated source, stat, lineup, injury, or odds is presented as verified.
- No exact-score parlay is described as stable or high probability.
