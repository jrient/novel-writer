# 去掉场景层 — 集作为最小内容单元

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将动态漫 Wizard 流程中的「分集→场景」两级生成改为「集」为最小内容单元，AI 直接生成 800-1500 字纯文本剧本写入集的 content 字段。

**Architecture:** 修改 AI prompt（纯文本输出替代 JSON 场景结构）→ 修改后端端点（不再解析 JSON，直接写文本+标记）→ 修改前端组件（按钮文案、判断逻辑、UI 简化）。改动集中在动态漫 Wizard 流程，不改数据模型。

**Tech Stack:** FastAPI + Python (async), Vue 3 + TypeScript + Element Plus

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/script_ai_service.py` | 修改 | `expand_episode` 改为 `generate_episode_content`，prompt 改为输出纯文本 |
| `backend/app/routers/drama.py` | 修改 | `session_expand_episode` 端点去掉 JSON 解析，改为写 content + generated 标记 |
| `frontend/src/components/drama/OutlineDraftPreview.vue` | 修改 | 按钮文案、判断逻辑、删除场景列表 |
| `frontend/src/views/DramaWizardView.vue` | 修改 | 文案适配、判断逻辑适配 |

## 不改动的文件（明确边界）

| 文件 | 说明 |
|------|------|
| `frontend/src/api/drama.ts` | API 接口不变，前端仍调用 `streamExpandEpisode` |
| `backend/app/models/script_node.py` | 数据模型不变 |
| `backend/app/schemas/drama.py` | Schema 不变 |
| 所有工作台组件（ScriptEditor, ScriptAiPanel, ScriptOutlineTree 等）| 本次不碰 |
| 解说漫相关代码 | 完全不受影响 |

---

### Task 1: AI Prompt 改造 — generate_episode_content

**Files:**
- Modify: `backend/app/services/script_ai_service.py`

- [ ] **Step 1: 将 `expand_episode` 方法重命名为 `generate_episode_content`**

在 `script_ai_service.py` 中，找到 `async def expand_episode(` 方法定义（约第 585 行），重命名为 `generate_episode_content`。同时修改方法内部的 prompt_entry 引用。

```python
async def generate_episode_content(
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
    """生成单集完整内容（SSE 流式，输出纯文本）"""
    prompt_entry = {
        "system": "你是一位专业的动态漫剧本撰写师，擅长将集概要展开为完整的叙事内容。你直接输出纯文本剧本，不输出 JSON，不使用结构化标签。",
        "user": """剧本信息：
标题：{title}
总体概述：{outline_summary}
主要角色：{main_characters}
核心冲突：{core_conflict}
风格基调：{style_tone}

当前集位置：{episode_position}
前一集：{prev_episode}
当前集概要：{current_episode}
后一集：{next_episode}

请将当前集扩展为一段完整的剧本文本，要求：
1. 800-1500 字
2. 包含自然穿插的对白、动作描写、心理活动和环境描写
3. 从"前一集"的结尾状态自然衔接开始，不要凭空切换
4. 结尾必须与"后一集"的开头衔接，留好过渡
5. 不要使用【场景】【对白】【动作】等结构化标签
6. 不要分场景，一气呵成
7. 对白自然流畅，符合人物性格

直接输出完整的剧本内容，不要有任何前缀或解释：""",
    }
```

替换原有的 DYNAMIC_PROMPTS["expand_episode"] 引用为上述内联 prompt。

- [ ] **Step 2: 替换方法体中的 prompt 构建逻辑**

删除对 `DYNAMIC_PROMPTS["expand_episode"]` 的引用，改为使用上面内联的 `prompt_entry`。同时修改 `.format()` 参数：

```python
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

- [ ] **Step 3: 同时保留旧的 DYNAMIC_PROMPTS["expand_episode"] 供参考（可选删除）**

从 `DYNAMIC_PROMPTS` 字典中删除 `"expand_episode"` 条目（第 183-217 行），因为已被内联 prompt 替代。

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/script_ai_service.py
git commit -m "refactor(ai): replace expand_episode with generate_episode_content

AI now outputs plain text (800-1500 chars) instead of JSON scene
structure. Episodes become the minimal content unit.

Confidence: high
Scope-risk: narrow"
```

---

### Task 2: 后端 Router 改造 — session_expand_episode

**Files:**
- Modify: `backend/app/routers/drama.py`

- [ ] **Step 1: 修改 `session_expand_episode` 端点**

当前逻辑：调用 `ai_service.expand_episode` → 等待 JSON → 解析 children → 写回 outline_draft。改为：调用 `ai_service.generate_episode_content` → 拼接纯文本 → 写入 episode 的 content + generated 标记。

替换 `session_expand_episode` 函数体中（约第 714-806 行）的 `async def stream():` 内部逻辑：

```python
@router.post("/{id}/session/expand-episode")
async def session_expand_episode(
    body: ExpandEpisodeRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """生成单集完整内容（SSE 流式）"""
    if project.script_type != "dynamic":
        raise HTTPException(status_code=400, detail="仅动态漫支持逐集生成")

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

    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_episode_content(
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
            logger.error(f"generate_episode_content stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if full_response:
            try:
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session and updated_session.outline_draft:
                    import copy
                    new_draft = copy.deepcopy(updated_session.outline_draft)
                    new_sections = new_draft.get("sections", [])
                    if idx < len(new_sections):
                        # 纯文本直接写入 content，标记已生成
                        new_sections[idx]["content"] = full_response.strip()
                        new_sections[idx]["generated"] = True
                        # 清除旧的 children（如果有）
                        new_sections[idx].pop("children", None)
                        new_draft["sections"] = new_sections
                        updated_session.outline_draft = new_draft
                        await db.commit()
                        logger.info(f"Episode {idx} content generated for project {project.id}")
            except Exception as e:
                logger.warning(f"Could not save episode content: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': '内容保存失败，请重试'})}\n\n"
                return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())
```

- [ ] **Step 2: 删除不再需要的 JSON 解析逻辑**

原代码中的 `json_str = full_response.strip()` → `json.loads(json_str)` → `children = result_json.get("children", [])` 整段替换为上述的纯文本保存逻辑。

- [ ] **Step 3: 提交**

```bash
git add backend/app/routers/drama.py
git commit -m "refactor(drama): simplify expand-episode endpoint for plain text output

No more JSON parsing. Episode content is saved directly to
outline_draft.sections[idx].content with a generated=true marker.

Confidence: high
Scope-risk: narrow"
```

---

### Task 3: 前端 — OutlineDraftPreview 组件简化

**Files:**
- Modify: `frontend/src/components/drama/OutlineDraftPreview.vue`

- [ ] **Step 1: 修改 isExpanded 判断逻辑**

将 `isExpanded` 函数从检查 `children.length` 改为检查 `generated` 标记：

```typescript
function isExpanded(index: number): boolean {
  return props.sections[index]?.generated === true
}
```

- [ ] **Step 2: 修改 EpisodeSection 接口**

```typescript
interface EpisodeSection {
  node_type: string
  title: string
  content: string
  sort_order: number
  generated?: boolean
  children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}
```

- [ ] **Step 3: 修改按钮文案和标签**

模板中的 "展开场景" 按钮改为 "生成内容"，"已展开" 标签改为 "已生成"：

```vue
<!-- 按钮 -->
<el-button
  v-if="!props.disableIndividual && !isExpanded(index)"
  size="small"
  :loading="expandingIndex === index"
  @click="handleExpand(index)"
>
  生成内容
</el-button>

<!-- 标签 -->
<el-tag v-if="isExpanded(index)" type="success" size="small">已生成</el-tag>
```

- [ ] **Step 4: 删除场景列表区域**

移除整个 `.scene-list` 的 div：

```vue
<!-- 删除这段：场景列表 -->
<!--
<div v-if="isExpanded(index)" class="scene-list">
  <div v-for="(scene, si) in ep.children" :key="si" class="scene-item">
    <span class="scene-index">场景 {{ si + 1 }}</span>
    <span class="scene-title">{{ scene.title }}</span>
  </div>
</div>
-->
```

- [ ] **Step 5: 添加内容预览（可选，提升体验）**

在已生成的集卡片下方显示内容预览：

```vue
<!-- 集概要下方 -->
<p class="episode-summary">{{ ep.content }}</p>

<!-- 新增：已生成时显示完整内容预览 -->
<div v-if="isExpanded(index)" class="episode-content-preview">
  <el-divider content-position="left">
    <el-tag size="small">完整内容</el-tag>
  </el-divider>
  <div class="full-content">{{ ep.content }}</div>
</div>
```

添加样式：

```css
.episode-content-preview {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #E8F5E9;
}

.full-content {
  font-size: 14px;
  color: #2C2C2C;
  line-height: 1.8;
  white-space: pre-wrap;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
  background: #FAFAF9;
  border-radius: 4px;
}
```

- [ ] **Step 6: 修改 episode-item--expanded 样式类名含义**

样式类名 `episode-item--expanded` 保持不变（只是 CSS 类名，不影响语义），但它现在表示"已生成内容"的样式。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/drama/OutlineDraftPreview.vue
git commit -m "refactor(frontend): simplify outline preview for episode-level content

Replace '展开场景' with '生成内容'. Remove scene list.
Check generated=true marker instead of children.

Confidence: high
Scope-risk: narrow"
```

---

### Task 4: 前端 — DramaWizardView 文案适配

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 修改副标题文案**

将第 162 行附近的副标题从：

```vue
<p class="outline-subtitle">
  共 {{ outlineSections.length }} 集 · 可逐集展开或一键展开全部场景
</p>
```

改为：

```vue
<p class="outline-subtitle">
  共 {{ outlineSections.length }} 集 · 可逐集生成或一键生成全部内容
</p>
```

- [ ] **Step 2: 修改 allExpanded 计算属性**

将 `allExpanded` 从检查 `children` 改为检查 `generated`：

```typescript
const allExpanded = computed(() =>
  outlineSections.value.length > 0 &&
  outlineSections.value.every(ep => ep.generated === true)
)
```

- [ ] **Step 3: 修改"展开全部场景"按钮文案**

```vue
<el-button
  plain
  :loading="isExpandingAll"
  :disabled="allExpanded"
  @click="handleExpandAll"
>
  {{ isExpandingAll ? `生成中 (${expandAllCurrent}/${expandAllTotal})` : allExpanded ? '已全部生成' : '生成全部内容' }}
</el-button>
```

- [ ] **Step 4: 修改 handleExpandAll 中的对话框文案**

将 ElMessageBox.confirm 的按钮文案更新：

```typescript
await ElMessageBox.confirm(
  '部分集已生成，请选择处理方式',
  '生成全部内容',
  {
    distinguishCancelAndClose: true,
    confirmButtonText: '全部重新生成',
    cancelButtonText: '跳过已生成',
  },
)
```

- [ ] **Step 5: 修改完成提示文案**

```typescript
if (failCount === targets.length) {
  ElMessage.error('全部集生成失败')
} else if (failCount > 0) {
  ElMessage.warning(`${failCount} 集生成失败，其余已完成`)
} else {
  ElMessage.success('全部内容生成完成')
}
```

- [ ] **Step 6: 修改正在展开的警告文案**

```typescript
// 防止重复触发
if (isExpandingAll.value) {
  ElMessage.warning('正在生成全部内容，请等待完成')
  return
}
// 单集正在生成中，拒绝
if (isSingleExpanding.value) {
  ElMessage.warning('请等待当前集生成完成')
  return
}
```

- [ ] **Step 7: 修改没有需要生成的集的提示**

```typescript
if (targets.length === 0) {
  ElMessage.info('没有需要生成的集')
  return
}
```

- [ ] **Step 8: 修改错误提示中的变量名**

```typescript
(error) => {
  ElMessage.error(`第 ${originalIndex + 1} 集生成失败：${error}`)
  currentAbortController.value = null
  failCount++
  resolve()
},
```

- [ ] **Step 9: 提交**

```bash
git add frontend/src/views/DramaWizardView.vue
git commit -m "refactor(frontend): adapt wizard copy for episode-level content generation

All '展开场景'/'已展开' references changed to '生成内容'/'已生成'.
Check generated=true marker instead of children.

Confidence: high
Scope-risk: narrow"
```

---

## 自审

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|-----------|-----------|
| AI prompt 改为输出纯文本 | Task 1 ✅ |
| 端点不再解析 JSON，直接写 content + generated | Task 2 ✅ |
| OutlineDraftPreview 按钮文案、判断逻辑、删除场景列表 | Task 3 ✅ |
| DramaWizardView 文案适配 | Task 4 ✅ |
| confirm-outline 不改 | 已明确标注不改动 ✅ |
| 数据模型不改 | 已明确标注不改动 ✅ |
| 解说漫不受影响 | 已明确标注边界 ✅ |
| 无旧数据迁移 | 已明确标注 ✅ |
| rewrite/expand/global-directive 保留但不改 | 已明确标注 ✅ |

### 占位符扫描

无 TBD/TODO，所有代码步骤都有具体内容。

### 类型一致性

`generated` 标记统一为 `boolean`（`true`），前端判断统一为 `ep.generated === true`。API 调用仍用 `streamExpandEpisode`，函数名不变。

### 完整性

所有 4 个文件的改动都已完整覆盖。每个 Task 可独立提交、独立测试。
