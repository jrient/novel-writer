# 剧本评审手册自动提炼系统 — Phase 1 设计文档

> **项目**: novel-writer AI辅助小说创作平台
> **Phase**: 1 / 3 (规律提炼)
> **日期**: 2026-04-16
> **模型**: Claude Sonnet 4.6 via OpenAI-compatible

## 1. 目标

从 55 部已评审剧本（含多位责编评分+评语+剧本正文）中，提炼出一本结构化的**剧本评审手册**。手册包含通用写作规律、类型专项要求、地雷清单三部分。

手册有两种形态：
- `handbook.md` — 人类可读，写给编剧和责编
- `rubric.json` — 机器可读，Phase 2 评分系统直接使用

### 整体路线（3 Phase）

| Phase | 目标 | 依赖 |
|-------|------|------|
| **Phase 1（本文档）** | 规律提炼 → 手册 | 无 |
| Phase 2 | 责编辅助评分模块 | Phase 1 手册 |
| Phase 3 | 创作端实时反馈 | Phase 1 + 2 |

## 2. 数据源

### 2.1 来源

| 数据 | 位置 | 格式 |
|------|------|------|
| 评审表 | `uploads/外部待审核剧本.xlsx` | xlsx，55 条有效行 |
| 剧本正文 | `uploads/drama/*.txt` | 44 个 txt（飞书导出） |

### 2.2 xlsx 列映射

| 列 | 含义 |
|---|---|
| A | 原创/改编 |
| B | 类型（男频/女频/萌宝/世情） |
| C | 剧本名 |
| D | 提交人 |
| E | 状态（签/改/拒） |
| F | 综合评分（可能为空） |
| G-H | 小冉：分数 + 评语 |
| I-J | 贾酒：分数 + 评语 |
| K-L | 47：分数 + 评语 |
| M-N | 宇间：分数 + 评语 |
| O-P | 帕克：分数 + 评语 |
| Q-R | Vicki：分数 + 评语 |
| S-T | 千北：分数 + 评语 |
| U-V | 小刚：分数 + 评语 |
| W-X | 山南：分数 + 评语 |
| Y-Z | 安兔兔：分数 + 评语 |
| AA-AB | 步步：分数 + 评语 |

有效行判断：状态列（E）非空 且 至少有一位责编打分。

### 2.3 匹配逻辑

xlsx 第 C 列（剧本名）模糊匹配 `uploads/drama/` 目录文件名（`difflib.SequenceMatcher`，阈值 > 0.5）。匹配不到的标记为 `text_missing`，仍参与 Pass 1。

### 2.4 数据模型

```python
class Review(BaseModel):
    reviewer: str
    score: int | None
    comment: str | None

class ScriptRecord(BaseModel):
    title: str
    source_type: str       # 原创 | 改编
    genre: str             # 男频 | 女频 | 萌宝 | 世情
    submitter: str
    status: str            # 签 | 改 | 拒
    reviews: list[Review]
    text_content: str | None = None
    mean_score: float | None = None
    score_range: tuple[int, int] | None = None
    score_std: float | None = None
```

### 2.5 分数聚合

- `mean_score`：所有责编分数均值
- `score_range`：(min, max) 区间
- `score_std`：标准差，大 std 标记为"争议作品"

## 3. 手册维度结构

### 3.1 通用维度（7 个）

1. **题材与设定创新度** — 设定组合新颖度、禁忌规避、市场饱和度
2. **开局与钩子（前 3 集）** — 事件/情绪阈值、冲突触发速度
3. **人设立体度** — 角色底线、时代契合度、避免恋爱脑/工具人
4. **节奏与冲突密度** — 每 N 集的事件级别、松紧交替
5. **文笔与台词** — 成熟度、出戏感、对白自然度
6. **爽点兑现** — 打击位置、兑现程度、频率
7. **对标与差异化** — 过载赛道识别、空白机会

### 3.2 类型 Overlay

- **男频**：世界观搭建速度、系统/金手指合理性、爽点节奏
- **女频**：男主出场时机、拉扯涩度、宿命感
- **萌宝**：奶团可爱度、助攻能力、双线互动
- **世情 / 年代 / 悬疑**：各自独立 overlay

### 3.3 反向章节

从状态=拒的剧本中挖掘：高频拒稿原因、致命组合、可救 vs 不可救、地雷清单。

### 3.4 类型切分策略

采用 **"全局手册 + 类型差异章节"** 策略（方案 D）：
- 先用所有样本挖通用规律
- 再针对每个类型写差异化 overlay
- 理由：55 部样本切细后每桶 <15 条，规律不稳定

## 4. 管线架构

### 4.1 两趟管线（方案 C + 新数据迭代）

```
xlsx + 剧本正文
    ↓ Pass 1: per-script 结构化提炼 (Sonnet 4.6, 55 次调用)
    ↓ 55 份 ScriptArchive JSON
    ↓ Pass 2: 跨剧本综合 (3 批次, 6 次调用)
    ↓ handbook.md + rubric.json
    ↓ 回测 (11 部 holdout)
    ↓ 新数据进来 → 增量 Pass 1 → 预测验证 → 重跑 Pass 2 → 手册 v(N+1)
```

### 4.2 Pass 1 — Per-Script 结构化提炼

**输入**：每部剧本的 ScriptRecord（元数据 + 所有评语 + 正文）

**输出**：ScriptArchive JSON

```python
class DimensionAnalysis(BaseModel):
    score: int                          # 1-10
    verdict: Literal["positive", "mixed", "negative"]
    evidence_from_reviews: list[str]
    evidence_from_text: list[str]
    extracted_rule: str

class ScriptArchive(BaseModel):
    title: str
    status: str
    genre: str
    mean_score: float
    score_range: tuple[int, int]
    dimensions: dict[str, DimensionAnalysis]  # 7 个维度
    type_specific_notes: str
    consensus_points: list[str]
    disagreement_points: list[str]
    red_flags: list[str]
    green_flags: list[str]
```

**Prompt 核心原则**：
1. 证据驱动：每个维度判定必须引用责编原话或正文原文
2. 保留分歧：责编间意见冲突记录在 disagreement_points
3. 共识提炼：≥50% 责编提到同一问题 → consensus_point
4. 维度打分：基于评语倾向，不是 LLM 自己的判断
5. 正文缺失时：仅基于评语，可信度标记 "low"

**执行策略**：
- 并发：`asyncio.Semaphore(5)`
- 重试：失败重试 2 次
- 断点续跑：已存在的 archive JSON 跳过
- Token 预算：单次输入 ~27K token

### 4.3 Pass 2 — 跨剧本综合

分 3 批次，各自聚焦一个目标：

| 批次 | 输入 | 产出 |
|------|------|------|
| Batch A：通用规律 | 全部档案的摘要视图（每份 ~200 字） | 7 个通用维度规律章节 |
| Batch B：类型 Overlay | 按 genre 分组，每组档案全量 | 每类型差异化章节 |
| Batch C：反向地雷 | 仅状态=拒 的档案全量 | 拒稿共性 + 地雷清单 |

**通用规律章节结构**（每维度）：
1. 核心规律（3-5 条）
2. 正例（签的剧本案例 2-3 个）
3. 反例（拒的剧本案例 2-3 个）
4. 量化锚点（如有数据支撑）
5. 可执行建议（do / don't）

**类型 Overlay 章节结构**（每类型）：
1. 特别看重什么（3-5 条）
2. 常见翻车点（3-5 条）
3. 与其他类型的关键差异
4. 评分维度加权/降权建议

**反向地雷章节结构**：
1. 高频拒稿原因 TOP 10
2. 致命组合
3. 可救 vs 不可救
4. 一句话地雷清单（10-15 条）

## 5. 输出物

### 5.1 handbook.md（人类可读）

```
# 剧本评审手册 v{version}
> 基于 {N} 部剧本 × {M} 位责编评审数据

## 第一部分：通用规律
### 1-7. 各维度章节

## 第二部分：类型专项
### 男频 / 女频 / 萌宝 / 世情

## 第三部分：地雷清单

## 附录：数据概览
```

### 5.2 rubric.json（机器可读）

```json
{
  "version": "1.0",
  "generated_at": "2026-04-16",
  "sample_size": 55,
  "universal_dimensions": {
    "premise_innovation": {
      "weight": 0.2,
      "rules": [...],
      "red_flags": [...],
      "green_flags": [...]
    }
  },
  "type_overlays": {
    "男频": { "weight_adjustments": {...} }
  },
  "rejection_patterns": [
    { "pattern": "开局平 + 人设恋爱脑", "rejection_rate": 0.9 }
  ]
}
```

## 6. 回测验证

### 6.1 流程

55 部 → 分层抽样 11 部 holdout（签3 改4 拒4）→ 44 部训练 → 手册 v1 → 预测 11 部 → 对比

### 6.2 验收指标

| 指标 | 计算方式 | 阈值 |
|------|---------|------|
| 状态命中率 | 预测状态 == 实际状态 | ≥ 70% (≥ 8/11) |
| 区间命中率 | 预测分数 ∈ [min, max] reviewer 区间 | ≥ 60% (≥ 7/11) |
| 分数 MAE | \|预测分 - 均分\| 平均 | ≤ 8 |
| 严重误判率 | 签↔拒 互判 | ≤ 10% |

### 6.3 未达标迭代

分析失败案例 → 调整 prompt → 重跑 Pass 1/2 → 重新回测。最多 3 轮。

## 7. 增量迭代机制

新数据进来时：

1. 解析新 xlsx + 匹配新正文
2. 仅对新剧本跑 Pass 1（旧档案复用）
3. 用当前手册预测新剧本 → 对比真实结果 → 验证手册质量
4. 合并新旧档案 → 重跑 Pass 2 → 手册 v(N+1)
5. 输出增量验证报告

每批新数据先当测试集，再变训练集。手册版本递增追踪。

## 8. 技术实现

### 8.1 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| LLM 调用 | `openai` SDK (兼容模式) |
| xlsx 解析 | `openpyxl` |
| 模糊匹配 | `difflib.SequenceMatcher` |
| 数据模型 | `pydantic` v2 |
| 并发 | `asyncio` + `Semaphore(5)` |
| CLI | `argparse` |

### 8.2 目录结构

```
/script_rubric/
├── data/
│   ├── raw/              # xlsx 原始文件 (symlink)
│   └── parsed/           # 解析后的 JSON
├── pipeline/
│   ├── parse_xlsx.py     # xlsx → ScriptRecord[]
│   ├── match_texts.py    # 匹配剧本正文
│   ├── pass1_extract.py  # Per-script 结构化提炼
│   ├── pass2_synthesize.py  # 跨剧本综合
│   ├── backtest.py       # 回测验证
│   └── run.py            # CLI 入口
├── prompts/
│   ├── pass1.md          # Pass 1 prompt 模板
│   └── pass2.md          # Pass 2 prompt 模板
├── outputs/
│   ├── archives/         # per-script JSON 档案
│   ├── handbook/         # 手册 (markdown + JSON)
│   └── backtest/         # 回测结果
├── config.py             # 配置
└── requirements.txt      # openai, openpyxl, pydantic
```

### 8.3 CLI 入口

```bash
python script_rubric/pipeline/run.py --full          # 首次完整运行
python script_rubric/pipeline/run.py --incremental   # 增量运行
python script_rubric/pipeline/run.py --backtest-only  # 仅回测
python script_rubric/pipeline/run.py --pass2-only     # 仅重跑 Pass 2
```

### 8.4 配置

```python
# API
API_BASE_URL = ""        # 从 .env 读取
API_KEY = ""             # 从 .env 读取
MODEL = "claude-sonnet-4-6"

# 管线参数
PASS1_CONCURRENCY = 5
PASS1_MAX_RETRIES = 2
HOLDOUT_RATIO = 0.2
HOLDOUT_SEED = 42
MAX_ITERATE_ROUNDS = 3

# 验收阈值
BACKTEST_STATUS_ACCURACY = 0.70
BACKTEST_RANGE_ACCURACY = 0.60
BACKTEST_MAE_THRESHOLD = 8
BACKTEST_CRITICAL_MISS_RATE = 0.10
```

## 9. 成本估算

| 步骤 | 调用次数 | 输入 token | 输出 token | 费用 |
|------|---------|-----------|-----------|------|
| Pass 1 (55部) | 55 | ~25K/次 | ~2K/次 | ¥20-35 |
| Pass 2 (3批) | 6 | ~10K/次 | ~4K/次 | ¥5-10 |
| 回测 (11部) | 11 | ~20K/次 | ~1K/次 | ¥5-10 |
| **首次总计** | **72** | | | **¥30-55** |
| **增量每批** | N+6 | | | **¥10-20** |

## 10. 时序

### 首次 Full Run (~15 分钟)

1. `parse_xlsx` → 55 条 ScriptRecord (~1s)
2. `match_texts` → 匹配报告 (~1s)
3. `split_holdout` → 44 训练 + 11 测试 (~0s)
4. `pass1_extract(44)` → 44 份 ScriptArchive (~5min)
5. `pass2_synthesize` → handbook_v1.md + rubric_v1.json (~2min)
6. `backtest(11)` → report_v1.md (~2min)
7. 检查指标 → 达标则完成，否则迭代（最多 3 轮）

### 增量 Run (~5 分钟)

1. 解析新数据 → N 条新记录
2. 匹配新正文
3. `pass1_extract(仅新)` → N 份新 ScriptArchive
4. 预测验证 → 验证报告
5. 合并 → `pass2_synthesize` → handbook_v(N+1)
