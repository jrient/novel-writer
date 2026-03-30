# 剧本创作问答流程优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在剧本创作 AI 问答流程中增加"信息确认"步骤，用户回答 5 个问题后点击"下一步"，后端生成结构化摘要供用户确认后再生成大纲。

**Architecture:** 扩展 Wizard 步骤从 3 步到 4 步，新增后端 summarize API 和前端信息确认页面。后端新增 ScriptSession.summary 字段存储结构化摘要。

**Tech Stack:** FastAPI + SQLAlchemy + Vue 3 + Element Plus + TypeScript

---

## 文件结构

| 文件 | 责任 | 改动类型 |
|------|------|----------|
| `backend/app/models/script_session.py` | 会话模型，存储摘要 | 修改 |
| `backend/app/schemas/drama.py` | API Schema 定义 | 修改 |
| `backend/app/services/script_ai_service.py` | AI 摘要生成逻辑 | 修改 |
| `backend/app/routers/drama.py` | summarize API 路由 | 修改 |
| `backend/alembic/versions/xxx_add_summary.py` | 数据库迁移 | 创建 |
| `frontend/src/api/drama.ts` | 前端 API 调用 | 修改 |
| `frontend/src/components/drama/WizardChat.vue` | 聊天组件，emit 事件 | 修改 |
| `frontend/src/views/DramaWizardView.vue` | Wizard 主页面 | 修改 |

---

## Task 1: 后端模型新增 summary 字段

**Files:**
- Modify: `backend/app/models/script_session.py:45`

- [ ] **Step 1: 在 ScriptSession 模型中添加 summary 字段**

在 `outline_draft` 字段后添加：

```python
    # AI 汇总的结构化信息
    summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="AI汇总的结构化信息"
    )
```

- [ ] **Step 2: 验证模型语法正确**

运行: `cd backend && python -c "from app.models.script_session import ScriptSession; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/script_session.py
git commit -m "feat(drama): add summary field to ScriptSession model"
```

---

## Task 2: 后端 Schema 新增 SessionSummaryResponse

**Files:**
- Modify: `backend/app/schemas/drama.py:167`

- [ ] **Step 1: 在 ScriptSessionResponse 后添加 SessionSummaryResponse**

在 `ScriptSessionResponse` 类后添加：

```python
class SessionSummaryResponse(BaseModel):
    """会话摘要响应（中文键名）"""
    故事概要: str
    主要角色: List[str]
    核心冲突: str
    场景设定: str
    风格基调: str
```

同时在顶部 import 区域确认已有 `List` 导入（已存在）。

- [ ] **Step 2: 验证 Schema 语法正确**

运行: `cd backend && python -c "from app.schemas.drama import SessionSummaryResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/drama.py
git commit -m "feat(drama): add SessionSummaryResponse schema"
```

---

## Task 3: AI Service 新增 generate_summary 方法

**Files:**
- Modify: `backend/app/services/script_ai_service.py:535`

- [ ] **Step 1: 在 ScriptAIService 类末尾添加 generate_summary 方法**

在 `global_directive` 方法后添加：

```python
    async def generate_summary(
        self,
        script_type: str,
        title: str,
        concept: Optional[str],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """根据问答历史生成结构化摘要"""

        history_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'AI'}: {m.get('content', '')}"
            for m in history
        ])

        prompt = f"""根据以下对话历史，提取剧本创作的关键信息，以 JSON 格式输出。

剧本类型: {script_type}
标题: {title}
创意概念: {concept or '（未提供）'}

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

        messages = self._build_messages(prompt, None)
        full_response = ""
        async for chunk in self._stream(messages):
            full_response += chunk

        # 解析 JSON
        json_str = full_response.strip()
        start = json_str.find('{')
        end = json_str.rfind('}')
        if start != -1 and end != -1:
            json_str = json_str[start:end+1]

        return json.loads(json_str)
```

- [ ] **Step 2: 验证方法语法正确**

运行: `cd backend && python -c "from app.services.script_ai_service import ScriptAIService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/script_ai_service.py
git commit -m "feat(drama): add generate_summary method to ScriptAIService"
```

---

## Task 4: Drama Router 新增 summarize 路由

**Files:**
- Modify: `backend/app/routers/drama.py`

- [ ] **Step 1: 在 imports 区域添加 SessionSummaryResponse 导入**

在 `from app.schemas.drama import (` 的导入列表中添加 `SessionSummaryResponse`：

```python
from app.schemas.drama import (
    DYNAMIC_NODE_TYPES,
    EXPLANATORY_NODE_TYPES,
    ExpandNodeRequest,
    GlobalDirectiveRequest,
    ReorderRequest,
    RewriteRequest,
    ScriptNodeCreate,
    ScriptNodeResponse,
    ScriptNodeUpdate,
    ScriptProjectCreate,
    ScriptProjectListResponse,
    ScriptProjectResponse,
    ScriptProjectUpdate,
    ScriptSessionResponse,
    SessionAnswerRequest,
    SessionSummaryResponse,  # 新增
)
```

- [ ] **Step 2: 在 session_skip 路由后添加 session_summarize 路由**

在 `@router.post("/{id}/session/skip")` 路由后（约 line 472）添加：

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

- [ ] **Step 3: 验证路由语法正确**

运行: `cd backend && python -c "from app.routers.drama import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/drama.py
git commit -m "feat(drama): add session summarize API endpoint"
```

---

## Task 5: 数据库迁移

**Files:**
- Create: `backend/alembic/versions/xxx_add_summary_to_script_session.py`

- [ ] **Step 1: 生成迁移文件**

运行: `cd backend && alembic revision --autogenerate -m "add summary to script_session"`
Expected: 生成新迁移文件

- [ ] **Step 2: 检查迁移文件内容**

确认迁移文件包含 `op.add_column('script_sessions', sa.Column('summary', sa.JSON(), nullable=True))`

- [ ] **Step 3: 执行迁移（如数据库可用）**

运行: `cd backend && alembic upgrade head`
Expected: 迁移成功

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(drama): add alembic migration for summary field"
```

---

## Task 6: 前端 API 新增 summarizeSession

**Files:**
- Modify: `frontend/src/api/drama.ts`

- [ ] **Step 1: 添加 SessionSummary 接口定义**

在文件末尾添加：

```typescript
export interface SessionSummary {
  故事概要: string
  主要角色: string[]
  核心冲突: string
  场景设定: string
  风格基调: string
}
```

- [ ] **Step 2: 添加 summarizeSession 函数**

在文件末尾添加：

```typescript
export async function summarizeSession(projectId: number): Promise<SessionSummary> {
  const res = await apiClient.post(`/api/v1/drama/${projectId}/session/summarize`)
  return res.data
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

运行: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 无错误或只有与本文件无关的错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/drama.ts
git commit -m "feat(drama): add summarizeSession API"
```

---

## Task 7: WizardChat.vue 移除 action-bar 并新增 emit

**Files:**
- Modify: `frontend/src/components/drama/WizardChat.vue`

- [ ] **Step 1: 移除底部 action-bar 区域**

删除 `<!-- 底部操作栏 -->` 整个区域（约 line 93-104）：

```vue
    <!-- 底部操作栏 -->
    <div class="action-bar" v-if="!isStreaming && questionCount >= 1">
      <el-button
        type="success"
        plain
        @click="startGenerateOutline"
        class="generate-btn"
      >
        信息已足够，开始生成大纲
      </el-button>
      <span class="question-hint">已回答 {{ questionCount }} 个问题</span>
    </div>
```

同时删除对应的 CSS 样式 `.action-bar`, `.generate-btn`, `.question-hint`。

- [ ] **Step 2: 新增 emit 定义**

在 `const emit = defineEmits<{` 中添加：

```typescript
const emit = defineEmits<{
  (e: 'outline-ready'): void
  (e: 'questions-complete'): void  // 新增：回答完成 5 个问题
}>()
```

- [ ] **Step 3: 在 questionCount 达到 5 时触发 emit**

在 `sendMessage` 函数中，`questionCount.value++` 后添加检查：

```typescript
  questionCount.value++
  if (questionCount.value >= MAX_QUESTIONS) {
    emit('questions-complete')
  }
```

- [ ] **Step 4: 修改 AI 返回 done:true 的处理逻辑**

在 `sendMessage` 的回调中，找到处理 `"done":true` 的逻辑（约 line 204-207），修改为：

```typescript
      if (finalText.includes('"done":true') || finalText === '__done__') {
        // AI 认为问答完成，触发 questions-complete
        emit('questions-complete')
      } else {
        addAiMessage(finalText)
        await scrollToBottom()
      }
```

删除原来的 `await generateOutline()` 调用。

- [ ] **Step 5: 移除 startGenerateOutline 函数**

删除 `startGenerateOutline` 函数（约 line 220-228），因为不再需要。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/drama/WizardChat.vue
git commit -m "feat(drama): remove action-bar and add questions-complete emit"
```

---

## Task 8: DramaWizardView.vue 新增信息确认步骤

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 扩展 wizardSteps 为 4 步**

修改 `wizardSteps` 定义：

```typescript
const wizardSteps = [
  { title: 'AI 问答' },    // Step 0
  { title: '信息确认' },   // Step 1（新增）
  { title: '大纲预览' },   // Step 2（原 Step 1）
  { title: '开始创作' },   // Step 3（原 Step 2）
]
```

- [ ] **Step 2: 导入 summarizeSession API**

在 imports 区域添加：

```typescript
import { skipToOutline, summarizeSession } from '@/api/drama'
import type { SessionSummary } from '@/api/drama'
```

- [ ] **Step 3: 新增状态变量**

在 `const confirming = ref(false)` 后添加：

```typescript
const summarizing = ref(false)
const sessionSummary = ref<SessionSummary | null>(null)
const generatingOutline = ref(false)
```

- [ ] **Step 4: 新增 handleQuestionsComplete 处理函数**

添加处理 WizardChat emit 的函数：

```typescript
function handleQuestionsComplete() {
  // 子组件通知问答完成，footer 按钮会自动变化
}
```

- [ ] **Step 5: 新增 handleNextStep 函数**

```typescript
async function handleNextStep() {
  summarizing.value = true
  try {
    const summary = await summarizeSession(projectId.value)
    sessionSummary.value = summary
    wizardStepIndex.value = 1
  } catch {
    ElMessage.error('汇总信息失败')
  } finally {
    summarizing.value = false
  }
}
```

- [ ] **Step 6: 新增 handleBackToChat 函数**

```typescript
function handleBackToChat() {
  sessionSummary.value = null
  wizardStepIndex.value = 0
}
```

- [ ] **Step 7: 新增 handleGenerateOutline 函数**

```typescript
async function handleGenerateOutline() {
  generatingOutline.value = true
  isStreaming.value = true  // 复用现有状态
  streamingText.value = ''

  try {
    // 调用生成大纲（复用现有逻辑）
    await dramaStore.generateOutline(projectId.value)
    wizardStepIndex.value = 2
  } catch {
    ElMessage.error('生成大纲失败')
  } finally {
    generatingOutline.value = false
    isStreaming.value = false
  }
}
```

注意：需要检查 dramaStore 是否有 generateOutline 方法，或直接调用 API。

- [ ] **Step 8: 修改 Step 0 的 footer**

替换原有的 footer 区域：

```vue
      <template v-if="wizardStepIndex === 0">
        <div class="chat-container">
          <WizardChat
            v-if="!pageLoading"
            :project-id="projectId"
            :session="dramaStore.session"
            @outline-ready="handleOutlineReady"
            @questions-complete="handleQuestionsComplete"
          />
          <div v-else class="loading-area">
            <el-skeleton :rows="5" animated />
          </div>
        </div>

        <div class="wizard-footer">
          <span v-if="questionCount < 5" class="hint-text">
            还需回答 {{ 5 - questionCount }} 个问题才能继续
          </span>
          <el-button
            v-else
            type="primary"
            size="large"
            :loading="summarizing"
            @click="handleNextStep"
            round
          >
            下一步
          </el-button>
        </div>
      </template>
```

需要新增 `questionCount` 变量，从 WizardChat 通过 emit 同步（或通过 props 传递）。

- [ ] **Step 9: 新增 Step 1 信息确认页模板**

在 Step 0 template 后添加：

```vue
      <!-- Step 1: 信息确认 -->
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

- [ ] **Step 10: 修改 Step 2 (原 Step 1) 大纲预览的索引**

确保大纲预览的 template 条件改为 `wizardStepIndex === 2`：

```vue
      <!-- Step 2: 大纲预览 -->
      <template v-else-if="wizardStepIndex === 2">
```

- [ ] **Step 11: 添加 CSS 样式**

在 `<style scoped>` 区域添加：

```css
/* 信息确认页 */
.summary-review {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 32px;
}

.summary-header {
  text-align: center;
}

.summary-header h3 {
  font-size: 22px;
  font-weight: 700;
  color: #2C2C2C;
  margin: 0 0 6px;
  font-family: 'Noto Serif SC', serif;
}

.summary-header p {
  font-size: 13px;
  color: #7A7A7A;
  margin: 0;
}

.summary-card {
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 16px;
  padding: 24px;
}

.summary-section {
  margin-bottom: 16px;
}

.summary-section:last-child {
  margin-bottom: 0;
}

.summary-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #6B7B8D;
  margin: 0 0 8px;
}

.summary-section p,
.summary-section ul {
  font-size: 15px;
  color: #2C2C2C;
  margin: 0;
  line-height: 1.6;
}

.summary-section ul {
  padding-left: 20px;
}

.summary-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.hint-text {
  font-size: 14px;
  color: #9E9E9E;
}
```

- [ ] **Step 12: 移除 handleSkip 函数和相关按钮**

删除 `handleSkip` 函数和"跳过问答"相关逻辑。

- [ ] **Step 13: 同步 questionCount 状态**

需要在 WizardChat 和父组件间同步 questionCount。方案：让 WizardChat emit 一个 `update:questionCount` 事件：

在 WizardChat.vue 中添加：
```typescript
emit('update:questionCount', questionCount.value)
```

在 DramaWizardView.vue 中：
```typescript
const questionCount = ref(0)

function handleQuestionsComplete() {
  // 可选处理
}

// 在 WizardChat 组件上添加:
@update:questionCount="(count) => questionCount = count"
```

或者更简单：通过 props 传递 questionCount 给 WizardChat，让父组件管理。

- [ ] **Step 14: 验证 Vue 编译**

运行: `cd frontend && npm run build 2>&1 | head -30`
Expected: 编译成功或有可解决的错误

- [ ] **Step 15: Commit**

```bash
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): add Step 1 info confirmation and update wizard flow"
```

---

## Task 9: 集成测试

- [ ] **Step 1: 启动后端服务**

运行: `cd backend && uvicorn app.main:app --reload`

- [ ] **Step 2: 启动前端服务**

运行: `cd frontend && npm run dev`

- [ ] **Step 3: 测试完整流程**

1. 创建新剧本项目
2. 进入 Wizard 页面
3. 回答 AI 问题，观察 footer 变化
4. 回答 5 个问题后，点击"下一步"
5. 确认信息确认页显示摘要
6. 点击"重新问答"返回
7. 再次点击"下一步"，确认重新生成摘要
8. 点击"生成大纲"，确认跳转到大纲预览
9. 确认步骤条显示正确

---

## 完成检查

- [ ] 所有 8 个文件的改动已提交
- [ ] 后端 API 可正常调用
- [ ] 前端流程正确运行
- [ ] 步骤条显示正确
- [ ] 无"跳过问答"功能