# API 接入说明

目标：把免费或免费额度 API 接到统一 match context JSON，再交给 `football_prediction_sim.py`。

## 已支持

### Open-Meteo Geocoding + Forecast

- 费用：免费，无 API key。
- 用途：城市经纬度、天气、风速、温度、降水。
- 映射：`context.specialFactors.weatherSeverity`、天气来源记录。

### football-data.org

- 费用：免费额度，需要 token。
- 环境变量：`FOOTBALL_DATA_API_TOKEN`
- 用途：赛程、比分、基础比赛信息。
- 限制：免费层覆盖赛事有限，国家队友谊赛/世界杯数据不一定全。

### The Odds API

- 费用：免费额度，需要 key。
- 环境变量：`THE_ODDS_API_KEY`
- 用途：1X2 欧赔。
- 映射：`market.homeOdds`、`market.drawOdds`、`market.awayOdds`。

## 使用

```bash
python3 scripts/fetch_match_context.py \
  --home Portugal \
  --away Nigeria \
  --date 2026-06-10 \
  --venue "Lisbon"
```

有 key 时：

```bash
FOOTBALL_DATA_API_TOKEN=... THE_ODDS_API_KEY=... \
python3 scripts/fetch_match_context.py --home Portugal --away Nigeria --date 2026-06-10 --venue Lisbon
```

输出 JSON 可以保存后手工补充 xG、阵容、战术因素，再喂给：

```bash
python3 scripts/football_prediction_sim.py fetched-context.json
```

## 原则

- API 缺失时，不伪造数据，写入 `sources.status = missing`。
- API 报错时，不中断整体输出，写入 `sources.status = error`。
- API 数据只作为输入层，仍需模型解释、校准和不确定性说明。
