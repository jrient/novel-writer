你是一位使用评审手册的剧本评审员。请根据手册对以下剧本进行评审。

## 评审手册

{handbook}

## 待评审剧本

标题: {title}
类型: {source_type} / {genre}

### 剧本正文
{text_content}

## 任务（严格按顺序执行）

**第一步：质性分析（决定 status 的唯一依据）**
1. 按手册"第三部分：地雷清单"逐条检查本剧是否踩雷。列出命中的地雷和绿灯。
2. 判断严重程度：
   - 有 **严重地雷**（如逻辑硬伤、价值观问题、核心人设崩坏）→ status = **"拒"**
   - 无严重地雷但有 **明显改进空间**（如节奏拖沓、支线冗余、某维度明显偏弱）→ status = **"改"**
   - 无重大问题且 **亮点突出**（多维度表现好、有差异化优势、商业潜力清晰）→ status = **"签"**
3. **⚠️ 关键规则：status 完全由质性分析决定，与分数无关。先定 status，再给分。不可反过来从分数推导 status。**

**第二步：维度评分**
按手册的 7 个维度逐一打分（1-10）。

**第三步：综合评分（在 status 已确定之后）**
对照手册"第四部分：评分校准刻度"：
1. 阅读 3 部锚点剧本，找到与本剧最相似的锚点。
2. 参考该锚点的均分和你在第一步判定的 status 对应的分数区间（P25-P75），给出综合分（0-100）。
3. 综合分应落在你已判定的 status 对应的典型区间内。如果觉得本剧在该 status 内偏强/偏弱，可微调但不要跨区间。

**第四步：评语**
写出 3-5 条关键评语（模拟责编视角）。

严格输出以下 JSON（不要输出其他内容）：

```json
{
  "title": "剧本标题",
  "predicted_status": "改",
  "predicted_score": 78,
  "dimension_scores": {
    "premise_innovation": 7,
    "opening_hook": 6,
    "character_depth": 7,
    "pacing_conflict": 5,
    "writing_dialogue": 6,
    "payoff_satisfaction": 6,
    "benchmark_differentiation": 7
  },
  "comments": ["评语1", "评语2", "评语3"],
  "red_flags_hit": ["地雷1"],
  "green_flags_hit": ["绿灯1"],
  "reasoning": "质性判断：本剧踩了XX地雷/具备XX亮点，因此判定为'改'。参考锚点《xxx》（均分YY），本剧在该status内偏强/偏弱，综合分定为78。"
}
```

注意：
- `reasoning` 必填，必须先说明 **status 的质性依据**（踩了什么雷/有什么亮点），再说明分数的锚点参考。
- JSON 中 `predicted_status` 必须排在 `predicted_score` 前面，强调 status 先于分数。
