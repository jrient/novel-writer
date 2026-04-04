# 设计规格：大纲预览一键展开全部场景

**日期：** 2026-04-04
**功能：** 剧本引导向导 Step 2 大纲预览，新增"一键展开全部场景"按钮
**状态：** 待实现

---

## 背景

剧本引导向导 Step 2（大纲预览）中，用户需要逐集点击"展开场景"按钮来查看每集的场景列表。当集数较多时（最多200集），逐一点击效率低。本功能在向导底部操作区新增"一键展开全部场景"按钮，自动顺序展开所有集的场景。

---

## 功能范围

**涉及文件：**
- `frontend/src/views/DramaWizardView.vue` — 主要改动
- `frontend/src/components/drama/OutlineDraftPreview.vue` — 新增 prop 和 emit

**不涉及：**
- 后端 API（`streamExpandEpisode` 已存在，无需修改）
- 其他步骤的 UI

---

## 详细设计

### 1. 状态定义

在 `DramaWizardView.vue` 中新增：

```ts
import { ElMessage, ElMessageBox } from 'element-plus'  // 新增 ElMessageBox

const isExpandingAll = ref(false)
const expandAllCurrent = ref(0)      // 当前正在展开第几集（1-based，用于显示）
const expandAllTotal = ref(0)        // 本次需展开的集总数
const isSingleExpanding = ref(false) // 子组件单集展开状态（由子组件 emit 同步）
const currentAbortController = ref<AbortController | null>(null) // 用于 onUnmounted 时中止
```

"已全部展开"的计算属性：

```ts
const allExpanded = computed(() =>
  outlineSections.value.length > 0 &&
  outlineSections.value.every(ep => (ep.children?.length ?? 0) > 0)
  // children? 为防御性写法，对应 children?: Array<...> 类型（见第7节）
)
```

### 2. `handleExpandAll()` 逻辑

```
1. 若 isSingleExpanding.value === true（子组件单集正在展开中）
   → ElMessage.warning('请等待当前集展开完成')，return

2. 检查是否存在已展开的集（children.length > 0）
   ├─ 有已展开的集：
   │  ElMessageBox.confirm(
   │    '部分集已展开，请选择展开方式',
   │    {
   │      distinguishCancelAndClose: true,
   │      confirmButtonText: '全部重新展开',
   │      cancelButtonText: '跳过已展开',
   │    }
   │  )
   │  ├─ 用户点"跳过已展开" (catch cancel) → targets = sections.filter(ep => !ep.children?.length)
   │  ├─ 用户点"全部重新展开" (confirm) → targets = 所有集
   │  └─ 用户点关闭 (catch close) → return，不展开
   └─ 全部未展开 → targets = 所有集

3. expandAllTotal.value = targets.length
   isExpandingAll.value = true

4. for (const { originalIndex } of targets)（顺序执行，逐个 await）：
   expandAllCurrent.value = 当前第几个（1-based）
   await new Promise<void>((resolve) => {
     const ctrl = streamExpandEpisode(
       projectId, originalIndex,
       () => {},
       () => {
         currentAbortController.value = null
         emit('episode-expanded', originalIndex)  // 仅成功时触发
         resolve()
       },
       (err) => {
         ElMessage.error(`第 ${originalIndex + 1} 集展开失败：${err}`)
         currentAbortController.value = null
         resolve()  // 失败后继续下一集，不触发 episode-expanded
       }
     )
     currentAbortController.value = ctrl
   })

5. isExpandingAll.value = false
   expandAllCurrent.value = 0
   currentAbortController.value = null
   ElMessage.success('全部场景展开完成')
```

### 3. `onUnmounted` 清理

```ts
onUnmounted(() => {
  currentAbortController.value?.abort()
  isExpandingAll.value = false
  expandAllCurrent.value = 0
})
```

中止进行中的 SSE 请求，防止组件卸载后回调修改已销毁的响应式状态。

### 4. 按钮状态

| 状态 | 文案 | 样式 | 可点击 |
|------|------|------|--------|
| 默认 | `展开全部场景` | plain | ✅ |
| 展开中 | `展开中 (3/12)` | plain + loading | ❌ |
| 全部完成 | `已全部展开` | plain | ❌（disabled） |

### 5. 按钮位置

Step 2 底部操作区，三个按钮从左到右：

```
[ 重新生成大纲 ]  [ 展开全部场景 ]  [ 下一步 → ]
```

- "展开全部场景"使用 `plain` 样式，视觉权重低于"下一步"（主操作按钮）

### 6. `OutlineDraftPreview` 改动

**新增 prop：**

```ts
defineProps<{
  projectId: number
  sections: EpisodeSection[]
  disableIndividual?: boolean  // 一键展开进行中时隐藏单集按钮
}>()
```

**新增 emit（用于父组件感知单集展开状态）：**

```ts
const emit = defineEmits<{
  (e: 'episode-expanded', index: number): void
  (e: 'expanding-change', isExpanding: boolean): void  // 新增
}>()
```

在 `handleExpand` 中：
```ts
function handleExpand(index: number) {
  // ...existing guard...
  expandingIndex.value = index
  emit('expanding-change', true)   // 新增

  streamExpandEpisode(...,
    () => { expandingIndex.value = null; emit('expanding-change', false); emit('episode-expanded', index) },
    (err) => { expandingIndex.value = null; emit('expanding-change', false); ElMessage.error(...) }
  )
}
```

在 `DramaWizardView.vue` 中监听：

```html
<OutlineDraftPreview
  ...
  :disable-individual="isExpandingAll"
  @expanding-change="isSingleExpanding = $event"
/>
```

单集按钮条件：`v-if="!disableIndividual && !isExpanded(index)"`

### 7. 类型定义统一

将 `OutlineDraftPreview.vue` 中的 `EpisodeSection` 的 `children` 改为可选字段，与防御性写法对齐：

```ts
interface EpisodeSection {
  node_type: string
  title: string
  content: string
  sort_order: number
  children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}
```

### 8. 后端行为确认

已验证：后端 `expand-episode` 接口（`drama.py` 第 795 行）对 `children` 是 **replace** 操作，会覆盖已有数据。因此"全部重新展开"时无需前端手动清空 `children`，后端完成后前端调用 `emit('episode-expanded')` 触发 `fetchSession()` 刷新即可。

---

## 冲突处理

| 场景 | 处理方式 |
|------|---------|
| 一键展开进行中，用户点单集"展开场景" | `disableIndividual=true`，按钮隐藏 |
| 单集正在展开中，用户点"展开全部" | 检查 `isSingleExpanding`，提示等待后返回 |
| 展开全部过程中某集 API 失败 | `ElMessage.error` 提示该集失败，继续展开剩余集 |
| 用户切换步骤/离开页面 | `onUnmounted` abort 当前 SSE 请求并重置状态 |
| 用户关闭确认框（×按钮） | `distinguishCancelAndClose: true`，关闭视为取消，不执行展开 |

---

## 不包含的内容（YAGNI）

- 展开全部的"取消"按钮（用户未要求）
- 展开进度条 UI（按钮文案已足够）
- 并行展开模式

---

## 验收标准

1. Step 2 底部出现"展开全部场景"按钮
2. 全部未展开时点击，直接开始顺序展开，无确认框
3. 部分已展开时点击，弹出确认框（"跳过已展开" / "全部重新展开" / 关闭）
4. 展开中按钮显示"展开中 (N/M)"并不可点击
5. 单集展开按钮在一键展开进行中隐藏
6. 某集失败时提示错误，继续展开剩余集
7. 全部展开完成后按钮显示"已全部展开"并禁用
8. 组件卸载时中止进行中的 SSE 请求
