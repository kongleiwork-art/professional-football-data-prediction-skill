# Professional Football Data Prediction Skill

一个用于专业足球赛前预测的 Skill：先抽取真实数据，再建立期望进球和比分概率底座，最后生成模型参数、胜平负概率、比分分布、关键战术对位、高威胁回合和进球链路拆解。

这个仓库不做平台文案生成，也不走泛泛的球迷聊天风格。它的重点是把公开赛前数据转成可解释、可校验、尽量可复现的专业预测报告。

## What It Does

- 抽取并标注赛程、近况、xG/xGA、Elo/排名、赔率、伤停、预计首发、阵型、球员状态、休息天数等输入。
- 区分确认事实、过期数据、缺失数据和模型假设。
- 将可上场人数、缺阵主力、存疑主力和位置分布折算成阵容可用性进球调整。
- 支持关键球员攻击/防守/门将影响权重，而不是只按缺阵人数处理。
- 用 Poisson / Dixon-Coles 风格比分矩阵或等价蒙特卡洛逻辑生成胜平负概率和 3-7 个比分分布。
- 支持用历史预测 CSV 做 Brier、log loss、ECE 和 temperature scaling 校准。
- 支持用市场赔率做去水后的概率校准或 sanity check。
- 将证据转换为 `attackStrength`、`defensiveStability`、`transitionSpeed`、`pressingIntensity` 等 0-100 模型参数。
- 分析关键战术对位，例如半空间、肋部、防线身后、rest-defense、弱侧转移、倒三角和二点球。
- 生成 6-10 个高威胁回合预测。
- 对每个预测进球拆解完整链路：发起、推进、关键动作、防守反应、终结和成立原因。

## Open-Source Method References

设计思路参考这些公开项目和数据流：

- `soccerdata`：多源足球数据抽取，例如 FBref、Club Elo、Football-Data.co.uk、Understat、Sofascore、WhoScored。
- `penaltyblog`：Poisson、Bivariate Poisson、Dixon-Coles、Bayesian、Elo/Massey/Colley 等足球模型。
- `worldfootballR`：FBref、Understat、Transfermarkt、Fotmob 数据抽取。
- `football-data.co.uk`：历史赛果、技术统计和赔率 CSV。

除非实际运行对应工具，否则报告里只写“方法参考”，不要写“已使用该包计算”。

## Repository Structure

```text
.
├── SKILL.md
├── scripts/
│   └── football_prediction_sim.py
│   └── calibrate_probabilities.py
│   └── backtest_predictions.py
│   └── shot_xg_proxy.py
├── data/
│   └── historical_predictions_template.csv
├── skill/
│   └── 专业预测可复制版.txt
├── docs/
│   ├── 使用说明.md
│   ├── 数据抽取有根据.md
│   ├── 模型规则.md
│   ├── 专业数据分析参考.md
│   └── 事件流规则.md
├── prompts/
│   ├── 01_先抽取数据.txt
│   ├── 02_生成专业预测.txt
│   ├── 03_生成事件流解说.txt
│   └── 04_生成结构化预测JSON.txt
├── templates/
│   ├── match_input_template.json
│   ├── evidence_table_template.json
│   └── professional_prediction_output_schema.json
└── examples/
    ├── 示例_法国_vs_阿根廷.md
    └── 示例_墨西哥_vs_加拿大.json
```

## Quick Start

复制 [skill/专业预测可复制版.txt](skill/%E4%B8%93%E4%B8%9A%E9%A2%84%E6%B5%8B%E5%8F%AF%E5%A4%8D%E5%88%B6%E7%89%88.txt) 到你使用的 AI 工具里，然后输入比赛信息：

```text
请用专业足球数据预测 Skill 分析这场比赛：

比赛：法国 vs 阿根廷
比赛时间：2026-06-20 20:00
比赛阶段：淘汰赛
场地：待确认
主客/中立场：中立场
可用数据：请优先联网核对最新赛程、近况、伤停、预计首发、xG/xGA、进失球、Elo/排名、赔率和休息天数。
我重点关注：期望进球、胜平负概率、比分分布、关键战术对位、高威胁回合、进球链路拆解。
输出语言：中文，专业术语充分。
```

## Reproducible Probability Helper

如果已经有结构化输入，可以填 `templates/match_input_template.json` 后运行：

```bash
python3 scripts/football_prediction_sim.py templates/match_input_template.json
```

输出包括：

- `homeExpectedGoals` / `awayExpectedGoals`
- 原始模型胜平负概率
- 可选市场校准概率
- 最可能比分分布

## Calibration Helper

如果有历史预测和赛果 CSV：

```bash
python3 scripts/backtest_predictions.py data/historical_predictions_template.csv
python3 scripts/calibrate_probabilities.py predictions.csv
```

CSV 格式：

```text
homeWin,draw,awayWin,result
0.52,0.27,0.21,H
```

输出包括 Brier、log loss、ECE 和建议的 temperature。

`backtest_predictions.py` 输出赛果命中率、精确比分命中率、Brier、log loss 和总进球误差。

## Required Output

每次分析固定输出以下部分：

1. 数据输入摘要
2. 模型假设与数据质量
3. 球队参数建模
4. 胜平负概率
5. 比分分布
6. 关键战术对位
7. 高威胁回合预测
8. 进球链路拆解
9. 不确定性因素

## Data Discipline

- 数据缺失时要明确标注，不把缺失数据写成事实。
- 概率判断至少绑定 4 类数据依据。
- 必须展示两队期望进球，并说明主要调整项。
- 比分分布必须和事件流一致。
- 高威胁回合不等于进球，大多数回合可以以射门、扑救、封堵、偏出或解围结束。
- 如果预测 `2-1`，事件流必须能解释 3 个进球和若干未转化机会。

## Professional Analytics References

See [docs/专业数据分析参考.md](docs/%E4%B8%93%E4%B8%9A%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90%E5%8F%82%E8%80%83.md) for how to map StatsBomb Open Data, socceraction/VAEP, soccer_xg, penaltyblog, goalmodel, kloppy, and mplsoccer into this prediction workflow.

## License

MIT License. See [LICENSE](LICENSE).
