# 解说漫样本池重建与 genre 感知抽样设计

> 日期: 2026-04-22
> 状态: 待实施（Path A）
> 触发事件: 编剧老师评价 剧本 8 (解说漫《老板的反击》) 第一集"干巴，没有向下看的欲望"

## 背景

剧本 8 第 1 集已生成为"分场剧本"格式，质量被外部编剧老师判为"干巴"。定位根因后发现**样本池分类错了**——`style_samples_dynamic.json` 把 AI 仿真人剧改编（《谋妃千岁》《八零福星》《嫡女贵凰》等都市/重生题材）当成动态漫范本，导致解说漫项目（如剧本 8 职场都市题材）抽到玄幻范本（《皇子》"天降金色字体"），学会了给都市主角硬塞"烫金劳动法"这种玄幻开挂模板。

同时，本次新从飞书「内部已签约待制作」表拉取了 20 份已签约剧本（去重后新增 17 份，共 73 万字正文），可用总样本从 67 条扩到 84 条，其中新增 8 部 60 集完本——长度和题材多样性都显著增强。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 修复范围 | 解说漫池 + 动态漫池都重建 | 一次做完分池，两类剧种都受益；解说漫修复后再不污染动态漫池 |
| 分池依据 | **题材质感**（不是 source_type 或文本格式） | AI 仿真人剧文本也是分场剧本格式，区别在于都市/家庭 vs 玄幻/修真；老师原话确认 |
| 抽样来源 | scripts.json（67）+ internal_signed_meta.json（20） | 外部已评 + 内部已签，各取所长 |
| 新增 17 份样本 | 不打分，按"已签约"隐含质量直接并入 | Q2a：最快验证样本分池假设；若后续效果不足再跑 rubric |
| 剧本 8 处理 | 保留原 25 集大纲，只重新生成第 1 集 episode_content | Q1b：不作废用户已有工作；先验证样本修复是否足够 |
| genre 检索 | `StyleGuard.get_style_samples(script_type, genre)` | 同题材优先，减少跨题材风格污染 |
| 不做 | 大纲重写、handbook 注入 outline、给新样本打分 | 留给后续 Path B/C，避免本轮范围膨胀 |

## 根因复盘（与方案对齐）

1. **样本池错配**：AI 仿真人剧原本被 `extract_fewshots.py::extract_from_scripts_json` 按 "status=签 且 writing_dialogue≥7" 扫入 `style_samples_dynamic.json`。对解说漫项目来说永远抽不到同题材范本，只能从《皇子》《天降魔丸》这类玄幻样本借结构。
2. **genre 未被利用**：`StyleGuard` 只按 `script_type` 分池，项目 `genre`（都市/女频/玄幻等）没进入抽样链路。
3. **验证通路不存在**：目前没有"针对某一个已生成剧本，换新样本重生成第 1 集"的捷径——开发调试需要手动清单式操作。

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│  数据源                                              │
│  scripts.json (67, 已评分)                           │
│  internal_signed_meta.json (20, 本次新拉)            │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  extract_fewshots.py（改造）                         │
│  • 合并两个数据源                                    │
│  • 按题材质感分池：                                  │
│     explanatory_pool ← 都市/家庭/重生/AI仿真人       │
│     dynamic_pool     ← 玄幻/修真/历史/萌宝玄幻       │
│  • 为每条样本打标签：genre / theme_tag               │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  style_samples_dynamic.json (重建)                   │
│  style_samples_explanatory.json (重建)               │
│   — 每条样本增加 genre / theme_tag 字段              │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  StyleGuard (扩展 API)                               │
│  get_style_samples(script_type, genre=None)          │
│   → 优先同 genre，回退同 script_type                 │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  script_ai_service.generate_episode_content          │
│  读取 project.genre，传入 StyleGuard                 │
└─────────────────────────────────────────────────────┘
```

## 详细设计

### 1. 数据源合并与统一 schema

目标：两个 JSON 合并后，样本条目都有足够信息支持按 genre/theme 检索。

**scripts.json 现有字段**：`title, source_type, genre, status, mean_score, text_content`
**internal_signed_meta.json 现有字段**：`title, source_type, genre, status, production_status, text_content`

**统一后内部使用的样本记录结构**：
```python
{
    "title": str,
    "source_type": "改编" | "原创",
    "genre": "男频" | "女频" | "萌宝" | "世情" | "",
    "theme_tag": "urban" | "xianxia" | "historical" | "family" | ...,  # 新增，人工+规则分类
    "script_type": "dynamic" | "explanatory",  # 新增，按 theme_tag 决定
    "status": "签",
    "mean_score": float | None,
    "excerpt": str,  # 清洗后的分场正文
    "source": "external_reviewed" | "internal_signed",
}
```

**theme_tag 分类规则（人工 + 关键字）**：
- `urban`（都市/职场/家庭）→ explanatory
- `rebirth_modern`（现代重生/复仇）→ explanatory
- `ai_realperson`（AI 仿真人剧改编）→ explanatory
- `xianxia`（修真/玄幻/仙侠）→ dynamic
- `historical`（历史/朝堂/穿越古代）→ dynamic
- `cute_baby`（萌宝）→ 按具体内容二选一（《天降魔丸》玄幻 → dynamic；其他可能 → explanatory）

### 2. extract_fewshots.py 改造

**新增**：`classify_script(record) -> (script_type, theme_tag)`
- 基于标题关键字（"AI真人/仿真人/重生/都市/职场" → explanatory）
- 基于 genre 和内容抽样（正则扫 text_content 开头 500 字，看有无"修真/神通/法宝/OS" 等 token）
- 对无法自动判定的条目，用人工清单兜底（白名单放到 `script_rubric/config/theme_classification.yaml`）

**输出改变**：
- `style_samples_dynamic.json` 的 `samples` 数组每条含 `genre`/`theme_tag`
- 同理 `style_samples_explanatory.json`
- 解说漫池目标 10-15 条样本（从 17+ 条候选里挑高质量的），动态漫池目标 10-15 条

### 3. StyleGuard API 变更

**修改**：`backend/app/services/style_guard.py`

```python
def get_style_samples(
    self,
    script_type: str,
    count: int = 1,
    genre: Optional[str] = None,
) -> list[dict]:
    """
    优先返回同 genre 样本；若同 genre 不足 count 条，用同 script_type 其他 genre 补足。
    返回格式：[{title, excerpt, genre, theme_tag}, ...]
    """
```

**`build_style_context` 签名同步加 `genre` 参数**，向下透传。

### 4. script_ai_service 集成

**修改**：`backend/app/services/script_ai_service.py`

- `ScriptAIService.__init__` 从 `project_settings` 或外层入参接收 `genre`
- `generate_episode_content` 调用 `_build_episode_user_prompt(..., genre=self.genre)`
- `_build_episode_user_prompt` 把 genre 透传给 `StyleGuard.build_style_context`

**drama.py router** 端：`session_expand_episode` 从 `project.genre`（或 `project.metadata_.settings.genre`）读 genre，构造 AIService 时传入。

### 5. 剧本 8 验证通路

**手动脚本** `scripts/regen_episode.py`（新增，一次性工具）：
1. 入参：`project_id`、`episode_index`、（可选）`dry_run`
2. 直接复用 `session_expand_episode` 的 async 流程，在 CLI 环境打印或落盘输出
3. 不覆盖数据库内容，`dry_run=True` 时只打印新生成文本

初次验证：`regen_episode.py --project-id 8 --episode-index 0 --dry-run`，输出与当前 intro 内容对比，由用户/老师判断是否改善。

## 文件变更清单

### 新增
- `script_rubric/data/parsed/internal_signed_meta.json` — ✅ 已完成（本轮会话拉取）
- `script_rubric/config/theme_classification.yaml` — 人工兜底白名单
- `scripts/regen_episode.py` — 验证工具（一次性 CLI）

### 修改
- `script_rubric/pipeline/extract_fewshots.py` — 合并两个源 + 分题材池 + 加 genre/theme_tag
- `script_rubric/outputs/style_samples_dynamic.json` — 重建（移除 AI 仿真人剧）
- `script_rubric/outputs/style_samples_explanatory.json` — 重建（从 1 条扩到 10-15 条）
- `backend/app/services/style_guard.py` — 加 genre 参数
- `backend/app/services/script_ai_service.py` — 透传 genre 到 StyleGuard
- `backend/app/routers/drama.py` — 从 project 读 genre 传入

### 不变
- `script_rubric/data/parsed/scripts.json` — 保留原样，不动
- `HandbookProvider` / handbook 注入链路 — 不动（留给 Path B）
- 前端 — 无 UI 变化
- 大纲生成（`outline` prompt）— 不动（留给 Path B）

## 验证计划

1. 跑 `extract_fewshots.py` → 检查两个 JSON 的 samples 数量和 genre 分布
2. 单元测试：`StyleGuard.get_style_samples("explanatory", genre="女频")` 返回的样本确实来自解说漫池且 genre 匹配
3. 跑 `regen_episode.py --project-id 8 --episode-index 0 --dry-run`，人工对比：
   - 原开头 "李总砸桌 → 于旁亮劳动法" 
   - 新开头是否具备：悬念/反差/生活化对白/脆弱感（至少出现两项）
4. 用老师最初的质评话术再问一遍（是否"还想继续看"）

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 新样本未打分，可能混入质量不均的 | 选长度 > 40K 且 production_status=完本 的优先；若后续验证效果不足，再补 rubric 打分 |
| 自动 theme_tag 分类错（如"霸道总裁"边界模糊） | 用人工 `theme_classification.yaml` 白名单兜底 |
| genre 字段在老项目中可能为空 | StyleGuard 实现同 genre 不足时自动回退同 script_type 全池 |
| 修改 StyleGuard 签名打破现有调用 | 新增的 `genre` 参数设默认值 `None`，向后兼容 |
| 剧本 8 重生成后仍"干巴" | 说明问题在大纲层；回退计划是触发 Path B（handbook 注入 outline）|

## 后续路径（不在本轮）

- **Path B**：把 handbook 的 7 维度/地雷清单注入 `outline` 和 `episode_content`
- **Path C**：大纲重写工具（让 outline 同样经 genre + handbook 生成）
- 给 internal_signed 的 17 份样本补跑 rubric 打分
