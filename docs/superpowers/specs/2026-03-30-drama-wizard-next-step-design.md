# 剧本创作问答流程优化设计

## 背景

当前剧本创作页面（DramaWizardView）的 AI 问答流程：
- 用户在 WizardChat 中回答 AI 问题
- AI 返回 `"done":true` 或用户点击"信息已足够"按钮 → 自动触发大纲生成
- 直接跳转到大纲预览页

用户需求：在 AI 收集足够信息后，增加一个"信息确认"步骤，让用户查看汇总信息后再决定生成大纲。

## 目标

将 3 步流程改为 4 步流程：

```
原来: [AI 问答] → [大纲预览] → [开始创作]
改后: [AI 问答] → [信息确认] → [大纲预览] → [开始创作]
```

核心改动：
1. 回答 5 个问题后，底部按钮变为"下一步"
2. 点击"下一步"，后端生成结构化摘要存入 session
3. 用户在"信息确认"页查看摘要，确认后点击"生成大纲"
4. **移除"跳过问答"功能**

---

## 前端改动

### WizardChat.vue

**移除底部 action-bar：**
- 删除现有的"信息已足够，开始生成大纲"按钮区域
- 该逻辑移到父组件 DramaWizardView 处理

**新增 emit 事件：**
```typescript
emit('questions-complete')  // questionCount >= 5 时触发
```

**修改 AI 响应处理：**
- 当 AI 返回 `"done":true` 时，不再自动触发 `generateOutline()`
- 改为 emit `questions-complete` 通知父组件

### DramaWizardView.vue

**扩展 Wizard 步骤：**
```typescript
const wizardSteps = [
  { title: 'AI 问答' },    // Step 0
  { title: '信息确认' },   // Step 1（新增）
  { title: '大纲预览' },   // Step 2（原 Step 1）
  { title: '开始创作' },   // Step 3（原 Step 2）
]
```

**注意：步骤条显示逻辑需同步调整，确保 done/active 状态正确显示。**

**新增状态变量：**
```typescript
const questionsComplete = ref(false)  // 是否完成 5 个问题
const sessionSummary = ref<SessionSummary | null>(null)  // 汇总信息
```

**Footer 按钮：**
```vue
<div class="wizard-footer">
  <!-- 回答少于 5 个问题时显示提示 -->
  <span v-if="questionCount < 5" class="hint-text">
    还需回答 {{ 5 - questionCount }} 个问题才能继续
  </span>

  <!-- 完成问答后 -->
  <el-button
    v-else
    type="primary"
    size="large"
    :loading="summarizing"
    @click="handleNextStep"
    class="next-btn"
    round
  >
    下一步
  </el-button>
</div>
```

**注意：移除原有的"跳过问答，直接生成大纲"按钮。**

**新增 handleNextStep 方法：**
```typescript
async function handleNextStep() {
  summarizing.value = true
  try {
    const summary = await summarizeSession(projectId.value)
    sessionSummary.value = summary
    wizardStepIndex.value = 1  // 跳转到信息确认页
  } catch {
    ElMessage.error('汇总信息失败')
  } finally {
    summarizing.value = false
  }
}
```

**新增 Step 1 信息确认页模板：**
```vue
<template v-else-if="wizardStepIndex === 1">
  <div class="summary-review">
    <div class="summary-header">
      <h3>创作信息汇总</h3>
      <p>请检查 AI 汇总的信息，确认后开始生成大纲</p>
    </div>

    <div class="summary-card">
      <div class="summary-section">
        <h4>故事概要</h4>
        <p>{{ sessionSummary?.故事概要 }}</p>
      </div>

      <div class="summary-section">
        <h4>主要角色</h4>
        <ul>
          <li v-for="c in sessionSummary?.主要角色" :key="c">{{ c }}</li>
        </ul>
      </div>

      <div class="summary-section">
        <h4>核心冲突</h4>
        <p>{{ sessionSummary?.核心冲突 }}</p>
      </div>

      <div class="summary-section">
        <h4>场景设定</h4>
        <p>{{ sessionSummary?.场景设定 }}</p>
      </div>

      <div class="summary-section">
        <h4>风格基调</h4>
        <p>{{ sessionSummary?.风格基调 }}</p>
      </div>
    </div>

    <div class="summary-actions">
      <el-button @click="handleBackToChat">重新问答</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="generatingOutline"
        @click="handleGenerateOutline"
        round
      >
        生成大纲
      </el-button>
    </div>
  </div>
</template>
```

**handleBackToChat 方法（返回重新问答时清除 summary）：**
```typescript
function handleBackToChat() {
  sessionSummary.value = null  // 清除摘要，下次点击"下一步"会重新生成
  wizardStepIndex.value = 0
}
```

### api/drama.ts

**新增 summarizeSession API：**
```typescript
export async function summarizeSession(projectId: number): Promise<SessionSummary> {
  const res = await axios.post(`/api/v1/drama/${projectId}/session/summarize`)
  return res.data
}

export interface SessionSummary {
  故事概要: string
  主要角色: string[]
  核心冲突: string
  场景设定: string
  风格基调: string
}
```

---

## 后端改动

### ScriptSession 模型

**新增 summary 字段：**
```python
# app/models/script_session.py
class ScriptSession(Base):
    ...
    summary = Column(JSON, nullable=True)  # 新增：AI 汇总的结构化信息
```

### Drama Router

**新增 summarize API：**
```python
@router.post("/{id}/session/summarize", response_model=SessionSummaryResponse)
async def session_summarize(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """根据问答历史生成结构化摘要"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = list(session.history or [])
    ai_service = ScriptAIService(project.ai_config)

    summary = await ai_service.generate_summary(
        script_type=project.script_type,
        title=project.title,
        concept=project.concept,
        history=history,
    )

    session.summary = summary
    await db.commit()

    return summary
```

### Drama Schema

**新增 SessionSummaryResponse（中文键名）：**
```python
class SessionSummaryResponse(BaseModel):
    故事概要: str
    主要角色: List[str]
    核心冲突: str
    场景设定: str
    风格基调: str
```

### ScriptAIService

**新增 generate_summary 方法：**
```python
async def generate_summary(
    self,
    script_type: str,
    title: str,
    concept: str,
    history: List[dict],
) -> dict:
    """根据问答历史生成结构化摘要"""

    history_text = "\n".join([
        f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
        for m in history
    ])

    prompt = f"""根据以下对话历史，提取剧本创作的关键信息，以 JSON 格式输出。

剧本类型: {script_type}
标题: {title}
创意概念: {concept}

对话历史:
{history_text}

请输出以下 JSON 结构（不要输出其他内容，键名使用中文）:
{
  "故事概要": "一句话描述核心剧情",
  "主要角色": ["角色1名称及简介", "角色2名称及简介"],
  "核心冲突": "核心冲突描述",
  "场景设定": "主要场景设定",
  "风格基调": "风格基调（如悬疑、温情、喜剧等）"
}"""

    response = await self._call_ai(prompt)

    # 解析 JSON
    json_str = response.strip()
    start = json_str.find('{')
    end = json_str.rfind('}')
    if start != -1 and end != -1:
        json_str = json_str[start:end+1]

    return json.loads(json_str)
```

**注意：输出 JSON 使用中文键名，前端展示时直接使用。**

---

## 数据库迁移

```sql
ALTER TABLE script_session ADD COLUMN summary JSONB NULL;
```

---

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `frontend/src/components/drama/WizardChat.vue` | 移除 action-bar，新增 emit |
| `frontend/src/views/DramaWizardView.vue` | 新增 Step 1，修改 footer 逻辑 |
| `frontend/src/api/drama.ts` | 新增 summarizeSession API |
| `backend/app/models/script_session.py` | 新增 summary 字段 |
| `backend/app/routers/drama.py` | 新增 summarize 路由 |
| `backend/app/schemas/drama.py` | 新增 SessionSummaryResponse |
| `backend/app/services/script_ai_service.py` | 新增 generate_summary 方法 |
| `backend/alembic/versions/xxx_add_summary.py` | 数据库迁移 |

---

## 测试要点

1. 回答少于 5 个问题时，显示"还需回答 X 个问题"提示
2. 回答 5 个问题后，按钮变为可点击的"下一步"
3. 点击"下一步"后，正确跳转到信息确认页并显示摘要
4. 信息确认页点击"重新问答"返回 Step 0，再次点击"下一步"会重新生成摘要
5. 点击"生成大纲"后正确生成大纲并跳转到大纲预览（Step 2）
6. AI 返回 `"done":true` 时不再自动生成大纲，改为触发 questions-complete
7. 步骤条显示正确：当前步骤高亮，已完成步骤标记为 done
8. 无"跳过问答"功能