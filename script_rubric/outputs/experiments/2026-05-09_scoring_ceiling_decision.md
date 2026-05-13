# 评分体系上限调研 — 决策日志

**日期**：2026-05-09
**触发**：用户提供 wiki 链接 `IEorwlbIwiafLzk5WK2cDK0on4b`（指向 bitable `IXbHb8BiuaCjutsu2eJcDBL6nCf`，名「外部待审核剧本0508」），要求把它当 holdout 验证 v4/v14 状态判别准确度。中途用户调整目标为"分数为主、签改拒为辅"。

---

## 一、本次调研做了什么

围绕 handbook v14 在评分任务上的真实表现，跑了三轮独立实验：

### 1. 0508 holdout 单独打分（n=21）
- 文件：`holdout_0508_v14_score_20260509_1059.{md,json}`
- status_accuracy 表面 85%，**但全部预测落入「改」**（majority class collapse）
- 签 (n=3) 均分 72.3 < 改 (n=17) 均分 73.8 —— **判别方向反了**

### 2. 合并 holdout（训练池 18 + 0508 21 = 39，n_truth=22）
- 文件：`merged_score_v14_20260509_1503.{md,json}`
- Spearman ρ = 0.238，MAE = 3.97（in-sample 0.228 vs holdout 0.236，几乎一致）
- 系统性低估：所有 actual=80 的样本预测全在 72-78
- 同一剧本三个副本预测分跨度 9 分（72.7→70/79/73）→ DeepSeek temp=0 仍非确定性

### 3. n_samples=3 + 线性校准（in-sample + LOO）
- 文件：`calibrated_v14_20260509_1547.{md,json}`，校准系数：`outputs/handbook/calibration_v14.json`
- 三种方案对比：
  | 方案 | n | ρ | MAE | in_range |
  |---|---|---|---|---|
  | raw (n_samples=3) | 22 | -0.123 | 3.59 | 50% |
  | + 线性校准 in-sample | 22 | 0.000 | 2.48 | 32% |
  | + 线性校准 LOO | 22 | - | 2.69 | 32% |
- 拟合公式 `actual = 0.127 × pred + 67.65` —— **斜率近 0，校准把所有预测压成 77（actuals 均值）**
- 多次平均把 ρ 从 0.24 抹到 -0.12 → 原本 0.24 是噪声而非信号

### 4. No-handbook baseline（同一批 22 真分样本）
- 文件：`no_handbook_baseline_20260509_1603.{md,json}`
- 结果：ρ = -0.305，MAE = 4.48，in_range 23%，status_acc 69%
- **不喂 handbook 反而 ρ 更负，MAE 更大** → handbook 不是噪声源
- 但同样无法区分 actual=72.7 vs actual=80（前者预测最高 84，后者最低预测 70）

---

## 二、调研结论

> **handbook v14 在评分任务上的表现，与一个"恒定输出 77 ± 3"的常数预测器统计上不可区分。继续在校准/手册/prompt 上调参不会有显著收益。**

证据链：
1. 训练标签全部聚集在 70-80 窄带（人评分本身没区分度）
2. LLM temp=0 在该任务上有 ±5 物理抖动
3. 喂/不喂 handbook 都得到接近 0 或负的 Spearman
4. 校准能把 MAE 推到"预测均值"baseline，但拿不到额外信号

### 校准产物（已落盘但**不建议启用**）

`outputs/handbook/calibration_v14.json`：

```json
{
  "linear": {"a": 0.127, "b": 67.65},
  "raw_metrics": {"mae": 3.59, "spearman": -0.123},
  "calibrated_metrics": {"mae": 2.48, "spearman": 0.0}
}
```

启用后所有线上预测都会被压向 77，**实质等同于把分数关闭**。建议保留文件作记录，但 `rubric_score_service.py` 不读取该文件。

### 同时修复的 bug

`predict_one`（`script_rubric/pipeline/backtest.py`）现在：
- 正文长度 < 100 字符直接返回 None + warn（消除 v14 backtest 报告中 pred=0 / pred=10 的"空文档预测"假数据）
- 支持 `n_samples` 参数：>1 时多次预测取分数均值，状态按阈值重算
- `predicted_score` 是 float 时自动 round（修了之前每批丢 1 条样本的问题）

---

## 三、放弃方向（明确不再追的路径）

- ❌ 改 backtest_predict.md prompt 措辞（无 handbook baseline 表明 prompt 不是瓶颈）
- ❌ 加更多 handbook 锚点 / 加大 dimension 颗粒度（信号上限被数据决定）
- ❌ 换更大模型（temp=0 抖动不是模型容量问题，是任务本身缺信号）

## 四、推荐转向（按 ROI 排序）

| 方向 | 简述 | 优先级 |
|---|---|---|
| **H. 红/绿旗优先** | 不输出综合分，输出"踩了哪些 red flags / green flags"，让人去判 | ⭐⭐⭐ 最高 |
| **F. 维度评级** | 综合分换成 5 个维度的 ABC 评级（人物/情节/对白/节奏/题材） | ⭐⭐ |
| **G. 配对比较** | "A 和 B 哪个更可签"，用 ELO 或 Bradley-Terry 聚合 | ⭐⭐（重写） |
| **I. 状态平衡数据** | 重新筹"拒"样本，让签/改/拒 1:1:1 后再训手册 | ⭐（数据成本高） |
| **J. 接受现状辅助化** | 分数仍输出但标 advisory，不当 ground truth | ⭐ |

---

## 五、变更记录

- `script_rubric/pipeline/backtest.py::predict_one` —— 加 MIN_CONTENT_CHARS skip / n_samples 参数 / float→int 容错
- `script_rubric/experiments/holdout_0508.py` —— 0508 单独评分实验
- `script_rubric/experiments/merged_score_holdout.py` —— 合并 holdout + Spearman
- `script_rubric/experiments/calibrated_holdout.py` —— n_samples=3 + 线性校准（含 LOO）
- `script_rubric/experiments/no_handbook_baseline.py` —— 不喂 handbook 的对照实验
- `script_rubric/outputs/handbook/calibration_v14.json` —— 校准系数（**记录用，不启用**）

