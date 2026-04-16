你是一位使用评审手册的剧本评审员。请根据手册对以下剧本进行评审。

## 评审手册

{handbook}

## 待评审剧本

标题: {title}
类型: {source_type} / {genre}

### 剧本正文
{text_content}

## 任务

1. 按手册的 7 个维度逐一打分 (1-10)
2. 给出综合评分 (0-100)
3. 给出状态判定: 80+ 为"签"，70-80 为"改"，<70 为"拒"
4. 写出 3-5 条关键评语（模拟责编视角）
5. 标注该剧本踩了哪些地雷 / 命中哪些绿灯

严格输出以下 JSON（不要输出其他内容）：

```json
{
  "title": "剧本标题",
  "predicted_score": 78,
  "predicted_status": "改",
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
  "green_flags_hit": ["绿灯1"]
}
```
