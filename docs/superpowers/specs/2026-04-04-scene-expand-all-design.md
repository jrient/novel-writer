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
- `frontend/src/components/drama/OutlineDraftPreview.vue` — 轻微改动（新增 prop）

**不涉及：**
- 后端 API（`streamExpandEpisode` 已存在，无需修改）
- 其他步骤的 UI

---

## 详细设计

### 1. 状态定义

在 `DramaWizardView.vue` 中新增：

```ts
const isExpandingAll = ref(false)
const expandAllCurrent = ref(0)   // 当前正在展开第几集（1-based，用于显示）
const expandAllTotal = ref(0)     // 本次需展开的集总数
```

"已全部展开"的计算属性（用于按钮禁用判断）：

```ts
const allExpanded = computed(() =>
  outlineSections.value.length > 0 &&
  outlineSections.value.every(ep => (ep.children?.length ?? 0) > 0)
)
```

### 2. `handleExpandAll()` 逻辑

```
1. 若 expandingIndex !== null（单集正在展开中）
   → ElMessage.warning('请等待当前集展开完成')，return

2. 检查是否存在已展开的集（children.length > 0）
   ├─ 有已展开的集：
   │  ElMessageBox.confirm(
   │    '部分集已展开，请选择展开方式',
   │    buttons: ['跳过已展开', '全部重新展开']
   │  )
   │  ├─ '跳过已展开' → targets = sections.filter(ep => !ep.children?.length)
   │  └─ '全部重新展开' → targets = 所有集（展开前不清空数据，由后端覆盖）
   └─ 全部未展开 → targets = 所有集

3. expandAllTotal.value = targets.length
   isExpandingAll.value = true

4. for (const { index } of targets)（顺序执行，逐个 await）：
   expandAllCurrent.value = 当前第几个（1-based）
   await new Promise<void>((resolve, reject) => {
     streamExpandEpisode(projectId, index, () => {}, resolve, (err) => {
       ElMessage.error(`第 ${index + 1} 集展开失败：${err}`)
       resolve()  // 失败后继续下一集，不中断整体流程
     })
   })
   emit('episode-expanded', index)

5. isExpandingAll.value = false
   expandAllCurrent.value = 0
   ElMessage.success('全部场景展开完成')
```

### 3. 按钮状态

| 状态 | 文案 | 样式 | 可点击 |
|------|------|------|--------|
| 默认 | `展开全部场景` | plain | ✅ |
| 展开中 | `展开中 (3/12)` | plain + loading | ❌ |
| 全部完成 | `已全部展开` | plain | ❌（disabled） |

### 4. 按钮位置

Step 2 底部操作区，三个按钮从左到右：

```
[ 重新生成大纲 ]  [ 展开全部场景 ]  [ 下一步 → ]
```

- "展开全部场景"使用 `plain` 样式，视觉权重低于"下一步"（主操作按钮）
- "重新生成大纲"在最左，破坏性操作保持距离

### 5. 冲突处理

| 场景 | 处理方式 |
|------|---------|
| 一键展开进行中，用户点单集"展开场景" | `OutlineDraftPreview` 收到 `disableIndividual=true` prop，各集按钮隐藏 |
| 单集正在展开中，用户点"展开全部" | 检查 `expandingIndex !== null`，提示等待后返回 |
| 展开全部过程中某集 API 失败 | `ElMessage.error` 提示该集失败，继续展开剩余集 |
| 展开过程中用户切换步骤/离开页面 | 不强制中断 SSE，自然结束；状态在 `onUnmounted` 中重置 |

### 6. `OutlineDraftPreview` 新增 prop

```ts
defineProps<{
  projectId: number
  sections: EpisodeSection[]
  disableIndividual?: boolean  // 新增：一键展开进行中时禁用单集按钮
}>()
```

单集"展开场景"按钮条件：`v-if="!disableIndividual && !isExpanded(index)"`

---

## 不包含的内容（YAGNI）

- 展开全部的"取消"功能（用户未要求）
- 展开进度条 UI（按钮文案已足够）
- 并行展开模式
- 展开结果的持久化（已由现有 `episode-expanded` 事件处理）

---

## 验收标准

1. Step 2 底部出现"展开全部场景"按钮
2. 全部未展开时点击，直接开始顺序展开
3. 部分已展开时点击，弹出确认框（两个选项）
4. 展开中按钮显示"展开中 (N/M)"并不可点击
5. 单集展开按钮在一键展开进行中隐藏
6. 某集失败时提示错误，继续展开剩余集
7. 全部展开完成后按钮显示"已全部展开"并禁用
