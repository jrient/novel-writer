# 动态漫大纲支持自定义集数（60集+）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户可以指定目标集数，采用两阶段生成策略（先生成简要大纲，再逐集展开），支持60集及以上的动态漫剧本大纲创作。

**Architecture:** 修改动态漫 outline prompt 只生成集标题+概要，新增 expand_episode 端点按需展开单集场景，集数由用户在 Step 1 摘要确认页填写并存入 session.summary。

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic v2, Vue 3, Element Plus, TypeScript

---

## 文件地图

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/schemas/drama.py` | 修改 | SessionSummaryResponse 新增 `目标集数` 字段 |
| `backend/app/services/script_ai_service.py` | 修改 | 改造 outline prompt（动态漫），新增 expand_episode prompt 和方法，动态 max_tokens |
| `backend/app/routers/drama.py` | 修改 | generate_outline 读取集数；新增 expand_episode 端点 |
| `backend/tests/test_drama_schemas.py` | 修改 | 新增 SessionSummaryResponse 目标集数测试 |
| `backend/tests/test_drama_ai_service.py` | 新建 | script_ai_service 单元测试 |
| `frontend/src/api/drama.ts` | 修改 | SessionSummary 新增 目标集数，新增 streamExpandEpisode |
| `frontend/src/views/DramaWizardView.vue` | 修改 | editableSummary 新增字段，Step 1 新增集数输入，Step 2 使用新组件 |
| `frontend/src/components/drama/OutlineDraftPreview.vue` | 新建 | Step 2 大纲预览组件，支持逐集展开 |

---

## Task 1: Backend Schema — 新增 目标集数 字段

**Files:**
- Modify: `backend/app/schemas/drama.py`
- Modify: `backend/tests/test_drama_schemas.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_drama_schemas.py` 文件末尾添加：

```python
# 在文件顶部的 import 里加 SessionSummaryResponse
from app.schemas.drama import (
    # ... existing imports ...
    SessionSummaryResponse,
)

def test_session_summary_response_default_episode_count():
    """目标集数有默认值 20"""
    data = {
        "故事概要": "一句话", "主要角色": ["角色A"],
        "核心冲突": "冲突", "场景设定": "设定", "风格基调": "悬疑",
    }
    s = SessionSummaryResponse(**data)
    assert s.目标集数 == 20


def test_session_summary_response_custom_episode_count():
    """目标集数可以自定义"""
    data = {
        "故事概要": "一句话", "主要角色": ["角色A"],
        "核心冲突": "冲突", "场景设定": "设定", "风格基调": "悬疑",
        "目标集数": 60,
    }
    s = SessionSummaryResponse(**data)
    assert s.目标集数 == 60


def test_session_summary_response_episode_count_min():
    """目标集数不能小于 1"""
    data = {
        "故事概要": "一句话", "主要角色": [],
        "核心冲突": "冲突", "场景设定": "设定", "风格基调": "悬疑",
        "目标集数": 0,
    }
    with pytest.raises(ValidationError):
        SessionSummaryResponse(**data)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/test_drama_schemas.py::test_session_summary_response_default_episode_count -v
```

期望输出：`ImportError` 或 `FAILED`（SessionSummaryResponse 尚未导出或缺少字段）

- [ ] **Step 3: 修改 Schema**

在 `backend/app/schemas/drama.py` 中修改 `SessionSummaryResponse`：

```python
# 在文件顶部加 Field import（已有则跳过）
from pydantic import BaseModel, ConfigDict, Field

class SessionSummaryResponse(BaseModel):
    """会话摘要响应（中文键名）"""
    故事概要: str
    主要角色: List[str]
    核心冲突: str
    场景设定: str
    风格基调: str
    目标集数: int = Field(default=20, ge=1, description="目标集数，仅动态漫有效")
```

同时在文件顶部的 `__all__` 或 import 区域确保 `SessionSummaryResponse` 可被导入（该文件无 `__all__`，直接修改即可）。

- [ ] **Step 4: 运行所有三个测试**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/test_drama_schemas.py -k "session_summary" -v
```

期望输出：三个测试均 `PASSED`

- [ ] **Step 5: 运行全量 schema 测试确保无回归**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/test_drama_schemas.py -v
```

期望输出：全部 `PASSED`

- [ ] **Step 6: 提交**

```bash
cd /data/project/novel-writer
git add backend/app/schemas/drama.py backend/tests/test_drama_schemas.py
git commit -m "feat(drama): add 目标集数 field to SessionSummaryResponse

Defaults to 20, min 1. Only meaningful for dynamic script type.
Stored in session.summary JSON column, no migration needed.

Constraint: SessionSummaryResponse is shared between summarize response and update request body
Confidence: high
Scope-risk: narrow"
```

---

## Task 2: AI Service — 改造 outline prompt + 新增 expand_episode

**Files:**
- Modify: `backend/app/services/script_ai_service.py`
- Create: `backend/tests/test_drama_ai_service.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_drama_ai_service.py`：

```python
"""
script_ai_service 单元测试
"""
import pytest
from app.services.script_ai_service import DYNAMIC_PROMPTS, ScriptAIService


def test_dynamic_outline_prompt_has_episode_count_placeholder():
    """动态漫 outline prompt 包含 {episode_count} 占位符"""
    user_prompt = DYNAMIC_PROMPTS["outline"]["user"]
    assert "{episode_count}" in user_prompt


def test_dynamic_outline_prompt_no_scene_content():
    """动态漫 outline prompt 不再要求生成 scene 内容"""
    user_prompt = DYNAMIC_PROMPTS["outline"]["user"]
    # 新 prompt 只要求标题+概要，不要求 scene content
    assert "场景描述" not in user_prompt
    assert "对白" not in user_prompt


def test_expand_episode_prompt_exists():
    """expand_episode prompt 存在"""
    assert "expand_episode" in DYNAMIC_PROMPTS


def test_expand_episode_prompt_has_required_placeholders():
    """expand_episode prompt 包含必要占位符"""
    user_prompt = DYNAMIC_PROMPTS["expand_episode"]["user"]
    for placeholder in ["{title}", "{outline_summary}", "{current_episode}",
                        "{episode_position}", "{main_characters}", "{core_conflict}"]:
        assert placeholder in user_prompt, f"Missing placeholder: {placeholder}"


def test_calc_max_tokens_for_episode_count():
    """max_tokens 根据集数动态计算"""
    from app.services.script_ai_service import calc_outline_max_tokens
    assert calc_outline_max_tokens(20) == 8000
    assert calc_outline_max_tokens(60) == max(8000, 60 * 150)  # 9000
    assert calc_outline_max_tokens(200) == 32000   # capped


def test_generate_outline_accepts_episode_count():
    """generate_outline 接受 episode_count 参数"""
    import inspect
    sig = inspect.signature(ScriptAIService.generate_outline)
    assert "episode_count" in sig.parameters
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/test_drama_ai_service.py -v
```

期望：多个 `FAILED`

- [ ] **Step 3: 修改 DYNAMIC_PROMPTS["outline"] prompt**

在 `backend/app/services/script_ai_service.py` 中，将 `DYNAMIC_PROMPTS["outline"]` 替换为：

```python
"outline": {
    "system": "你是一位专业的动态漫剧本策划师，擅长将创意构思转化为结构严谨的长篇剧本大纲。你必须严格输出 JSON 格式，不输出任何其他内容。",
    "user": """剧本基本信息：
标题：{title}
创意概念：{concept}
目标集数：{episode_count}

收集到的信息：
{history}

请生成一份 JSON 格式的简要大纲，要求：
1. 生成 {episode_count} 集的剧情大纲，覆盖故事的开端、发展、高潮、结局
2. 每集只需标题和一句话概要，不需要展开场景
3. 确保剧情连贯、节奏合理，各阶段集数分配得当
4. sort_order 必须从 0 开始连续递增

JSON 结构如下：
{{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {{
      "node_type": "episode",
      "title": "第一集：标题",
      "content": "本集一句话概要",
      "sort_order": 0,
      "children": []
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",
},
```

- [ ] **Step 4: 新增 expand_episode prompt 到 DYNAMIC_PROMPTS**

在 `DYNAMIC_PROMPTS` 的 `"expand"` 条目之前插入：

```python
"expand_episode": {
    "system": "你是一位专业的动态漫剧本撰写师，擅长将集概要展开为详细的场景描述。你必须严格输出 JSON 格式，不输出任何其他内容。",
    "user": """剧本信息：
标题：{title}
总体概述：{outline_summary}
主要角色：{main_characters}
核心冲突：{core_conflict}
风格基调：{style_tone}

当前集位置：{episode_position}
前一集：{prev_episode}
当前集：{current_episode}
后一集：{next_episode}

请将当前集展开为 2-4 个详细场景，要求：
1. 场景的 content 包含完整的场景描述、对白和动作
2. 场景之间衔接自然，与前后集保持连贯
3. sort_order 从 0 开始连续递增

JSON 结构如下：
{{
  "children": [
    {{
      "node_type": "scene",
      "title": "场景标题",
      "content": "【场景】场景描述\\n\\n【对白】\\n角色A：对白内容\\n\\n【动作】\\n动作描述",
      "sort_order": 0
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",
},
```

- [ ] **Step 5: 新增 calc_outline_max_tokens 函数**

在 `_build_history_text` 函数之前插入：

```python
def calc_outline_max_tokens(episode_count: int) -> int:
    """根据集数动态计算 outline 生成所需 max_tokens，上限 32000"""
    return min(32000, max(8000, episode_count * 150))
```

- [ ] **Step 6: 修改 generate_outline 方法签名和实现**

将现有的 `generate_outline` 方法替换为：

```python
async def generate_outline(
    self,
    script_type: str,
    title: str,
    concept: Optional[str],
    history: List[Dict[str, Any]],
    episode_count: int = 20,
) -> AsyncGenerator[str, None]:
    """生成剧本大纲（SSE 流式）"""
    prompts = _get_prompts(script_type)
    prompt_entry = prompts["outline"]

    # 动态漫使用 episode_count 占位符，解说漫不需要
    if script_type == "dynamic":
        prompt = prompt_entry["user"].format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
            episode_count=episode_count,
        )
        # 动态计算 max_tokens
        dynamic_max_tokens = calc_outline_max_tokens(episode_count)
        original_max_tokens = self.max_tokens
        self.max_tokens = max(self.max_tokens, dynamic_max_tokens)
    else:
        prompt = prompt_entry["user"].format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
        )
        original_max_tokens = self.max_tokens

    system_prompt = self._get_system_prompt("outline", script_type)
    messages = self._build_messages(prompt, system_prompt)
    try:
        async for chunk in self._stream(messages):
            yield chunk
    finally:
        self.max_tokens = original_max_tokens
```

- [ ] **Step 7: 新增 expand_episode 方法**

在 `generate_outline` 方法之后插入：

```python
async def expand_episode(
    self,
    title: str,
    outline_summary: str,
    main_characters: List[str],
    core_conflict: str,
    style_tone: str,
    episode_index: int,
    total_episodes: int,
    current_episode: Dict[str, Any],
    prev_episode: Optional[Dict[str, Any]],
    next_episode: Optional[Dict[str, Any]],
) -> AsyncGenerator[str, None]:
    """展开单集为详细场景（SSE 流式）"""
    prompt_entry = DYNAMIC_PROMPTS["expand_episode"]

    def _ep_str(ep: Optional[Dict[str, Any]]) -> str:
        if not ep:
            return "（无）"
        return f"{ep.get('title', '')}：{ep.get('content', '')}"

    # 判断故事阶段
    ratio = (episode_index + 1) / total_episodes
    if ratio <= 0.2:
        stage = "开端阶段"
    elif ratio <= 0.6:
        stage = "发展阶段"
    elif ratio <= 0.85:
        stage = "高潮阶段"
    else:
        stage = "结局阶段"

    prompt = prompt_entry["user"].format(
        title=title,
        outline_summary=outline_summary,
        main_characters="、".join(main_characters) if main_characters else "（未指定）",
        core_conflict=core_conflict or "（未指定）",
        style_tone=style_tone or "（未指定）",
        episode_position=f"第 {episode_index + 1} 集 / 共 {total_episodes} 集，处于{stage}",
        prev_episode=_ep_str(prev_episode),
        current_episode=_ep_str(current_episode),
        next_episode=_ep_str(next_episode),
    )
    system_prompt = prompt_entry["system"]
    messages = self._build_messages(prompt, system_prompt)
    async for chunk in self._stream(messages):
        yield chunk
```

- [ ] **Step 8: 运行测试**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/test_drama_ai_service.py -v
```

期望：全部 `PASSED`

- [ ] **Step 9: 运行全量测试防回归**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/ -v --ignore=tests/test_drama_models.py -x
```

期望：全部 `PASSED`（忽略需要数据库的模型测试）

- [ ] **Step 10: 提交**

```bash
cd /data/project/novel-writer
git add backend/app/services/script_ai_service.py backend/tests/test_drama_ai_service.py
git commit -m "feat(drama): add custom episode count support to outline and expand_episode AI methods

- Dynamic outline prompt now takes {episode_count} param, generates title+summary only (no scenes)
- New expand_episode method with full global context (characters, conflict, tone, position)
- Dynamic max_tokens calculation: max(8000, episode_count * 150), capped at 32000

Constraint: explanatory script type outline prompt unchanged
Rejected: always use 32000 max_tokens | wasteful for small episode counts
Confidence: high
Scope-risk: narrow"
```

---

## Task 3: Router — 修改 generate_outline + 新增 expand_episode 端点

**Files:**
- Modify: `backend/app/routers/drama.py`

- [ ] **Step 1: 修改 generate_outline 端点，读取集数并处理 JSON 截断**

找到 `session_generate_outline` 函数（约第 524 行），替换 `stream()` 内部函数：

```python
@router.post("/{id}/session/generate-outline")
async def session_generate_outline(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """生成大纲草稿（SSE 流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")

    session.state = "generating"
    await db.commit()

    # 读取目标集数（仅动态漫有效）
    episode_count = 20
    if project.script_type == "dynamic" and session.summary:
        episode_count = int((session.summary or {}).get("目标集数", 20))
        episode_count = max(1, min(200, episode_count))

    history = list(session.history or [])
    if session.summary:
        import json as _json
        summary_text = _json.dumps(session.summary, ensure_ascii=False)
        history = history + [
            {"role": "assistant", "content": "根据以上对话，我整理的创作信息如下："},
            {"role": "user", "content": f"确认的创作信息：{summary_text}\n请严格基于以上确认信息生成大纲。"},
        ]
    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_outline(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=history,
                episode_count=episode_count,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if full_response:
            try:
                json_str = full_response.strip()
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]

                outline_json = json.loads(json_str)
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session:
                    if updated_session.outline_draft:
                        outline_history = list(updated_session.outline_history or [])
                        outline_history.append(updated_session.outline_draft)
                        updated_session.outline_history = outline_history
                    updated_session.outline_draft = outline_json
                    updated_session.state = "done"
                    await db.commit()
                    logger.info(f"Outline saved for project {project.id}, episodes={episode_count}")
                    # 检查生成的集数是否完整
                    actual_count = len(outline_json.get("sections", []))
                    if actual_count < episode_count:
                        yield f"data: {json.dumps({'type': 'partial_warning', 'actual': actual_count, 'expected': episode_count})}\n\n"
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse outline JSON: {e}")
                # 尝试补全截断的 JSON
                try:
                    fixed = json_str.rstrip()
                    # 补全常见截断：缺少结尾的 ]}}
                    for suffix in [']}', ']}', ']}}']:
                        try:
                            outline_json = json.loads(fixed + suffix)
                            # 解析成功，保存修复后的结果
                            update_result = await db.execute(
                                select(ScriptSession).where(ScriptSession.project_id == project.id)
                            )
                            updated_session = update_result.scalar_one_or_none()
                            if updated_session:
                                updated_session.outline_draft = outline_json
                                updated_session.state = "done"
                                await db.commit()
                                actual_count = len(outline_json.get("sections", []))
                                yield f"data: {json.dumps({'type': 'partial_warning', 'actual': actual_count, 'expected': episode_count})}\n\n"
                            break
                        except json.JSONDecodeError:
                            continue
                    else:
                        # 无法修复
                        yield f"data: {json.dumps({'type': 'error', 'message': f'大纲生成不完整，请减少集数后重试'})}\n\n"
                        return
                except Exception:
                    yield f"data: {json.dumps({'type': 'error', 'message': '大纲解析失败，请重试'})}\n\n"
                    return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())
```

- [ ] **Step 2: 新增 ExpandEpisodeRequest schema（在 drama.py 路由文件或 schemas 中）**

在 `backend/app/schemas/drama.py` 末尾添加：

```python
class ExpandEpisodeRequest(BaseModel):
    """展开单集请求"""
    episode_index: int = Field(..., ge=0, description="要展开的集索引（从0开始）")
```

- [ ] **Step 3: 新增 expand_episode 路由端点**

在 `session_generate_outline` 函数之后添加：

```python
@router.post("/{id}/session/expand-episode")
async def session_expand_episode(
    body: ExpandEpisodeRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """展开单集为详细场景（SSE 流式）"""
    if project.script_type != "dynamic":
        raise HTTPException(status_code=400, detail="仅动态漫支持逐集展开")

    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not session.outline_draft:
        raise HTTPException(status_code=400, detail="请先生成大纲")

    sections = session.outline_draft.get("sections", [])
    idx = body.episode_index
    if idx < 0 or idx >= len(sections):
        raise HTTPException(status_code=400, detail=f"集索引 {idx} 超出范围（共 {len(sections)} 集）")

    current_ep = sections[idx]
    prev_ep = sections[idx - 1] if idx > 0 else None
    next_ep = sections[idx + 1] if idx < len(sections) - 1 else None
    total = len(sections)

    summary_data = session.summary or {}
    main_characters = summary_data.get("主要角色", [])
    core_conflict = summary_data.get("核心冲突", "")
    style_tone = summary_data.get("风格基调", "")
    outline_summary = session.outline_draft.get("summary", "")

    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.expand_episode(
                title=project.title,
                outline_summary=outline_summary,
                main_characters=main_characters,
                core_conflict=core_conflict,
                style_tone=style_tone,
                episode_index=idx,
                total_episodes=total,
                current_episode=current_ep,
                prev_episode=prev_ep,
                next_episode=next_ep,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"expand_episode stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if full_response:
            try:
                json_str = full_response.strip()
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]
                result_json = json.loads(json_str)
                children = result_json.get("children", [])

                # 写回 outline_draft
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session and updated_session.outline_draft:
                    import copy
                    new_draft = copy.deepcopy(updated_session.outline_draft)
                    new_sections = new_draft.get("sections", [])
                    if idx < len(new_sections):
                        new_sections[idx]["children"] = children
                        new_draft["sections"] = new_sections
                        updated_session.outline_draft = new_draft
                        await db.commit()
                        logger.info(f"Episode {idx} expanded with {len(children)} scenes for project {project.id}")
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse expand_episode JSON: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': '场景生成解析失败，请重试'})}\n\n"
                return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())
```

- [ ] **Step 4: 在 routers/drama.py 顶部补充 ExpandEpisodeRequest 导入**

找到 drama.py 中的 schema 导入区，添加 `ExpandEpisodeRequest`：

```python
from app.schemas.drama import (
    # ... existing imports ...
    ExpandEpisodeRequest,
)
```

- [ ] **Step 5: 启动后端，手动验证端点存在**

```bash
cd /data/project/novel-writer && docker compose up -d backend
docker compose exec backend python -c "from app.routers.drama import router; routes = [r.path for r in router.routes]; print([r for r in routes if 'expand' in r])"
```

期望输出：`['/{id}/session/expand-episode']`

- [ ] **Step 6: 运行全量测试**

```bash
cd /data/project/novel-writer && docker compose exec backend pytest tests/ -v -x
```

期望：全部 `PASSED`

- [ ] **Step 7: 提交**

```bash
cd /data/project/novel-writer
git add backend/app/routers/drama.py backend/app/schemas/drama.py
git commit -m "feat(drama): add expand_episode endpoint and episode_count to generate_outline

- generate_outline reads 目标集数 from session.summary, passes to AI service
- Dynamic max_tokens based on episode count
- JSON truncation handling: try bracket-repair, fallback to partial_warning event
- New POST /{id}/session/expand-episode endpoint for on-demand episode expansion

Constraint: episode_index uses array position (not UUID) — known race condition risk documented in spec
Confidence: high
Scope-risk: moderate"
```

---

## Task 4: 前端 API — SessionSummary 类型 + streamExpandEpisode

**Files:**
- Modify: `frontend/src/api/drama.ts`

- [ ] **Step 1: 修改 SessionSummary interface，新增 目标集数**

找到 `frontend/src/api/drama.ts` 中的 `SessionSummary` interface（约第 107 行），替换为：

```typescript
export interface SessionSummary {
  故事概要: string
  主要角色: string[]
  核心冲突: string
  场景设定: string
  风格基调: string
  目标集数: number
}
```

- [ ] **Step 2: 新增 streamExpandEpisode 函数**

在 `streamGenerateOutline` 函数之后添加：

```typescript
export function streamExpandEpisode(
  projectId: number,
  episodeIndex: number,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/expand-episode`,
    { episode_index: episodeIndex },
    onChunk,
    onDone,
    onError,
  )
}
```

- [ ] **Step 3: 验证 TypeScript 编译无错误**

```bash
cd /data/project/novel-writer && docker compose exec frontend npx tsc --noEmit 2>&1 | head -30
```

期望：无类型错误输出（或仅有预存的无关错误）

- [ ] **Step 4: 提交**

```bash
cd /data/project/novel-writer
git add frontend/src/api/drama.ts
git commit -m "feat(drama): add 目标集数 to SessionSummary type and streamExpandEpisode API"
```

---

## Task 5: 前端 DramaWizardView — Step 1 新增集数输入

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 更新 editableSummary 响应式对象，加入 目标集数 默认值**

找到 `DramaWizardView.vue` 中的 `editableSummary`（约第 204 行），替换为：

```typescript
const editableSummary = reactive<SessionSummary>({
  故事概要: '',
  主要角色: [],
  核心冲突: '',
  场景设定: '',
  风格基调: '',
  目标集数: 20,
})
```

- [ ] **Step 2: 找到 syncEditableSummary 函数，补充 目标集数 同步**

找到 `syncEditableSummary` 函数（搜索 `syncEditableSummary`），确保包含 `目标集数` 的处理：

```typescript
function syncEditableSummary(summary: SessionSummary) {
  editableSummary.故事概要 = summary.故事概要 || ''
  editableSummary.主要角色 = [...(summary.主要角色 || [])]
  editableSummary.核心冲突 = summary.核心冲突 || ''
  editableSummary.场景设定 = summary.场景设定 || ''
  editableSummary.风格基调 = summary.风格基调 || ''
  editableSummary.目标集数 = summary.目标集数 ?? 20
}
```

- [ ] **Step 3: 在 Step 1 模板中，"风格基调"区块后面添加"目标集数"输入**

找到 `<!-- 风格基调 -->` 对应的 `</div>` 结束标签（约第 125 行），在其后、`</div class="summary-card">` 之前插入：

```html
<div v-if="dramaStore.currentProject?.script_type === 'dynamic'" class="summary-section">
  <h4>目标集数</h4>
  <p class="summary-hint">AI 将生成这么多集的简要大纲，之后可逐集展开详细场景</p>
  <el-input-number
    v-model="editableSummary.目标集数"
    :min="1"
    :max="200"
    :step="10"
    controls-position="right"
    style="width: 160px"
  />
</div>
```

同时在 `<style scoped>` 中添加：

```css
.summary-hint {
  font-size: 12px;
  color: #9E9E9E;
  margin: 4px 0 8px;
}
```

- [ ] **Step 4: 在浏览器中验证 Step 1 显示正常（有集数输入框）**

```bash
cd /data/project/novel-writer && docker compose up -d frontend
```

访问一个动态漫项目的向导页，完成问答后，Step 1 应该在"风格基调"下方看到"目标集数"输入框，默认值 20。

- [ ] **Step 5: 提交**

```bash
cd /data/project/novel-writer
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): add 目标集数 input to wizard step 1 summary review

Only shown for dynamic script type. Defaults to 20, stored in session.summary."
```

---

## Task 6: 新建 OutlineDraftPreview 组件

**Files:**
- Create: `frontend/src/components/drama/OutlineDraftPreview.vue`

该组件接收 `outline_draft.sections` 数组，显示每集标题+概要，支持逐集展开。

- [ ] **Step 1: 新建组件文件**

创建 `frontend/src/components/drama/OutlineDraftPreview.vue`：

```vue
<template>
  <div class="outline-draft-preview">
    <div v-if="!sections.length" class="empty-state">
      <el-empty description="暂无大纲数据" :image-size="60" />
    </div>

    <div v-else class="episode-list">
      <div
        v-for="(ep, index) in sections"
        :key="index"
        class="episode-item"
        :class="{ 'episode-item--expanded': isExpanded(index) }"
      >
        <!-- 集标题行 -->
        <div class="episode-header">
          <div class="episode-meta">
            <span class="episode-index">第 {{ index + 1 }} 集</span>
            <span class="episode-title">{{ ep.title }}</span>
          </div>
          <div class="episode-actions">
            <el-tag v-if="isExpanded(index)" type="success" size="small">已展开</el-tag>
            <el-button
              v-else
              size="small"
              :loading="expandingIndex === index"
              @click="handleExpand(index)"
            >
              展开场景
            </el-button>
          </div>
        </div>

        <!-- 集概要 -->
        <p class="episode-summary">{{ ep.content }}</p>

        <!-- 已展开的场景列表 -->
        <div v-if="isExpanded(index)" class="scene-list">
          <div
            v-for="(scene, si) in ep.children"
            :key="si"
            class="scene-item"
          >
            <span class="scene-index">场景 {{ si + 1 }}</span>
            <span class="scene-title">{{ scene.title }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamExpandEpisode } from '@/api/drama'

interface EpisodeSection {
  node_type: string
  title: string
  content: string
  sort_order: number
  children: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}

const props = defineProps<{
  projectId: number
  sections: EpisodeSection[]
}>()

const emit = defineEmits<{
  (e: 'episode-expanded', index: number): void
}>()

const expandingIndex = ref<number | null>(null)

function isExpanded(index: number): boolean {
  return (props.sections[index]?.children?.length ?? 0) > 0
}

function handleExpand(index: number) {
  if (expandingIndex.value !== null) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }
  expandingIndex.value = index

  streamExpandEpisode(
    props.projectId,
    index,
    () => { /* chunk 忽略，完成后刷新 */ },
    () => {
      expandingIndex.value = null
      emit('episode-expanded', index)
    },
    (error) => {
      expandingIndex.value = null
      ElMessage.error(`展开失败：${error}`)
    },
  )
}
</script>

<style scoped>
.outline-draft-preview {
  padding: 8px 0;
}

.episode-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.episode-item {
  border: 1px solid #ECEAE6;
  border-radius: 8px;
  padding: 12px 16px;
  background: #FAFAF9;
  transition: border-color 0.2s;
}

.episode-item--expanded {
  border-color: #67c23a;
  background: #f0f9eb;
}

.episode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.episode-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.episode-index {
  font-size: 12px;
  color: #9E9E9E;
  white-space: nowrap;
  flex-shrink: 0;
}

.episode-title {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-actions {
  flex-shrink: 0;
}

.episode-summary {
  font-size: 13px;
  color: #6B7B8D;
  margin: 6px 0 0;
  line-height: 1.5;
}

.scene-list {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #E8F5E9;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.scene-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.scene-index {
  color: #9E9E9E;
  flex-shrink: 0;
}

.scene-title {
  color: #4CAF50;
}
</style>
```

- [ ] **Step 2: 验证 TypeScript 编译无错误**

```bash
cd /data/project/novel-writer && docker compose exec frontend npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: 提交**

```bash
cd /data/project/novel-writer
git add frontend/src/components/drama/OutlineDraftPreview.vue
git commit -m "feat(drama): add OutlineDraftPreview component for two-stage outline expansion

Shows N episodes as title+summary cards. Each episode has an expand button
that calls streamExpandEpisode SSE. Expanded episodes show scene titles.

Constraint: only one episode can expand at a time to avoid SSE conflicts
Confidence: high
Scope-risk: narrow"
```

---

## Task 7: 前端 DramaWizardView — Step 2 替换为 OutlineDraftPreview

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 导入 OutlineDraftPreview 组件**

在 `DramaWizardView.vue` 的 `<script setup>` 中，找到现有的组件导入区：

```typescript
import OutlineDraftPreview from '@/components/drama/OutlineDraftPreview.vue'
```

- [ ] **Step 2: 新增 handleEpisodeExpanded 处理函数**

在 `handleGenerateOutline` 函数之后添加：

```typescript
async function handleEpisodeExpanded(_index: number) {
  // 刷新 session 以获取最新的 outline_draft（含展开后的 children）
  await dramaStore.fetchSession(projectId.value)
}
```

- [ ] **Step 3: 替换 Step 2 模板中的 ScriptOutlineTree**

找到 Step 2 模板（`<!-- Step 2: 大纲预览 -->`），将 `<ScriptOutlineTree>` 部分替换为：

```html
<!-- Step 2: 大纲预览 -->
<template v-else-if="wizardStepIndex === 2">
  <div class="outline-review">
    <div class="outline-header">
      <h3 class="outline-title">剧本大纲</h3>
      <p class="outline-subtitle">
        共 {{ outlineSections.length }} 集 · 点击"展开场景"可逐集生成详细场景
      </p>
    </div>

    <div class="outline-tree-wrapper">
      <OutlineDraftPreview
        :project-id="projectId"
        :sections="outlineSections"
        @episode-expanded="handleEpisodeExpanded"
      />
    </div>

    <div class="outline-actions">
      <el-button @click="wizardStepIndex = 1">返回确认</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="confirming"
        @click="handleConfirmOutline"
        round
      >
        确认大纲，开始创作
      </el-button>
    </div>
  </div>
</template>
```

- [ ] **Step 4: 新增 outlineSections computed 属性**

在 `outlineDraftNodes` computed 之后添加：

```typescript
const outlineSections = computed(() => {
  const draft = dramaStore.session?.outline_draft
  if (!draft?.sections) return []
  return draft.sections as Array<{
    node_type: string
    title: string
    content: string
    sort_order: number
    children: Array<{ node_type: string; title: string; content: string; sort_order: number }>
  }>
})
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd /data/project/novel-writer && docker compose exec frontend npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 6: 启动完整应用，手动验证端到端流程**

```bash
cd /data/project/novel-writer && docker compose up -d
```

验证步骤：
1. 创建一个新的动态漫项目
2. 完成 5 个问答
3. Step 1 摘要确认页，确认"目标集数"输入框存在，改为 20
4. 点击"生成大纲"，等待完成
5. Step 2 显示 20 集的简要大纲列表
6. 点击某集的"展开场景"按钮
7. 展开完成后，该集显示"已展开"标签和场景列表

- [ ] **Step 7: 提交**

```bash
cd /data/project/novel-writer
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): replace outline tree with OutlineDraftPreview in wizard step 2

Step 2 now shows episode list with expand-on-demand. Each episode starts as
title+summary only; clicking 'expand' generates detailed scenes via SSE.
User can confirm outline at any time without expanding all episodes.

Confidence: high
Scope-risk: moderate"
```

---

## 完成验证

- [ ] 全量后端测试通过：`docker compose exec backend pytest tests/ -v`
- [ ] TypeScript 无新错误：`docker compose exec frontend npx tsc --noEmit`
- [ ] 端到端手动验证：生成 20 集大纲，逐集展开，确认大纲进入创作台
