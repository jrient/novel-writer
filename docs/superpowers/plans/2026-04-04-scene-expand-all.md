# 一键展开全部场景 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在剧本引导向导 Step 2 大纲预览的底部操作区新增"一键展开全部场景"按钮，顺序调用 `streamExpandEpisode` API 依次展开所有集的场景列表。

**Architecture:** 改动仅限两个前端文件。`OutlineDraftPreview.vue` 新增 `disableIndividual` prop 和 `expanding-change` emit，用于与父组件互斥；`DramaWizardView.vue` 新增展开全部的状态管理和 `handleExpandAll()` 函数，并在 Step 2 操作区渲染新按钮。后端无需改动。

**Tech Stack:** Vue 3 (Composition API), TypeScript, Element Plus (`ElMessage`, `ElMessageBox`), SSE via `streamExpandEpisode` (already exists in `@/api/drama`)

**Spec:** `docs/superpowers/specs/2026-04-04-scene-expand-all-design.md`

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/components/drama/OutlineDraftPreview.vue` | Modify | 新增 prop、emit，修改按钮条件，更新类型定义 |
| `frontend/src/views/DramaWizardView.vue` | Modify | 新增状态、函数、按钮，更新 imports 和 template |

---

## Task 1: 更新 OutlineDraftPreview — 类型、prop 和 emit

**Files:**
- Modify: `frontend/src/components/drama/OutlineDraftPreview.vue`

- [ ] **Step 1: 将 `EpisodeSection.children` 改为可选字段**

在 `OutlineDraftPreview.vue` 第 62 行，将：
```ts
children: Array<{ node_type: string; title: string; content: string; sort_order: number }>
```
改为：
```ts
children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
```

- [ ] **Step 2: 新增 `disableIndividual` prop**

将 `defineProps` 改为：
```ts
const props = defineProps<{
  projectId: number
  sections: EpisodeSection[]
  disableIndividual?: boolean
}>()
```

- [ ] **Step 3: 新增 `expanding-change` emit**

将 `defineEmits` 改为：
```ts
const emit = defineEmits<{
  (e: 'episode-expanded', index: number): void
  (e: 'expanding-change', isExpanding: boolean): void
}>()
```

- [ ] **Step 4: 修改 `handleExpand` — 发出展开状态事件**

将当前的 `handleExpand` 函数替换为：
```ts
function handleExpand(index: number) {
  if (expandingIndex.value !== null) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }
  expandingIndex.value = index
  emit('expanding-change', true)

  streamExpandEpisode(
    props.projectId,
    index,
    () => { /* chunk 忽略 */ },
    () => {
      expandingIndex.value = null
      emit('expanding-change', false)
      emit('episode-expanded', index)
    },
    (error) => {
      expandingIndex.value = null
      emit('expanding-change', false)
      ElMessage.error(`展开失败：${error}`)
    },
  )
}
```

- [ ] **Step 5: 修改单集按钮的显示条件**

将模板中：
```html
<el-button
  v-else
  size="small"
  :loading="expandingIndex === index"
  @click="handleExpand(index)"
>
```
改为（注意 `v-if` 替换 `v-else`）：
```html
<el-button
  v-if="!props.disableIndividual && !isExpanded(index)"
  size="small"
  :loading="expandingIndex === index"
  @click="handleExpand(index)"
>
```
同时将 `<el-tag v-if="isExpanded(index)"` 保持不变（已展开标签仍显示）。

- [ ] **Step 6: 验证模板结构正确**

确认 `episode-actions` 区域最终结构为：
```html
<div class="episode-actions">
  <el-tag v-if="isExpanded(index)" type="success" size="small">已展开</el-tag>
  <el-button
    v-if="!props.disableIndividual && !isExpanded(index)"
    size="small"
    :loading="expandingIndex === index"
    @click="handleExpand(index)"
  >
    展开场景
  </el-button>
</div>
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/drama/OutlineDraftPreview.vue
git commit -m "feat(drama): add disableIndividual prop and expanding-change emit to OutlineDraftPreview

Scope-risk: narrow
Confidence: high"
```

---

## Task 2: 更新 DramaWizardView — imports 和新增状态

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 更新 Vue imports，加入 `onUnmounted`**

将第 194 行：
```ts
import { ref, reactive, computed, watch, onMounted } from 'vue'
```
改为：
```ts
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
```

- [ ] **Step 2: 更新 Element Plus import，加入 `ElMessageBox`**

将第 197 行：
```ts
import { ElMessage } from 'element-plus'
```
改为：
```ts
import { ElMessage, ElMessageBox } from 'element-plus'
```

- [ ] **Step 3: 新增 `streamExpandEpisode` import**

将第 199 行：
```ts
import { summarizeSession, updateSessionSummary, streamGenerateOutline } from '@/api/drama'
```
改为：
```ts
import { summarizeSession, updateSessionSummary, streamGenerateOutline, streamExpandEpisode } from '@/api/drama'
```

- [ ] **Step 4: 新增展开全部相关状态变量**

在 `script setup` 中现有 `const confirming = ref(false)` 附近，新增以下变量（放在一起便于阅读）：
```ts
// 一键展开全部场景
const isExpandingAll = ref(false)
const expandAllCurrent = ref(0)
const expandAllTotal = ref(0)
const isSingleExpanding = ref(false)
const currentAbortController = ref<AbortController | null>(null)
```

- [ ] **Step 5: 同步 `outlineSections` 内联类型 — 将 `children` 改为可选**

`DramaWizardView.vue` 第 274-281 行的 `outlineSections` computed 中有一个内联类型断言，其中 `children` 是非可选字段。需同步改为 `children?:` 与 spec §7 保持一致。

将：
```ts
return draft.sections as Array<{
  node_type: string
  title: string
  content: string
  sort_order: number
  children: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}>
```
改为：
```ts
return draft.sections as Array<{
  node_type: string
  title: string
  content: string
  sort_order: number
  children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}>
```

- [ ] **Step 6: 新增 `allExpanded` 计算属性**

在 `outlineSections` computed 下方新增：
```ts
const allExpanded = computed(() =>
  outlineSections.value.length > 0 &&
  outlineSections.value.every(ep => (ep.children?.length ?? 0) > 0)
)
```

- [ ] **Step 7: Commit（中间状态）**

```bash
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): add expand-all state and imports to DramaWizardView

Scope-risk: narrow
Confidence: high"
```

---

## Task 3: 实现 `handleExpandAll()` 和 `onUnmounted`

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 实现 `handleExpandAll` 函数**

在 `handleEpisodeExpanded` 函数下方新增：

```ts
async function handleExpandAll() {
  // 单集正在展开中，拒绝
  if (isSingleExpanding.value) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }

  const sections = outlineSections.value
  let targets: Array<{ originalIndex: number }>

  // 检查是否有已展开的集
  const hasExpanded = sections.some(ep => (ep.children?.length ?? 0) > 0)

  if (hasExpanded) {
    try {
      await ElMessageBox.confirm(
        '部分集已展开，请选择展开方式',
        '展开全部场景',
        {
          distinguishCancelAndClose: true,
          confirmButtonText: '全部重新展开',
          cancelButtonText: '跳过已展开',
        },
      )
      // 用户点"全部重新展开" (confirm)
      targets = sections.map((_, i) => ({ originalIndex: i }))
    } catch (action) {
      if (action === 'cancel') {
        // 用户点"跳过已展开"
        targets = sections
          .map((ep, i) => ({ ep, originalIndex: i }))
          .filter(({ ep }) => (ep.children?.length ?? 0) === 0)
          .map(({ originalIndex }) => ({ originalIndex }))
      } else {
        // 用户点关闭 (close) 或按 Esc
        return
      }
    }
  } else {
    targets = sections.map((_, i) => ({ originalIndex: i }))
  }

  if (targets.length === 0) {
    ElMessage.info('没有需要展开的集')
    return
  }

  expandAllTotal.value = targets.length
  isExpandingAll.value = true

  for (let i = 0; i < targets.length; i++) {
    const { originalIndex } = targets[i]
    expandAllCurrent.value = i + 1

    await new Promise<void>((resolve) => {
      const ctrl = streamExpandEpisode(
        projectId.value,
        originalIndex,
        () => { /* chunk 忽略 */ },
        async () => {
          currentAbortController.value = null
          await dramaStore.fetchSession(projectId.value)
          resolve()
        },
        (error) => {
          ElMessage.error(`第 ${originalIndex + 1} 集展开失败：${error}`)
          currentAbortController.value = null
          resolve()
        },
      )
      currentAbortController.value = ctrl
    })
  }

  isExpandingAll.value = false
  expandAllCurrent.value = 0
  currentAbortController.value = null
  ElMessage.success('全部场景展开完成')
}
```

> **注意：** 每集展开成功后直接调用 `dramaStore.fetchSession()` 刷新数据。spec 中 `emit('episode-expanded')` 的写法是子组件视角的伪代码；由于 `handleExpandAll` 本身就在父组件 `DramaWizardView` 中，直接调用 store 是等价且更直接的正确做法。

- [ ] **Step 2: 新增 `onUnmounted` 清理**

在 `onMounted` 下方新增：
```ts
onUnmounted(() => {
  currentAbortController.value?.abort()
  isExpandingAll.value = false
  expandAllCurrent.value = 0
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): implement handleExpandAll with sequential SSE and abort cleanup

Constraint: Sequential only — no parallel expand
Scope-risk: narrow
Confidence: high"
```

---

## Task 4: 更新 Step 2 模板 — 绑定新 props/events 和新增按钮

**Files:**
- Modify: `frontend/src/views/DramaWizardView.vue`

- [ ] **Step 1: 更新 `OutlineDraftPreview` 的模板绑定**

将：
```html
<OutlineDraftPreview
  :project-id="projectId"
  :sections="outlineSections"
  @episode-expanded="handleEpisodeExpanded"
/>
```
改为：
```html
<OutlineDraftPreview
  :project-id="projectId"
  :sections="outlineSections"
  :disable-individual="isExpandingAll"
  @episode-expanded="handleEpisodeExpanded"
  @expanding-change="isSingleExpanding = $event"
/>
```

- [ ] **Step 2: 在 `outline-actions` 中新增"展开全部场景"按钮**

将：
```html
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
```
改为：
```html
<div class="outline-actions">
  <el-button @click="wizardStepIndex = 1">返回确认</el-button>
  <el-button
    plain
    :loading="isExpandingAll"
    :disabled="allExpanded"
    @click="handleExpandAll"
  >
    {{ isExpandingAll ? `展开中 (${expandAllCurrent}/${expandAllTotal})` : allExpanded ? '已全部展开' : '展开全部场景' }}
  </el-button>
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
```

- [ ] **Step 3: 更新 `outline-subtitle` 提示文案**

将：
```html
共 {{ outlineSections.length }} 集 · 点击"展开场景"可逐集生成详细场景
```
改为：
```html
共 {{ outlineSections.length }} 集 · 可逐集展开或一键展开全部场景
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/DramaWizardView.vue
git commit -m "feat(drama): wire expand-all button and OutlineDraftPreview bindings in wizard Step 2

Scope-risk: narrow
Confidence: high"
```

---

## Task 5: 手动验证验收标准

- [ ] **Step 1: 启动前端开发服务器**

```bash
cd /data/project/novel-writer
docker compose up -d   # 或本地: cd frontend && npm run dev
```

- [ ] **Step 2: 验证 AC1 — Step 2 底部出现"展开全部场景"按钮**

进入剧本引导向导，完成 Step 0/1，到达 Step 2 大纲预览页。
预期：底部操作区显示三个按钮：`返回确认` / `展开全部场景` / `确认大纲，开始创作`

- [ ] **Step 3: 验证 AC2 — 全部未展开时直接展开，无确认框**

在所有集未展开的状态下点击"展开全部场景"。
预期：直接开始展开，按钮变为 `展开中 (1/N)`，无弹窗。

- [ ] **Step 4: 验证 AC3 — 部分已展开时弹确认框**

手动展开1-2集后，点击"展开全部场景"。
预期：弹出 `ElMessageBox` 含两个选项"跳过已展开"和"全部重新展开"，关闭按钮也存在。

- [ ] **Step 5: 验证 AC4 — 展开中按钮显示进度**

展开全部进行中，观察按钮。
预期：显示 `展开中 (N/M)` 格式，不可点击。

- [ ] **Step 6: 验证 AC5 — 单集按钮在展开全部时隐藏**

展开全部进行中，观察各集行。
预期：各集的"展开场景"按钮消失（已展开的集仍显示"已展开"标签）。

- [ ] **Step 7: 验证 AC7 — 全部完成后按钮禁用**

展开完成后观察按钮。
预期：显示"已全部展开"且不可点击，`ElMessage.success` 提示出现。

- [ ] **Step 8: 验证 AC6 — 某集失败时继续展开剩余集**

在浏览器 Network 面板中对某集的 `expand-episode` 请求拦截返回错误（或临时关闭网络后恢复）。
预期：弹出 `ElMessage.error` 提示该集失败，其他集继续展开，不中断整体流程。

- [ ] **Step 9: 验证 AC8 — 组件卸载时中止 SSE**

展开进行中（按钮显示"展开中 N/M"），点击"返回确认"或浏览器后退离开页面。
在 Chrome DevTools → Network 面板确认：EventStream 连接状态变为 `canceled`（而非 `pending`）。
预期：`onUnmounted` 触发 `abort()`，SSE 连接被中止。

- [ ] **Step 10: Commit 验证通过**

```bash
git add .
git commit -m "chore: manual verification complete for expand-all feature" --allow-empty
```

---

## 快速参考

**关键文件：**
- `frontend/src/components/drama/OutlineDraftPreview.vue` — 子组件（prop/emit改动）
- `frontend/src/views/DramaWizardView.vue` — 父组件（状态、函数、模板）
- `frontend/src/api/drama.ts:259` — `streamExpandEpisode` API（只读参考，勿修改）

**不需要改动的文件：**
- 后端任何文件
- `frontend/src/stores/drama.ts`
- 其他 Vue 组件
