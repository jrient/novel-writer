# Script Rubric 评分校准设计 (Handbook v4)

> 日期：2026-04-16
> 关联文档：`2026-04-16-script-rubric-design.md`（Phase 1 主设计）
> 触发原因：手册 v3 回测显示分数 MAE = 14.7、区间命中率 = 14%，均未达标

## 背景

手册 v3 回测（7 部测试集）结果：

| 指标 | 实际 | 阈值 | 结果 |
|------|------|------|------|
| 状态命中率 | 71% | ≥70% | PASS |
| 严重误判率 | 0% | ≤10% | PASS |
| 区间命中率 | 14% | ≥60% | FAIL |
| 分数 MAE | 14.7 | ≤8 | FAIL |

诊断发现两个**独立但耦合**的问题：

1. **模型系统性低估**：7 个测试样本预测分全部低于实际，偏差 -3 到 -23.6 分。模型内部用 4-7 的压缩刻度对维度评分，反推总分偏低约 15 分。
2. **状态阈值与真实分布错位**：`backtest_predict.md` 硬编码 "80+ 签 / 70-80 改 / <70 拒"，但训练集实际分布为：
   - 签：n=7，均分 78.7（76.8-80）
   - 改：n=11，均分 77.7（71.5-82.5）
   - 拒：n=26，均分 72.9（68-79.7）

   三类大量重叠，硬阈值无法对应真实评审行为。

## 设计目标

不重跑 Pass 1（44 部档案不变），仅通过 Pass 2 阶段引入校准信息，让 v4 手册同时改善 MAE 与区间命中率，并保持状态命中率与零严重误判。

## 架构决策

### 决策 1：校准信息落在手册里，而非仅在预测 prompt

校准信息（统计 + 锚点）成为 handbook v4 的"第四部分"，预测 prompt 引用该节。理由：
- 手册是项目长效产出，校准属于刻度对齐，应与手册同生命周期。
- 预测 prompt 仅持有引用，不直接持有数字，更易维护。

### 决策 2：校准节由 Python 确定性渲染，Pass 2 LLM 不参与

- 校准信息的核心价值是精确，任何 LLM 改写都引入幻觉风险。
- Python 计算 → 渲染 markdown → 直接 append 到手册。
- 失败可重跑，无需怀疑 LLM 输出。

### 决策 3：每状态 1 部锚点剧本

- 锚点选 `mean_score` 与 status 均值最近的剧本（绝对距离最小）。
- 仅从训练集挑（已按 seed=42 切分），杜绝测试集泄漏。
- 1 部 / status 而非多部：减小 token 与泄漏面，足以锚定刻度。

### 决策 4：阈值为 advisory 而非 hard cut

- 训练集三状态分数大量重叠（签均 78.7、改均 77.7 仅差 1 分）。
- 校准节明确写"分数与状态高度重叠，刻度仅为参考"。
- 预测 prompt 要求 status 判定综合质性维度（红旗/绿旗），分数不作硬切。

## 实现范围

### 1. 新增：校准节生成器

文件：`script_rubric/pipeline/pass2_synthesize.py`

新函数 `_build_calibration_section(archives: list[ScriptArchive]) -> str`，输出三块 markdown：

**A. 状态-分数映射表**

按 status 聚合，输出：

```
| 状态 | 样本数 | 均分 | P25 | P75 | 维度典型分布 |
| 签   | 7     | 78.7 | 77.0 | 79.5 | 题材 7.4 / 人设 7.6 / ... |
| 改   | 11    | 77.7 | 74.0 | 80.5 | ...                      |
| 拒   | 26    | 72.9 | 70.5 | 75.5 | ...                      |
```

P25/P75 用 `statistics.quantiles(n=4)` 计算；维度典型分布列出 7 维 avg。

**B. 推荐阈值（advisory）**

```
- 签 / 改 边界 ≈ 78（重叠区 76-80 需结合质性判断）
- 改 / 拒 边界 ≈ 75（重叠区 73-77 需结合质性判断）
> 分数与状态高度重叠，刻度仅为参考；最终 status 取决于质性维度。
```

边界用相邻 status 均值的 midpoint，保留 1 位小数：(78.7+77.7)/2 = 78.2、(77.7+72.9)/2 = 75.3。重叠区由相邻 status 的 P25/P75 范围决定（如签的 P25 到改的 P75 即重叠区）。

**C. 锚点剧本（每 status 1 部）**

挑选规则：在该 status 内，选 `abs(mean_score - status_mean)` 最小的剧本；并列时取 title 字典序较小者（确定性）。

每部锚点输出：
- title / genre / status / mean_score
- 7 个维度分（仅 score，不含 reasoning）
- top-2 共识点（取 `consensus_points[:2]`）
- top-1 红旗（如 status≠签）或 top-1 绿旗（如 status=签）

格式示例：
```
### 锚点 · 拒 · 《被杀就满级，我乃皇家第一侍卫 1-10》
- 类型：男频爽文 / 实际均分：76.4
- 维度：题材 7 / 人设 8 / 故事 7 / 情感 6 / 表达 7 / 制作 8 / 商业 7
- 共识：节奏明快不拖沓；金手指设计合理。
- 红旗：女性角色工具化严重。
```

### 2. 手册结构变更

`synthesize_all` 中拼装顺序：

```
# 剧本评审手册 v{version}
## 第一部分：通用规律        (LLM, 不变)
## 第二部分：类型专项        (LLM, 不变)
## 第三部分：地雷清单        (LLM, 不变)
## 第四部分：评分校准刻度    (NEW, 调用 _build_calibration_section)
## 附录：数据概览            (确定性, 不变)
```

放第四部分而非附录的原因：第四部分是预测时的核心参考，置于附录会让 LLM 误判其重要性。

### 3. 预测 prompt 改写

文件：`script_rubric/prompts/backtest_predict.md`

变更点：
1. **删除**硬编码 "80+签 70-80改 <70拒"。
2. **新增**段落（位置：评分流程开头）：
   > 第一步：对照手册第四部分"评分校准刻度"。先看 3 部锚点剧本的维度分模式，找到与本剧最相似的锚点；再参考状态均分/分位数，估算本剧总分。**注意分数与状态高度重叠**，分数仅作刻度参考，status 判定要综合质性维度（红旗/绿旗）。
3. **修改**输出 schema 注释：要求 `reasoning` 显式说明"参考的锚点剧本是哪部，分数偏高/偏低的依据"。

输出 JSON schema 不变：`{"score": int, "status": str, "reasoning": str}`。

### 4. 测试

文件：`script_rubric/tests/test_pass2_calibration.py`（新建）

3 个单测，使用 fixture 构造 6-9 部 mock archive：
1. `test_calibration_section_has_all_statuses`：渲染输出包含"签"、"改"、"拒"三个状态行。
2. `test_anchor_selection_closest_to_mean`：选出的锚点 `mean_score` 与 status 均值的距离 ≤ 该 status 内任一其它剧本的距离。
3. `test_no_test_set_leakage`：给定一个 holdout title 集合，确保锚点 title 都不在其中（通过函数签名传入训练集 only）。

注：第 3 条要求 `_build_calibration_section` 的输入 archives 必须是训练集；调用方 `synthesize_all` 在拼装前已按 holdout split 过，本节函数无需自行切分（保持单一职责）。

## 实施顺序

1. 编辑 `pass2_synthesize.py`：新增 `_build_calibration_section`、修改 `synthesize_all` 拼装。
2. 编辑 `prompts/backtest_predict.md`：移除硬阈值、新增锚点引用说明。
3. 新建 `tests/test_pass2_calibration.py`：3 个单测。
4. 运行 `pytest script_rubric/tests/` 确保单测通过。
5. 运行 `python -m script_rubric.pipeline.run pass2 --version 4`（复用 44 archives，仅重跑 Pass 2 LLM 三次调用）。
6. 运行 `python -m script_rubric.pipeline.run backtest --version 4`。
7. 查看 `outputs/backtest/report_v4.md`，对照接受标准。

## 接受标准

| 指标 | v3 | v4 目标 | 性质 |
|------|------|---------|------|
| 状态命中率 | 71% | ≥70% | 不能跌破 |
| 区间命中率 | 14% | ≥60% | 关键改善项 |
| 分数 MAE | 14.7 | ≤8 | 关键改善项 |
| 严重误判率 | 0% | ≤10% | 不能引入新风险 |

## 回滚与失败诊断

v4 是独立产物（`handbook_v4.md` / `rubric_v4.json` / `report_v4.md`），失败不影响 v3。

诊断分支：
- **MAE 仍高**：锚点策略问题。考虑改为每 status 取 P25/P50/P75 三锚点，或追加每个 status 的"分数推导示例"段落。
- **status 跌破 70%**：advisory 措辞不够强，模型过度依赖刻度表。考虑在阈值表前加更显著的"DO NOT 仅凭分数判定 status"提示。
- **区间命中率仍低**：模型输出区间过窄。考虑在 prompt 中加硬约束："区间宽度必须 ≥ 8 分"。

## 范围外（不在本次实施）

- 不改 Pass 1 抽取逻辑，不重跑 44 部档案。
- 不引入后验线性校准（未来若手册策略仍不稳，可考虑作为补救层）。
- 不做按类型（genre）的细粒度校准（样本量太小，3-5 部 / genre 不足以稳定统计）。
- 不改 backtest 切分逻辑或评估指标。
