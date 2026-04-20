# Score-Tier Training Expansion Design

## Problem

script_rubric pipeline v4 只用 44 部有确认状态(签/改/拒)的剧本训练。xlsx 中还有 23 部有 >=3 人评分但无确认状态的剧本被浪费。v4 回测 status 命中率仅 43%，核心瓶颈是训练数据不足。

## Solution

新增"仅评分"数据通道，将 23 部有评分无状态的剧本纳入 Pass 1 提取和 Pass 2 合成。回测仍只用有确认状态的数据，保持评估可靠性。

## Score Tier Rules

依据 xlsx 表头 `80+可签，70-80可改`：
- mean_score >= 80 → inferred status "签"
- 70 <= mean_score < 80 → inferred status "改"
- mean_score < 70 → inferred status "拒"

## Changes

### 1. config.py
- Add `MIN_SCORES_FOR_INCLUSION = 3`
- Add `SCORE_TIER_THRESHOLDS = {"签": 80, "改": 70}` (>= 80 签, >= 70 改, < 70 拒)

### 2. models.py
- Add `status_source: str = "confirmed"` to ScriptRecord (values: "confirmed" | "score_inferred")

### 3. parse_xlsx.py
- Add `include_scored: bool = False` parameter to `parse_xlsx()`
- When `include_scored=True`, also include rows with:
  - No status (or status not in 签/改/拒)
  - At least `MIN_SCORES_FOR_INCLUSION` reviewer scores
  - Non-empty title
- For these rows, compute mean score and map to status via SCORE_TIER_THRESHOLDS
- Set `status_source="score_inferred"`

### 4. pass1_extract.py
- In `_build_user_prompt()`: when `status_source == "score_inferred"`, show "状态: 未确认（评分推断：X）" instead of "状态: X"
- In `_validate_archive()`: skip status mismatch check for score_inferred records

### 5. pass2_synthesize.py
- `synthesize_universal()`: no change (already takes all archives)
- `synthesize_redflags()`: include low-score inferred archives alongside rejected
- `_build_calibration_section()`: only use confirmed-status archives (filter by checking archive titles against confirmed set)
- `_build_data_overview()`: show confirmed vs inferred counts
- `synthesize_all()`: accept optional `confirmed_titles: set[str]` for calibration filtering

### 6. run.py
- `cmd_full()`: parse with `include_scored=True`, split holdout only from confirmed records, merge score-inferred records into training set
- Version auto-increment to v5

## Data Flow

```
xlsx 154 rows
  ├─ confirmed status (44) → holdout split → train (~36) + test (~8)
  └─ scored, no status (23) → all join training
                                ↓
                train ~36 + scored 23 = ~59
                                ↓
                       Pass 1 (incremental)
                                ↓
                       Pass 2 → handbook v5
                                ↓
                       Backtest on ~8 confirmed holdout
```

## What Does NOT Change

- Backtest holdout split logic (only confirmed status)
- Backtest evaluation metrics (same 4 metrics)
- Pass 1 prompt structure (same 7 dimensions)
- Pass 2 prompt templates (same universal/overlay/redflags)
- Existing 44 archives (skip_existing=True)

## Success Criteria

Compare v5 vs v4 backtest on same holdout set. Target: improve at least one metric without regressing others.
