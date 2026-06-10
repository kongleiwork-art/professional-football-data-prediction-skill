---
name: professional-football-data-prediction
description: Use this skill to produce professional football match predictions from real pre-match data, including win/draw/loss probabilities, score distributions, tactical matchups, high-threat possession sequences, and detailed goal-chain breakdowns.
---

# Professional Football Data Prediction

Use this Skill when the user wants a football match prediction that is grounded in data and expressed with professional tactical language.

Only produce analytical sections for evidence, model parameters, probabilities, score distribution, tactical matchups, event flow, goal chains, and uncertainty.

## Core Workflow

Always work in this order:

1. Extract and timestamp available match data.
2. Mark missing or stale data instead of inventing it.
3. Convert evidence into model parameters.
4. Generate win/draw/loss probabilities and score distribution.
5. Identify decisive tactical matchups.
6. Produce 6 to 10 high-threat event-flow predictions.
7. Break down every predicted goal as a complete attacking chain.
8. List uncertainty factors that could materially change the forecast.

## Required Data Inputs

Prioritize current, verifiable match data:

- Fixture: teams, date, kickoff time, venue, stage, home/neutral status.
- Team form: recent 5 to 10 matches, goals for/against, xG/xGA if available.
- Squad state: injuries, suspensions, probable XI, formation, rotation risk.
- Player state: key attackers, creators, defenders, goalkeeper form.
- Tactical profile: build-up style, pressing height, transition speed, rest-defense, set-piece threat.
- Context: group table, knockout incentives, travel, rest days, weather, schedule congestion.

If a data field is unavailable, write that it is missing and lower certainty for any dependent conclusion.

## Model Parameters

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

Explain which evidence moved each important parameter.

## Probability Rules

- Output home win, draw, and away win as percentages summing to 100.
- Bind the probability explanation to at least three evidence categories.
- Avoid extreme probabilities unless the input data strongly supports them.
- Score distribution must align with the predicted event flow.

## Tactical Language

Use precise football terms when relevant:

- half-space
- rest-defense
- counter-pressing
- pressing trigger
- weak-side switch
- cutback
- third-man run
- second ball
- low block
- mid-block
- defensive line height
- channel between fullback and center-back
- zone 14
- box occupation
- blind-side run

Chinese output may use: 半空间、肋部、反压迫、压迫触发点、弱侧转移、倒三角、第三人跑动、二点球、低位防守、中位防守、防线身后、禁区占位、盲侧前插。

## Required Output Structure

Use these exact sections:

1. 数据输入摘要
2. 球队参数建模
3. 胜平负概率
4. 比分分布
5. 关键战术对位
6. 高威胁回合预测
7. 进球链路拆解
8. 不确定性因素

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

- Probabilities sum to 100.
- Every major probability claim cites data categories.
- Score distribution matches the event-flow story.
- Every predicted goal has a full chain from initiation to finish.
- Missing lineup, injury, or xG data is reflected in uncertainty.
- Output contains only the required professional prediction sections.
