# 剧本评审手册生成器 (Script Rubric)

从编辑审核数据中提炼评审手册，用于辅助剧本质量预判。

## 架构

两阶段 LLM pipeline + 确定性校准 + 回测验证：

```
飞书多维表格 (冲量/精品)
       │
       ▼  data/sync_bitable.py CLI
bitable_rubric.json
       │
       ▼
   ┌─────────┐     精品表（完整评分字段）
   │ parse    │────────────────────────────┐
   │ bitable  │                            │
   └─────────┘                             │
       │                                   │
       ▼                                   ▼
   ┌─────────┐  seed=42        ┌──────────────────┐
   │ holdout  │───────────────▶│ 训练集 / 测试集    │
   │ split    │                └──────────────────┘
   └─────────┘                    │            │
       │                          │            │
       ▼                          │            ▼
   ┌─────────┐                    │      ┌──────────┐
   │ Pass 1   │ 每部一次 LLM 调用 │      │ backtest │ 测试集逐部预测
   │ extract  │ → 结构化档案      │      │ predict  │ → 对照 4 指标
   └─────────┘                    │      └──────────┘
       │                          │            │
       ▼                          │            ▼
   ┌─────────┐  3 次 LLM 调用    │      ┌──────────┐
   │ Pass 2   │ + 确定性校准节    │      │ report   │ PASS / FAIL
   │ synth    │ → handbook vN     │      └──────────┘
   └─────────┘                    │
       │                          │
       ▼                          │
   handbook_vN.md ◀───────────────┘
   rubric_vN.json
```

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 校准信息 | Python 确定性渲染，不经 LLM | 数字精确，无幻觉风险 |
| 锚点选择 | 每 status 1 部，mean_score 离均值最近 | 仅从训练集选，防测试泄漏 |
| 阈值策略 | advisory（软建议），非 hard cut | 签/改/拒分数高度重叠，硬阈值不可靠 |
| 回测切分 | 按 status 分层，seed=42 固定 | 确保可复现 + 各 status 至少 1 部进测试 |
| JSON 解析 | 4 层降级（fence → raw → brace-slice → json-repair） | 不同 LLM 输出格式不一，需鲁棒容错 |

## 目录结构

```
script_rubric/
├── config.py                  # 所有配置（路径/模型/阈值/维度定义）
├── models.py                  # Pydantic v2 模型
├── requirements.txt           # 独立依赖（openai/pydantic/json-repair/httpx）
│
├── data/                      # 数据目录
│   ├── bitable_rubric.json    # 飞书多维表格导出数据（由 data/sync_bitable.py 生成）
│   └── sync_history.json      # 同步历史记录
│
├── pipeline/
│   ├── parse_bitable.py       # bitable JSON → ScriptRecord[]
│   ├── match_texts.py         # 匹配剧本正文文件
│   ├── llm_client.py          # AsyncOpenAI 封装 + extract_json（4 层降级）
│   ├── pass1_extract.py       # 每部剧本 → ScriptArchive（结构化档案）
│   ├── pass2_synthesize.py    # 跨剧本合成手册 + 确定性校准节
│   ├── backtest.py            # holdout split + predict + evaluate
│   └── run.py                 # CLI: full / incremental / pass2 / backtest
│
├── prompts/                   # LLM prompt 模板（中文）
│   ├── pass1.md               # 单剧本档案提取
│   ├── pass2_universal.md     # 通用规律合成
│   ├── pass2_overlay.md       # 类型专项合成
│   ├── pass2_redflags.md      # 地雷清单合成
│   └── backtest_predict.md    # 回测预测（两阶段：先 status 后 score）
│
├── outputs/
│   ├── archives/              # 结构化档案（JSON）
│   ├── handbook/              # handbook_v1-v4.md + rubric_v1-v4.json
│   └── backtest/              # report_v1-v4.md
│
└── tests/                     # 单测
    ├── test_models.py
    ├── test_llm_client.py
    ├── test_match_texts.py
    ├── test_backtest.py
    └── test_pass2_calibration.py

data/
├── sync_bitable.py            # CLI: 从飞书多维表格 URL 拉取数据
├── feishu_common.py           # 飞书 API 公共模块
└── downloads/                 # 下载缓存目录
```

## 使用

```bash
# 1. 从飞书多维表格拉取数据（需要用户提供 bitable URL）
python data/sync_bitable.py https://<TENANT>.feishu.cn/base/<APP_TOKEN>

# 2. 环境变量（.env 或 export）
OPENAI_BASE_URL=https://yibuapi.com/v1
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gemini-3.1-pro-preview

# 3. 运行 pipeline
# 完整流程：解析 → 切分 → Pass 1 → Pass 2 → 回测
python -m script_rubric.pipeline.run full --version 1

# 仅重跑 Pass 2（复用已有档案，自动过滤测试集）
python -m script_rubric.pipeline.run pass2 --version 4

# 仅重跑回测
python -m script_rubric.pipeline.run backtest --version 4

# 增量：仅提取新增剧本，合并后重合成手册
python -m script_rubric.pipeline.run incremental

# 测试
pytest script_rubric/tests/ -v
```

## 手册结构（v4）

```
# 剧本评审手册 v4
├── 第一部分：通用规律          ← LLM 从训练集归纳
├── 第二部分：类型专项          ← 按 genre 分组，≥3 部才生成
├── 第三部分：地雷清单          ← 从拒/改档案中提炼
├── 第四部分：评分校准刻度      ← Python 确定性生成
│   ├── A. 状态-分数分布表（均分/P25/P75/维度均值）
│   ├── B. 推荐阈值（advisory，含重叠区警告）
│   └── C. 锚点剧本（每 status 1 部）
└── 附录：数据概览              ← Python 确定性生成
```

## 评估指标

| 指标 | 含义 | 阈值 |
|------|------|------|
| 状态命中率 | 预测 status 与编辑一致的比例 | ≥70% |
| 区间命中率 | 预测分落在编辑评分区间内的比例 | ≥60% |
| 分数 MAE | 预测分与编辑均分的平均绝对误差 | ≤8 |
| 严重误判率 | 签↔拒 跨两级误判的比例 | ≤10% |

## 迭代历史

| 版本 | 状态命中 | 区间命中 | MAE | 严重误判 | 关键变更 |
|------|---------|---------|-----|---------|---------|
| v1 | - | - | - | - | 基线，13/36 JSON 解析失败 |
| v2 | - | - | - | - | 修复 JSON 解析（json-repair 降级链） |
| v3 | 71% ✅ | 14% ❌ | 14.7 ❌ | 0% ✅ | 全量 44 档案，首次完整回测 |
| v4 | 43% ❌ | 86% ✅ | 2.4 ✅ | 14% ❌ | 加入校准刻度表+锚点剧本 |

### v4 分析

分数校准大幅成功（MAE 14.7→2.4），但 status 准确率下降。根因：编辑的签/改/拒决定依赖隐性质性判断（市场定位、IP 重复度等），非纯文本+分数可推导。两次 prompt 调整（分数优先 vs status 优先）对 gemini-3.1-pro 行为无影响。

**下一步：** 等编辑审核新提交的 17 部剧本后，扩大训练集重跑。

## 可复用模式

以下模式适用于本项目中其他 LLM pipeline 功能：

### 1. 鲁棒 JSON 解析

```python
# pipeline/llm_client.py — 4 层降级
# 1) markdown fence 提取 → 2) 裸 JSON parse → 3) 花括号切片 → 4) json-repair
```
不同模型（Claude/Gemini/GPT）的 JSON 输出格式不一致，单一解析策略必然失败。

### 2. 确定性 vs LLM 混合架构

需要精确的数据（统计、阈值、锚点）用 Python 确定性生成；需要归纳、总结、理解的部分用 LLM。两者在最终产物中拼接。**永远不要让 LLM 重写你计算好的数字。**

### 3. 回测驱动迭代

每次变更 prompt 或手册后，用固定 seed 的 holdout 集自动回测，4 个指标全部 PASS 才算达标。避免"改了感觉更好"的主观判断。

### 4. 训练/测试隔离

所有用于合成手册的数据必须来自训练集。锚点选择、统计计算、prompt 示例——任何进入手册的信息都不能包含测试集数据。`cmd_pass2_only` 每次运行都重新切分并过滤。

### 5. 增量友好设计

Pass 1 档案按 title 独立存储为 JSON，`skip_existing=True` 跳过已提取的。新数据到达后只需提取增量，然后重跑 Pass 2。
