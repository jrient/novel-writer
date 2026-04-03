# 剧本设定侧边栏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为剧本创作工作台新增可滑入的设定抽屉，管理人物/世界观/风格/剧情/AI指令，所有设定在每次 AI 调用时自动注入 system prompt。

**Architecture:** 数据存储在已有的 `script_projects.metadata_["settings"]` JSON 字段，无需数据库迁移。后端新增 `PUT /settings` 端点 + 修改 `ScriptAIService` 接受 `project_settings` 参数。前端新增 `ScriptSettingsDrawer.vue` 和 `CharacterEditOverlay.vue` 两个组件。

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 / Vue 3 + TypeScript + Element Plus + Pinia

**Spec:** `docs/superpowers/specs/2026-04-03-script-settings-sidebar-design.md`

---

## File Map

### 新增文件
- `frontend/src/components/drama/ScriptSettingsDrawer.vue` — 设定抽屉主体
- `frontend/src/components/drama/CharacterEditOverlay.vue` — 角色编辑浮层
- `backend/tests/test_drama_settings.py` — 后端 settings schema 单元测试

### 修改文件
- `backend/app/services/script_ai_service.py` — `ScriptAIService.__init__` 增加 `project_settings` 参数；新增 `_build_settings_context()` 方法；替换 `_get_system_prompt()` 方法体以在 system prompt 头部注入设定
- `backend/app/routers/drama.py` — 新增 `ProjectSettingsUpdate` schema + `PUT /{id}/settings` 端点；6 个 AI 端点传入 `project_settings`；补充 `Field` 导入
- `backend/tests/test_drama_ai_service.py` — 追加 `_build_settings_context` 单元测试（文件已存在）
- `frontend/src/api/drama.ts` — 新增 `ProjectSettings` 类型 + `updateProjectSettings()` 函数
- `frontend/src/stores/drama.ts` — 新增 `projectSettings` computed + `updateProjectSettings()` action；补充 `computed` 导入
- `frontend/src/views/DramaWorkbenchView.vue` — 工具栏增加「⚙ 设定」按钮；挂载两个新组件（`Setting` icon 已存在，无需重复导入）

---

## Task 1: 后端 ScriptAIService 增加 project_settings 注入

**Files:**
- Modify: `backend/app/services/script_ai_service.py`
- Modify: `backend/tests/test_drama_ai_service.py` (已存在，追加测试)

- [ ] **Step 1: 追加失败测试到已有测试文件**

在 `backend/tests/test_drama_ai_service.py` **末尾**追加（文件已存在，有导入 `ScriptAIService`）：

```python
def test_build_settings_context_empty():
    """空 settings 返回空字符串"""
    svc = ScriptAIService(ai_config={}, project_settings={})
    assert svc._build_settings_context() == ""


def test_build_settings_context_full():
    """非空 settings 返回正确格式的上下文字符串"""
    settings_data = {
        "characters": [
            {"id": "c1", "name": "张三", "description": "豪爽"},
            {"id": "c2", "name": "李四", "description": ""},  # 空描述不追加冒号
        ],
        "world_setting": "架空古代",
        "tone": "热血",
        "plot_anchors": "主角不能死",
        "persistent_directive": "不要出现现代词汇",
    }
    svc = ScriptAIService(ai_config={}, project_settings=settings_data)
    ctx = svc._build_settings_context()
    assert "【剧本设定】" in ctx
    assert "张三：豪爽" in ctx
    assert "李四" in ctx
    assert "架空古代" in ctx
    assert "热血" in ctx
    assert "主角不能死" in ctx
    assert "不要出现现代词汇" in ctx


def test_build_settings_context_partial():
    """只填了部分字段，不注入空字段"""
    svc = ScriptAIService(ai_config={}, project_settings={"tone": "悬疑"})
    ctx = svc._build_settings_context()
    assert "悬疑" in ctx
    assert "世界观" not in ctx
    assert "人物" not in ctx


def test_settings_prepended_to_system_prompt():
    """project_settings 内容出现在 system prompt 的最前面"""
    svc = ScriptAIService(
        ai_config={},
        project_settings={"persistent_directive": "保持角色一致性"},
    )
    system = svc._get_system_prompt("question", "dynamic")
    assert system is not None
    assert system.startswith("【剧本设定】")
    assert "保持角色一致性" in system


def test_empty_settings_does_not_modify_system_prompt():
    """空 settings 不影响原有 system prompt"""
    svc_with = ScriptAIService(ai_config={}, project_settings={})
    svc_without = ScriptAIService(ai_config={})
    assert svc_with._get_system_prompt("question", "dynamic") == \
           svc_without._get_system_prompt("question", "dynamic")
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_ai_service.py -k "test_build_settings or test_settings_prepended or test_empty_settings" -v 2>&1 | tail -20
```

期望：`AttributeError: 'ScriptAIService' object has no attribute '_build_settings_context'`

- [ ] **Step 3: 实现 ScriptAIService 修改**

**3a. 修改 `__init__`** — 在 `script_ai_service.py` line 292 找到 `def __init__`，增加 `project_settings` 参数：

```python
def __init__(
    self,
    ai_config: Optional[Dict[str, Any]] = None,
    project_settings: Optional[Dict[str, Any]] = None,  # 新增
):
    self.ai_config = ai_config or {}
    self.project_settings = project_settings or {}       # 新增
    self.provider = self.ai_config.get("provider") or settings.DEFAULT_AI_PROVIDER
    self.model = self._resolve_model()
    self.temperature = self._resolve_temperature()
    self.max_tokens = self._resolve_max_tokens()
    self.custom_prompts: Dict[str, Any] = self.ai_config.get("prompt_config") or {}
```

**3b. 新增 `_build_settings_context` 方法** — 在 `_get_system_prompt` 方法之前插入：

```python
def _build_settings_context(self) -> str:
    """将非空设定字段构建为可注入 system prompt 的字符串"""
    s = self.project_settings
    lines = ["【剧本设定】"]
    chars = s.get("characters", [])
    if chars:
        lines.append("人物：")
        for c in chars:
            desc = c.get("description") or ""
            if desc:
                lines.append(f"  - {c['name']}：{desc}")
            else:
                lines.append(f"  - {c['name']}")
    if s.get("world_setting"):
        lines.append(f"世界观：{s['world_setting']}")
    if s.get("tone"):
        lines.append(f"风格基调：{s['tone']}")
    if s.get("plot_anchors"):
        lines.append(f"核心要素：{s['plot_anchors']}")
    if s.get("persistent_directive"):
        lines.append(f"持久指令：{s['persistent_directive']}")
    return "\n".join(lines) if len(lines) > 1 else ""
```

**3c. 替换整个 `_get_system_prompt` 方法体** — 原方法有 early return，需改为先收集 `base` 再注入 settings context：

```python
def _get_system_prompt(self, key: str, script_type: str) -> Optional[str]:
    """获取系统提示词：优先使用用户自定义，否则用默认；前置注入 project_settings"""
    if isinstance(self.custom_prompts, dict):
        custom = self.custom_prompts.get("system_prompt")
        if custom:
            base: Optional[str] = custom
        else:
            prompts = _get_prompts(script_type)
            prompt_entry = prompts.get(key, {})
            base = prompt_entry.get("system") if isinstance(prompt_entry, dict) else None
    else:
        prompts = _get_prompts(script_type)
        prompt_entry = prompts.get(key, {})
        base = prompt_entry.get("system") if isinstance(prompt_entry, dict) else None

    settings_ctx = self._build_settings_context()
    if not settings_ctx:
        return base
    if base:
        return f"{settings_ctx}\n\n{base}"
    return settings_ctx
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_ai_service.py -v 2>&1 | tail -30
```

期望：所有测试（含原有测试）通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/script_ai_service.py backend/tests/test_drama_ai_service.py
git commit -m "feat(drama): add project_settings injection to ScriptAIService

ScriptAIService now accepts project_settings dict and prepends
non-empty settings to system prompts via _build_settings_context().
Empty settings leave existing prompts unchanged.

Scope-risk: narrow"
```

---

## Task 2: 后端 drama.py — 6 个 AI 端点传入 project_settings

**Files:**
- Modify: `backend/app/routers/drama.py` (lines ~463, ~532, ~597, ~715, ~920, ~957)

- [ ] **Step 1: 找到所有需修改的 ScriptAIService 调用行**

```bash
grep -n "ScriptAIService(project.ai_config)" /data/project/novel-writer/backend/app/routers/drama.py
```

期望输出 7 行（含 global-directive 那行保持不变）。

- [ ] **Step 2: 修改 6 个 AI 端点**

找到以下 6 处 `ai_service = ScriptAIService(project.ai_config)` 调用（排除 `global-directive` 端点），逐一替换为：

```python
_proj_settings = (project.metadata_ or {}).get("settings", {})
ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)
```

**6 处端点（约行号，以 grep 结果为准）：**
- `session/answer`（约 line 463）
- `session/summarize`（约 line 532）
- `session/generate-outline`（约 line 597）
- `session/expand-episode`（约 line 715）
- `nodes/{id}/expand`（约 line 920）
- `ai/rewrite`（约 line 957）

**不修改**：`ai/global-directive` 端点（约 line 996）保持 `ScriptAIService(project.ai_config)` 不变。

- [ ] **Step 3: 验证修改后 7 处调用的状态**

```bash
grep -n "ScriptAIService" /data/project/novel-writer/backend/app/routers/drama.py
```

期望：6 行含 `project_settings=_proj_settings`，1 行（global-directive）不含。

- [ ] **Step 4: 运行原有测试，确认无回归**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_ai_service.py tests/test_drama_schemas.py -v 2>&1 | tail -20
```

期望：全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/drama.py
git commit -m "feat(drama): pass project_settings to ScriptAIService in 6 AI endpoints

Excludes global-directive endpoint (execution-type, manages own prompt).

Scope-risk: narrow
Directive: global-directive endpoint intentionally excluded — do not add settings injection there"
```

---

## Task 3: 后端新增 PUT /settings 端点

**Files:**
- Modify: `backend/app/routers/drama.py`
- Create: `backend/tests/test_drama_settings.py`

- [ ] **Step 1: 创建 schema 单元测试文件**

```python
# backend/tests/test_drama_settings.py
"""
剧本设定 Schema 单元测试
测试 ProjectSettingsUpdate 的字段验证
"""
import pytest
from pydantic import ValidationError


def test_project_settings_valid():
    """有效的 settings 通过验证"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    s = ProjectSettingsUpdate(
        characters=[CharacterSettingItem(id="c1", name="张三", description="豪爽")],
        world_setting="架空古代",
        tone="热血",
        plot_anchors="主角不能死",
        persistent_directive="不要出现现代词汇",
    )
    assert s.tone == "热血"
    assert s.characters[0].name == "张三"


def test_project_settings_defaults():
    """所有字段均有默认值"""
    from app.routers.drama import ProjectSettingsUpdate
    s = ProjectSettingsUpdate()
    assert s.characters == []
    assert s.world_setting == ""
    assert s.tone == ""
    assert s.plot_anchors == ""
    assert s.persistent_directive == ""


def test_character_name_max_length():
    """角色名称超过 100 字符时验证失败"""
    from app.routers.drama import CharacterSettingItem
    with pytest.raises(ValidationError):
        CharacterSettingItem(id="c1", name="x" * 101, description="")


def test_character_description_max_length():
    """角色描述超过 2000 字符时验证失败"""
    from app.routers.drama import CharacterSettingItem
    with pytest.raises(ValidationError):
        CharacterSettingItem(id="c1", name="张三", description="x" * 2001)


def test_tone_max_length():
    """tone 超过 1000 字符时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(tone="x" * 1001)


def test_world_setting_max_length():
    """world_setting 超过 3000 字符时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(world_setting="x" * 3001)


def test_characters_max_count():
    """角色列表超过 50 个时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    chars = [CharacterSettingItem(id=f"c{i}", name=f"角色{i}", description="") for i in range(51)]
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(characters=chars)


def test_model_dump_roundtrip():
    """model_dump 后可以重新构造"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    s = ProjectSettingsUpdate(
        characters=[CharacterSettingItem(id="c1", name="张三", description="豪爽")],
        tone="热血",
    )
    d = s.model_dump()
    s2 = ProjectSettingsUpdate(**d)
    assert s2.tone == "热血"
    assert s2.characters[0].name == "张三"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_settings.py -v 2>&1 | tail -20
```

期望：`ImportError: cannot import name 'ProjectSettingsUpdate'`（schema 还未创建）

- [ ] **Step 3: 在 drama.py 中补充 `Field` 导入 + 新增 schema + 新增端点**

**3a. 修改 pydantic 导入**（约 line 43）：

```python
from pydantic import BaseModel, Field
```

**3b. 在现有 schema 区域末尾（约 line 100 之前）新增**：

```python
class CharacterSettingItem(BaseModel):
    id: str
    name: str = Field(..., max_length=100)
    description: str = Field("", max_length=2000)


class ProjectSettingsUpdate(BaseModel):
    characters: List[CharacterSettingItem] = Field(default_factory=list, max_length=50)
    world_setting: str = Field("", max_length=3000)
    tone: str = Field("", max_length=1000)
    plot_anchors: str = Field("", max_length=3000)
    persistent_directive: str = Field("", max_length=2000)
```

**3c. 在 `update_ai_config` 端点（约 line 263）之后新增端点**：

```python
@router.put("/{id}/settings", response_model=ScriptProjectResponse)
async def update_project_settings(
    body: ProjectSettingsUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新剧本设定（人物/世界观/风格/剧情/持久化AI指令）"""
    current_meta = dict(project.metadata_ or {})
    current_meta["settings"] = body.model_dump()
    project.metadata_ = current_meta
    await db.commit()
    await db.refresh(project)
    return project
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_settings.py -v 2>&1 | tail -20
```

期望：所有测试通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/drama.py backend/tests/test_drama_settings.py
git commit -m "feat(drama): add PUT /{id}/settings endpoint with Pydantic validation

Stores characters/world_setting/tone/plot_anchors/persistent_directive
in metadata_['settings'] without overwriting other metadata fields.
Field limits: name≤100, description≤2000, world/plot≤3000, tone≤1000.

Scope-risk: narrow"
```

---

## Task 4: 前端 API + Store 增加 settings 支持

**Files:**
- Modify: `frontend/src/api/drama.ts`
- Modify: `frontend/src/stores/drama.ts`

- [ ] **Step 1: 在 `frontend/src/api/drama.ts` 中新增类型和函数**

在文件顶部 Types 区域（`AIConfig` interface 之后，约 line 23）新增：

```typescript
export interface CharacterSetting {
  id: string
  name: string
  description: string
}

export interface ProjectSettings {
  characters: CharacterSetting[]
  world_setting: string
  tone: string
  plot_anchors: string
  persistent_directive: string
}

export const defaultProjectSettings: ProjectSettings = {
  characters: [],
  world_setting: '',
  tone: '',
  plot_anchors: '',
  persistent_directive: '',
}
```

在 `updateAIConfig` 函数（约 line 158）之后新增：

```typescript
export async function updateProjectSettings(id: number, data: ProjectSettings): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}/settings`, data)
}
```

- [ ] **Step 2: 修改 `frontend/src/stores/drama.ts`**

**2a. 修改 vue import**（第 5 行）：

```typescript
import { ref, computed } from 'vue'
```

**2b. 在 API import 中新增**：

```typescript
import {
  // ... 原有 imports 保持不变 ...
  updateProjectSettings as apiUpdateProjectSettings,
} from '@/api/drama'
import type {
  // ... 原有 type imports 保持不变 ...
  ProjectSettings,
} from '@/api/drama'
import { defaultProjectSettings } from '@/api/drama'
```

**2c. 在 `const loading = ref(false)` 之后新增**：

```typescript
// Settings — derived from currentProject.metadata_["settings"]
const projectSettings = computed<ProjectSettings>(() => {
  const meta = currentProject.value?.metadata_
  if (meta && typeof meta === 'object' && 'settings' in meta) {
    return meta.settings as ProjectSettings
  }
  return { ...defaultProjectSettings }
})

async function updateProjectSettings(id: number, settings: ProjectSettings) {
  const updated = await apiUpdateProjectSettings(id, settings)
  if (currentProject.value?.id === id) {
    currentProject.value = updated
  }
  return updated
}
```

**2d. 在 `return` 语句中新增** `projectSettings` 和 `updateProjectSettings`：

```typescript
return {
  projects,
  currentProject,
  nodes,
  currentNode,
  session,
  loading,
  projectSettings,        // 新增
  fetchProjects,
  fetchProject,
  createProject,
  updateProject,
  removeProject,
  updateProjectAIConfig,
  updateProjectSettings,  // 新增
  fetchNodes,
  addNode,
  editNode,
  removeNode,
  reorder,
  selectNode,
  fetchSession,
  resetSession,
  confirmProjectOutline,
}
```

- [ ] **Step 3: 验证类型编译**

```bash
cd /data/project/novel-writer/frontend
npx tsc --noEmit 2>&1 | head -30
```

期望：无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/drama.ts frontend/src/stores/drama.ts
git commit -m "feat(drama): add ProjectSettings types, API function and store computed+action"
```

---

## Task 5: 新建 ScriptSettingsDrawer.vue

**Files:**
- Create: `frontend/src/components/drama/ScriptSettingsDrawer.vue`

- [ ] **Step 1: 创建组件文件**

```vue
<!-- frontend/src/components/drama/ScriptSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    direction="rtl"
    :modal="false"
    :size="360"
    :with-header="false"
    class="settings-drawer"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="drawer-inner">
      <!-- Header -->
      <div class="drawer-header">
        <span class="drawer-title">⚙ 剧本设定</span>
        <span class="save-status">
          <span v-if="saving" class="status-saving">保存中...</span>
          <span v-else-if="savedAt" class="status-saved">已保存 ✓</span>
        </span>
        <el-button text :icon="Close" @click="$emit('update:visible', false)" />
      </div>

      <!-- Collapse panels -->
      <el-collapse v-model="activeNames" class="settings-collapse">

        <!-- 人物设定 -->
        <el-collapse-item name="characters">
          <template #title><span class="panel-title">👤 人物设定</span></template>
          <div class="character-list">
            <div
              v-for="char in localSettings.characters"
              :key="char.id"
              class="character-card"
            >
              <span class="char-name">{{ char.name || '未命名角色' }}</span>
              <el-button text size="small" @click="openCharacterEdit(char)">编辑</el-button>
              <el-button text size="small" type="danger" @click="removeCharacter(char.id)">删除</el-button>
            </div>
            <el-button text size="small" class="add-char-btn" @click="addCharacter">
              + 添加角色
            </el-button>
          </div>
        </el-collapse-item>

        <!-- 世界观 / 背景 -->
        <el-collapse-item name="world">
          <template #title><span class="panel-title">🌍 世界观 / 背景</span></template>
          <el-input
            v-model="localSettings.world_setting"
            type="textarea"
            :rows="4"
            :maxlength="3000"
            show-word-limit
            placeholder="描述故事发生的时代、地点、世界背景..."
            @input="scheduleSave"
          />
        </el-collapse-item>

        <!-- 风格 / 基调 -->
        <el-collapse-item name="tone">
          <template #title><span class="panel-title">🎭 风格 / 基调</span></template>
          <el-input
            v-model="localSettings.tone"
            type="textarea"
            :rows="3"
            :maxlength="1000"
            show-word-limit
            placeholder="剧本整体风格、语气、节奏偏好..."
            @input="scheduleSave"
          />
        </el-collapse-item>

        <!-- 核心剧情要素 -->
        <el-collapse-item name="plot">
          <template #title><span class="panel-title">📌 核心剧情要素</span></template>
          <el-input
            v-model="localSettings.plot_anchors"
            type="textarea"
            :rows="4"
            :maxlength="3000"
            show-word-limit
            placeholder="主线冲突、关键伏笔、不可改变的剧情锚点..."
            @input="scheduleSave"
          />
        </el-collapse-item>

        <!-- 持久化 AI 指令 -->
        <el-collapse-item name="directive">
          <template #title><span class="panel-title">⚡ 持久化 AI 指令</span></template>
          <el-input
            v-model="localSettings.persistent_directive"
            type="textarea"
            :rows="4"
            :maxlength="2000"
            show-word-limit
            placeholder="每次 AI 生成时自动注入的指令（区别于全局指令的按需执行）..."
            @input="scheduleSave"
          />
        </el-collapse-item>

      </el-collapse>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import type { ProjectSettings, CharacterSetting } from '@/api/drama'
import { defaultProjectSettings } from '@/api/drama'

const props = defineProps<{
  visible: boolean
  settings: ProjectSettings
  projectId: number
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'edit-character': [char: CharacterSetting]
  'save': [settings: ProjectSettings]
}>()

const activeNames = ref(['characters', 'world', 'tone', 'plot', 'directive'])
const saving = ref(false)
const savedAt = ref<Date | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const localSettings = ref<ProjectSettings>({ ...defaultProjectSettings })

watch(
  () => props.settings,
  (val) => {
    localSettings.value = {
      ...defaultProjectSettings,
      ...val,
      characters: val.characters ? [...val.characters] : [],
    }
  },
  { immediate: true, deep: true },
)

function scheduleSave() {
  saving.value = true          // 防抖等待期间显示"保存中..."
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('save', { ...localSettings.value })
    saving.value = false
    savedAt.value = new Date() // 乐观更新：emit 触发后即视为已保存
  }, 500)
}

function openCharacterEdit(char: CharacterSetting) {
  emit('edit-character', char)
}

function addCharacter() {
  const newChar: CharacterSetting = {
    id: crypto.randomUUID(),
    name: '',
    description: '',
  }
  localSettings.value.characters = [...localSettings.value.characters, newChar]
  emit('edit-character', newChar)
}

function removeCharacter(id: string) {
  localSettings.value.characters = localSettings.value.characters.filter(c => c.id !== id)
  scheduleSave()
}

function saveNow() {
  if (debounceTimer) clearTimeout(debounceTimer)
  emit('save', { ...localSettings.value })
  savedAt.value = new Date()
}

function updateCharacter(updated: CharacterSetting) {
  const idx = localSettings.value.characters.findIndex(c => c.id === updated.id)
  if (idx !== -1) {
    localSettings.value.characters[idx] = { ...updated }
  } else {
    localSettings.value.characters.push({ ...updated })
  }
  saveNow()
}

defineExpose({ saveNow, updateCharacter })
</script>

<style scoped>
.settings-drawer :deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.drawer-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #E0DFDC;
  background: white;
  flex-shrink: 0;
}

.drawer-title {
  font-size: 14px;
  font-weight: 600;
  color: #2C2C2C;
  flex: 1;
}

.save-status { font-size: 12px; }
.status-saving { color: #9E9E9E; }
.status-saved { color: #67C23A; }

.settings-collapse {
  flex: 1;
  overflow-y: auto;
  border-top: none;
}

.settings-collapse :deep(.el-collapse-item__header) {
  padding: 0 16px;
  font-size: 13px;
  font-weight: 500;
}

.settings-collapse :deep(.el-collapse-item__content) {
  padding: 8px 16px 16px;
}

.panel-title { font-size: 13px; }

.character-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.character-card {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: #F7F6F3;
  border-radius: 6px;
  border: 1px solid #E0DFDC;
}

.char-name {
  flex: 1;
  font-size: 13px;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-char-btn {
  color: #6B7B8D !important;
  margin-top: 4px;
}
</style>
```

- [ ] **Step 2: 验证类型编译**

```bash
cd /data/project/novel-writer/frontend
npx tsc --noEmit 2>&1 | grep -i "ScriptSettingsDrawer\|error" | head -20
```

期望：无类型错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drama/ScriptSettingsDrawer.vue
git commit -m "feat(drama): add ScriptSettingsDrawer component

5-section collapsible drawer with 500ms debounced auto-save and save status indicator."
```

---

## Task 6: 新建 CharacterEditOverlay.vue

**Files:**
- Create: `frontend/src/components/drama/CharacterEditOverlay.vue`

- [ ] **Step 1: 创建组件文件**

```vue
<!-- frontend/src/components/drama/CharacterEditOverlay.vue -->
<template>
  <teleport to="body">
    <transition name="overlay-fade">
      <div v-if="visible" class="char-overlay-backdrop" @click.self="handleCancel">
        <div
          class="char-overlay-card"
          ref="cardRef"
          tabindex="-1"
          @keydown.esc="handleCancel"
          @keydown.ctrl.enter="handleSave"
        >
          <div class="overlay-header">
            <span class="overlay-title">{{ isNew ? '添加角色' : '编辑角色' }}</span>
            <el-button text :icon="Close" @click="handleCancel" />
          </div>

          <div class="overlay-body">
            <div class="field-group">
              <label class="field-label">角色名称</label>
              <el-input
                v-model="draft.name"
                placeholder="输入角色姓名..."
                maxlength="100"
                ref="nameInputRef"
              />
            </div>
            <div class="field-group">
              <label class="field-label">角色描述</label>
              <el-input
                v-model="draft.description"
                type="textarea"
                :rows="6"
                maxlength="2000"
                show-word-limit
                placeholder="描述角色性格、背景、说话风格等，AI 生成时会参考这些信息..."
              />
            </div>
          </div>

          <div class="overlay-footer">
            <span class="shortcut-hint">Ctrl+Enter 保存 · Esc 取消</span>
            <div class="footer-actions">
              <el-button @click="handleCancel">取消</el-button>
              <el-button type="primary" @click="handleSave" :disabled="!draft.name.trim()">保存</el-button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import type { CharacterSetting } from '@/api/drama'

const props = defineProps<{
  visible: boolean
  character: CharacterSetting | null
}>()

const emit = defineEmits<{
  'save': [character: CharacterSetting]
  'cancel': []
}>()

const cardRef = ref<HTMLElement | null>(null)
const nameInputRef = ref<{ focus: () => void } | null>(null)
const draft = ref<CharacterSetting>({ id: '', name: '', description: '' })
const isNew = ref(false)

watch(
  () => props.character,
  (char) => {
    if (char) {
      draft.value = { ...char }
      isNew.value = !char.name
    }
  },
  { immediate: true },
)

watch(
  () => props.visible,
  async (val) => {
    if (val) {
      await nextTick()
      cardRef.value?.focus()
      nameInputRef.value?.focus()
    }
  },
)

function handleSave() {
  if (!draft.value.name.trim()) return
  emit('save', { ...draft.value, name: draft.value.name.trim() })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.char-overlay-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.char-overlay-card {
  background: white;
  border-radius: 10px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.18);
  width: 480px;
  max-width: 90vw;
  outline: none;
}

.overlay-header {
  display: flex;
  align-items: center;
  padding: 16px 20px 12px;
  border-bottom: 1px solid #E0DFDC;
}

.overlay-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
}

.overlay-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
}

.overlay-footer {
  display: flex;
  align-items: center;
  padding: 12px 20px 16px;
  border-top: 1px solid #E0DFDC;
}

.shortcut-hint {
  flex: 1;
  font-size: 11px;
  color: #BDBDBD;
}

.footer-actions {
  display: flex;
  gap: 8px;
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.15s ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
```

- [ ] **Step 2: 验证类型编译**

```bash
cd /data/project/novel-writer/frontend
npx tsc --noEmit 2>&1 | grep -i "CharacterEditOverlay\|error" | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drama/CharacterEditOverlay.vue
git commit -m "feat(drama): add CharacterEditOverlay component

Teleport-based modal for editing character name + description.
Supports Esc to cancel and Ctrl+Enter to save. Auto-focuses name input on open."
```

---

## Task 7: 更新 DramaWorkbenchView.vue 串联一切

**Files:**
- Modify: `frontend/src/views/DramaWorkbenchView.vue`

注意：`Setting` icon 在 DramaWorkbenchView.vue line 167 已导入（`AI 配置`按钮使用），无需重复添加。

- [ ] **Step 1: 在工具栏 `header-right` 中添加「⚙ 设定」按钮**

在现有「全局指令」按钮之前插入（约 line 21）：

```html
<el-button
  size="small"
  class="toolbar-btn"
  :class="{ 'toolbar-btn--active': showSettingsDrawer }"
  @click="showSettingsDrawer = !showSettingsDrawer"
>
  <el-icon><Setting /></el-icon>
  设定
</el-button>
```

- [ ] **Step 2: 在 Dialogs 区域挂载两个新组件**

在 `<AiConfigPanel ... />` 之后（约 line 129）添加：

```html
<!-- Settings Drawer -->
<ScriptSettingsDrawer
  v-model:visible="showSettingsDrawer"
  :settings="dramaStore.projectSettings"
  :project-id="projectId"
  ref="settingsDrawerRef"
  @save="handleSaveSettings"
  @edit-character="handleEditCharacter"
/>

<!-- Character Edit Overlay -->
<CharacterEditOverlay
  :visible="showCharacterOverlay"
  :character="editingCharacter"
  @save="handleCharacterSave"
  @cancel="showCharacterOverlay = false"
/>
```

- [ ] **Step 3: 在 `<script setup>` 中新增 imports、refs 和 handlers**

**新增 imports**（在现有 component imports 之后）：

```typescript
import ScriptSettingsDrawer from '@/components/drama/ScriptSettingsDrawer.vue'
import CharacterEditOverlay from '@/components/drama/CharacterEditOverlay.vue'
import type { CharacterSetting, ProjectSettings } from '@/api/drama'
```

**新增 refs 和 handlers**（在 `showAiConfig` ref 之后）：

```typescript
// Settings drawer state
const showSettingsDrawer = ref(false)
const showCharacterOverlay = ref(false)
const editingCharacter = ref<CharacterSetting | null>(null)
const settingsDrawerRef = ref<InstanceType<typeof ScriptSettingsDrawer> | null>(null)

async function handleSaveSettings(settings: ProjectSettings) {
  try {
    await dramaStore.updateProjectSettings(projectId.value, settings)
  } catch (err) {
    console.error('Save settings failed:', err)
    ElMessage.error('设定保存失败')
  }
}

function handleEditCharacter(char: CharacterSetting) {
  editingCharacter.value = char
  showCharacterOverlay.value = true
}

function handleCharacterSave(updated: CharacterSetting) {
  showCharacterOverlay.value = false
  settingsDrawerRef.value?.updateCharacter(updated)
}
```

- [ ] **Step 4: 验证类型编译**

```bash
cd /data/project/novel-writer/frontend
npx tsc --noEmit 2>&1 | head -30
```

期望：无类型错误

- [ ] **Step 5: 手动验证（启动 docker）**

```bash
cd /data/project/novel-writer && docker compose up -d
```

打开 `http://localhost:8083/drama/workbench/<任意项目id>`，验证：
1. 工具栏出现「⚙ 设定」按钮，「全局指令」按钮依然存在
2. 点击「⚙ 设定」后从右侧滑出抽屉，不影响左侧和中央布局
3. 5 个折叠面板可展开/折叠，文本框有字数限制显示
4. 编辑文本后 500ms 自动保存，显示「已保存 ✓」
5. 点击「添加角色」弹出 CharacterEditOverlay（居中浮层）
6. Esc 关闭浮层，Ctrl+Enter 保存并写回列表
7. 刷新页面后设定数据依然保留

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/DramaWorkbenchView.vue
git commit -m "feat(drama): wire ScriptSettingsDrawer and CharacterEditOverlay into workbench

Adds '设定' toolbar button alongside preserved '全局指令'.
Settings auto-saved to metadata_['settings'] via store action."
```

---

## Task 8: 端到端验证

- [ ] **Step 1: 后端所有相关测试**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_ai_service.py tests/test_drama_settings.py tests/test_drama_schemas.py -v 2>&1 | tail -30
```

期望：全部通过

- [ ] **Step 2: 前端类型检查**

```bash
cd /data/project/novel-writer/frontend
npx tsc --noEmit 2>&1 | head -20
```

期望：无错误

- [ ] **Step 3: 手动验证 AI 注入**

1. 在设定抽屉中填写「风格基调：悬疑紧张」并等待保存
2. 在 AI 助手面板对某个节点请求内容生成
3. 观察生成结果是否体现悬疑风格
