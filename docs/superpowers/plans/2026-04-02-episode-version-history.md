# Episode Version History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add version history for episode nodes in the script editor, allowing users to view and restore previous versions.

**Architecture:** New `script_node_versions` table stores content snapshots. Backend provides CRUD+restore API. Frontend creates snapshots before AI apply and node switch, displays version list in a dialog.

**Tech Stack:** SQLAlchemy (model), FastAPI (API), Vue 3 + Element Plus (UI), Pinia (store)

**Spec:** `docs/superpowers/specs/2026-04-02-episode-version-history-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/models/script_node_version.py` | ORM model for version table |
| Modify | `backend/app/models/__init__.py:21-34` | Register new model |
| Modify | `backend/app/models/script_node.py:13-89` | Add `versions` relationship |
| Modify | `backend/app/schemas/drama.py` | Add version request/response schemas |
| Modify | `backend/app/routers/drama.py:733-786` | Create init versions on confirm_outline |
| Modify | `backend/app/routers/drama.py` (append) | Add 3 new version API endpoints |
| Modify | `frontend/src/api/drama.ts` (append) | Add version API functions |
| Modify | `frontend/src/stores/drama.ts:100-178` | Add version actions |
| Modify | `frontend/src/components/drama/ScriptEditor.vue:14-29` | Add "history" button in header |
| Create | `frontend/src/components/drama/VersionHistoryDialog.vue` | Version list dialog component |
| Modify | `frontend/src/views/DramaWorkbenchView.vue:280-360` | Wire up version snapshots on AI apply and node switch |

---

### Task 1: Backend Model — ScriptNodeVersion

**Files:**
- Create: `backend/app/models/script_node_version.py`
- Modify: `backend/app/models/__init__.py:21-34`
- Modify: `backend/app/models/script_node.py`

- [ ] **Step 1: Create the model file**

Create `backend/app/models/script_node_version.py`:

```python
"""
剧本节点版本历史模型
保存 episode 节点的历史版本，支持内容恢复
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.script_node import ScriptNode


class ScriptNodeVersion(Base):
    """剧本节点版本历史表"""
    __tablename__ = "script_node_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("script_nodes.id", ondelete="CASCADE"),
        nullable=False, comment="所属节点ID"
    )

    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="版本号（节点内递增）"
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="标题快照"
    )

    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="内容快照"
    )

    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual",
        comment="来源: init/ai_apply/switch/manual"
    )

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )

    node: Mapped["ScriptNode"] = relationship("ScriptNode", back_populates="versions")

    __table_args__ = (
        Index("ix_snv_node_version", "node_id", "version_number"),
    )
```

- [ ] **Step 2: Add relationship to ScriptNode**

In `backend/app/models/script_node.py`, add at the top with other TYPE_CHECKING imports:

```python
if TYPE_CHECKING:
    from app.models.script_node_version import ScriptNodeVersion
```

Add relationship to the class (after `parent` relationship):

```python
    versions: Mapped[list["ScriptNodeVersion"]] = relationship(
        "ScriptNodeVersion", back_populates="node", cascade="all, delete-orphan",
        order_by="ScriptNodeVersion.version_number.desc()"
    )
```

- [ ] **Step 3: Register model in `__init__.py`**

In `backend/app/models/__init__.py`, add after ScriptSession import (line 23):

```python
from app.models.script_node_version import ScriptNodeVersion
```

Add `"ScriptNodeVersion"` to the `__all__` list on the ScriptProject line.

- [ ] **Step 4: Verify table creation**

Run: `docker compose exec backend python -c "from app.models import ScriptNodeVersion; print(ScriptNodeVersion.__tablename__)"`
Expected: `script_node_versions`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/script_node_version.py backend/app/models/__init__.py backend/app/models/script_node.py
git commit -m "feat(drama): add ScriptNodeVersion model for episode version history"
```

---

### Task 2: Backend Schemas

**Files:**
- Modify: `backend/app/schemas/drama.py`

- [ ] **Step 1: Add version schemas**

Append to the end of `backend/app/schemas/drama.py`:

```python
# ── Node Version Schemas ──

class CreateVersionRequest(BaseModel):
    source: str = Field(..., pattern=r"^(ai_apply|switch|manual)$", description="版本来源")

class NodeVersionResponse(BaseModel):
    id: int
    node_id: int
    version_number: int
    title: Optional[str] = None
    content: Optional[str] = None
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class NodeVersionListResponse(BaseModel):
    id: int
    node_id: int
    version_number: int
    title: Optional[str] = None
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

Make sure `datetime` and `ConfigDict` are imported at top of file. Check if `from datetime import datetime` exists; add if not. Check if `ConfigDict` is imported from pydantic; add if not.

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/drama.py
git commit -m "feat(drama): add version history request/response schemas"
```

---

### Task 3: Backend API Endpoints

**Files:**
- Modify: `backend/app/routers/drama.py` (append new endpoints)

- [ ] **Step 1: Add helper function for creating a version snapshot**

Add this helper function before the existing endpoints (after imports section):

```python
from app.models.script_node_version import ScriptNodeVersion
from app.schemas.drama import CreateVersionRequest, NodeVersionResponse, NodeVersionListResponse

async def _create_node_version(
    db: AsyncSession, node: ScriptNode, source: str
) -> ScriptNodeVersion:
    """Create a version snapshot for an episode node, enforcing max 20 versions."""
    # Get next version number
    result = await db.execute(
        select(func.coalesce(func.max(ScriptNodeVersion.version_number), 0))
        .where(ScriptNodeVersion.node_id == node.id)
    )
    next_version = result.scalar() + 1

    version = ScriptNodeVersion(
        node_id=node.id,
        version_number=next_version,
        title=node.title,
        content=node.content,
        source=source,
    )
    db.add(version)
    await db.flush()

    # Enforce max 20 versions: delete oldest if exceeded
    count_result = await db.execute(
        select(func.count()).where(ScriptNodeVersion.node_id == node.id)
    )
    total = count_result.scalar()
    if total > 20:
        oldest = await db.execute(
            select(ScriptNodeVersion)
            .where(ScriptNodeVersion.node_id == node.id)
            .order_by(ScriptNodeVersion.version_number.asc())
            .limit(total - 20)
        )
        for old_ver in oldest.scalars():
            await db.delete(old_ver)

    return version
```

- [ ] **Step 2: Add GET versions list endpoint**

Append to `backend/app/routers/drama.py`:

```python
@router.get("/{id}/nodes/{node_id}/versions", response_model=list[NodeVersionListResponse])
async def list_node_versions(
    node_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """查询节点版本历史列表"""
    result = await db.execute(
        select(ScriptNodeVersion)
        .where(ScriptNodeVersion.node_id == node_id)
        .order_by(ScriptNodeVersion.version_number.desc())
    )
    return result.scalars().all()
```

- [ ] **Step 3: Add POST create version endpoint**

```python
@router.post("/{id}/nodes/{node_id}/versions", response_model=NodeVersionResponse)
async def create_node_version(
    node_id: int,
    body: CreateVersionRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """手动创建节点版本快照"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Episode 节点不存在")

    version = await _create_node_version(db, node, body.source)
    await db.commit()
    await db.refresh(version)
    return version
```

- [ ] **Step 4: Add POST restore version endpoint**

```python
@router.post("/{id}/nodes/{node_id}/versions/{version_id}/restore", response_model=NodeVersionResponse)
async def restore_node_version(
    node_id: int,
    version_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """恢复到指定版本（恢复前自动创建当前内容的快照）"""
    # Get the node
    node_result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Episode 节点不存在")

    # Get the target version
    ver_result = await db.execute(
        select(ScriptNodeVersion).where(
            ScriptNodeVersion.id == version_id,
            ScriptNodeVersion.node_id == node_id,
        )
    )
    target = ver_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")

    # Snapshot current content before restoring
    pre_restore = await _create_node_version(db, node, "manual")

    # Restore node content
    node.title = target.title
    node.content = target.content
    await db.commit()
    await db.refresh(pre_restore)
    return pre_restore
```

- [ ] **Step 5: Modify confirm_outline to create init versions**

In the existing `session_confirm_outline` endpoint (around line 733-786), add version creation after `_write_nodes_async`. Before `await db.commit()`, add:

```python
    # Create initial versions for all episode nodes
    ep_result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    for ep_node in ep_result.scalars():
        init_ver = ScriptNodeVersion(
            node_id=ep_node.id,
            version_number=1,
            title=ep_node.title,
            content=ep_node.content,
            source="init",
        )
        db.add(init_ver)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/drama.py
git commit -m "feat(drama): add version history API endpoints (list, create, restore)"
```

---

### Task 4: Frontend API Layer

**Files:**
- Modify: `frontend/src/api/drama.ts`

- [ ] **Step 1: Add version types and API functions**

Append to `frontend/src/api/drama.ts`:

```typescript
// ── Node Version API ──

export interface NodeVersion {
  id: number
  node_id: number
  version_number: number
  title: string | null
  content: string | null
  source: 'init' | 'ai_apply' | 'switch' | 'manual'
  created_at: string
}

export interface NodeVersionListItem {
  id: number
  node_id: number
  version_number: number
  title: string | null
  source: string
  created_at: string
}

export async function listNodeVersions(projectId: number, nodeId: number): Promise<NodeVersionListItem[]> {
  return request.get<NodeVersionListItem[]>(`/drama/${projectId}/nodes/${nodeId}/versions`)
}

export async function createNodeVersion(projectId: number, nodeId: number, source: string): Promise<NodeVersion> {
  return request.post<NodeVersion>(`/drama/${projectId}/nodes/${nodeId}/versions`, { source })
}

export async function restoreNodeVersion(projectId: number, nodeId: number, versionId: number): Promise<NodeVersion> {
  return request.post<NodeVersion>(`/drama/${projectId}/nodes/${nodeId}/versions/${versionId}/restore`)
}

export async function getNodeVersion(projectId: number, nodeId: number, versionId: number): Promise<NodeVersion> {
  return request.get<NodeVersion>(`/drama/${projectId}/nodes/${nodeId}/versions/${versionId}`)
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/drama.ts
git commit -m "feat(drama): add version history API client functions"
```

---

### Task 5: Frontend — VersionHistoryDialog Component

**Files:**
- Create: `frontend/src/components/drama/VersionHistoryDialog.vue`

- [ ] **Step 1: Create the dialog component**

Create `frontend/src/components/drama/VersionHistoryDialog.vue`:

```vue
<template>
  <el-dialog
    v-model="visible"
    title="历史版本"
    width="640px"
    :close-on-click-modal="false"
    @open="loadVersions"
  >
    <div v-loading="loading" class="version-list">
      <el-empty v-if="!loading && !versions.length" description="暂无历史版本" :image-size="60" />

      <div
        v-for="ver in versions"
        :key="ver.id"
        class="version-item"
        :class="{ 'version-item--active': expandedId === ver.id }"
      >
        <div class="version-header" @click="toggleExpand(ver)">
          <div class="version-meta">
            <span class="version-number">v{{ ver.version_number }}</span>
            <el-tag :type="sourceTagType(ver.source)" size="small" effect="plain">
              {{ sourceLabel(ver.source) }}
            </el-tag>
            <span class="version-title">{{ ver.title || '(无标题)' }}</span>
          </div>
          <span class="version-time">{{ formatTime(ver.created_at) }}</span>
        </div>

        <div v-if="expandedId === ver.id" class="version-content">
          <div v-if="expandedContent === null" v-loading="true" style="min-height: 60px" />
          <pre v-else class="content-preview">{{ expandedContent || '(空内容)' }}</pre>
          <div class="version-actions">
            <el-button
              type="primary"
              size="small"
              :loading="restoring"
              @click="handleRestore(ver)"
            >
              恢复此版本
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listNodeVersions, restoreNodeVersion } from '@/api/drama'
import type { NodeVersionListItem, NodeVersion } from '@/api/drama'

const props = defineProps<{
  projectId: number
  nodeId: number
}>()

const emit = defineEmits<{
  (e: 'restored'): void
}>()

const visible = defineModel<boolean>({ default: false })

const versions = ref<NodeVersionListItem[]>([])
const loading = ref(false)
const expandedId = ref<number | null>(null)
const expandedContent = ref<string | null>(null)
const restoring = ref(false)

async function loadVersions() {
  loading.value = true
  expandedId.value = null
  expandedContent.value = null
  try {
    versions.value = await listNodeVersions(props.projectId, props.nodeId)
  } catch {
    ElMessage.error('加载版本历史失败')
  } finally {
    loading.value = false
  }
}

async function toggleExpand(ver: NodeVersionListItem) {
  if (expandedId.value === ver.id) {
    expandedId.value = null
    expandedContent.value = null
    return
  }
  expandedId.value = ver.id
  // Load full content from version list (content is included in full response)
  // For list items without content, fetch individually
  expandedContent.value = null
  try {
    const { default: request } = await import('@/utils/request')
    const full = await request.get<NodeVersion>(
      `/drama/${props.projectId}/nodes/${props.nodeId}/versions`
    )
    // Find the version in the full list — actually let's just re-fetch with content
    // Simpler: use a dedicated endpoint or include content in list
    // For now, fetch all versions (they include content in the full response model)
    const allVersions = await listNodeVersions(props.projectId, props.nodeId) as unknown as NodeVersion[]
    const target = allVersions.find(v => v.id === ver.id)
    expandedContent.value = target?.content ?? '(无内容)'
  } catch {
    expandedContent.value = '(加载失败)'
  }
}

async function handleRestore(ver: NodeVersionListItem) {
  try {
    await ElMessageBox.confirm(
      `确定恢复到 v${ver.version_number}？当前内容将自动保存为新版本。`,
      '恢复确认',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' },
    )
    restoring.value = true
    await restoreNodeVersion(props.projectId, props.nodeId, ver.id)
    ElMessage.success('已恢复')
    emit('restored')
    visible.value = false
  } catch (e: unknown) {
    if (e !== 'cancel' && (e as { toString?: () => string })?.toString?.() !== 'cancel') {
      ElMessage.error('恢复失败')
    }
  } finally {
    restoring.value = false
  }
}

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    init: '初始',
    ai_apply: 'AI应用',
    switch: '切换',
    manual: '手动',
  }
  return map[source] || source
}

function sourceTagType(source: string): '' | 'success' | 'warning' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'info'> = {
    init: 'info',
    ai_apply: 'warning',
    switch: '',
    manual: 'success',
  }
  return map[source] || 'info'
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped>
.version-list {
  max-height: 480px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-item {
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.version-item--active {
  border-color: #6B7B8D;
}

.version-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.version-header:hover {
  background: #F7F6F3;
}

.version-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-number {
  font-size: 13px;
  font-weight: 600;
  color: #6B7B8D;
  min-width: 28px;
}

.version-title {
  font-size: 13px;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.version-time {
  font-size: 12px;
  color: #9E9E9E;
  flex-shrink: 0;
}

.version-content {
  border-top: 1px solid #E0DFDC;
  padding: 12px 14px;
  background: #FAFAF9;
}

.content-preview {
  font-size: 13px;
  line-height: 1.6;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0 0 10px;
  background: white;
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #ECEAE6;
}

.version-actions {
  text-align: right;
}
</style>
```

**Note:** The `toggleExpand` function above has a problem — `listNodeVersions` returns `NodeVersionListItem` which may not include `content`. This will be fixed in Task 6 by changing the list endpoint to include content, since episode content is bounded and we won't have many versions (max 20).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/drama/VersionHistoryDialog.vue
git commit -m "feat(drama): add VersionHistoryDialog component"
```

---

### Task 6: Fix version list to include content

The list endpoint should return full content so the dialog can show previews without extra requests.

**Files:**
- Modify: `backend/app/routers/drama.py` — change list endpoint response model to `list[NodeVersionResponse]`

- [ ] **Step 1: Update list endpoint response model**

Change the GET versions endpoint from `response_model=list[NodeVersionListResponse]` to `response_model=list[NodeVersionResponse]`.

- [ ] **Step 2: Simplify the dialog's toggleExpand**

In `VersionHistoryDialog.vue`, replace the `toggleExpand` function:

```typescript
async function toggleExpand(ver: NodeVersionListItem) {
  if (expandedId.value === ver.id) {
    expandedId.value = null
    expandedContent.value = null
    return
  }
  expandedId.value = ver.id
  expandedContent.value = (ver as unknown as NodeVersion).content ?? '(无内容)'
}
```

And update `loadVersions` to cast properly:

```typescript
async function loadVersions() {
  loading.value = true
  expandedId.value = null
  expandedContent.value = null
  try {
    versions.value = await listNodeVersions(props.projectId, props.nodeId) as unknown as NodeVersion[]
  } catch {
    ElMessage.error('加载版本历史失败')
  } finally {
    loading.value = false
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/drama.py frontend/src/components/drama/VersionHistoryDialog.vue
git commit -m "fix(drama): include content in version list response for preview"
```

---

### Task 7: Frontend — Wire Up ScriptEditor

**Files:**
- Modify: `frontend/src/components/drama/ScriptEditor.vue:14-29`

- [ ] **Step 1: Add "历史版本" button in editor header**

In `ScriptEditor.vue`, import the dialog and add the button. Modify the `<template>` section.

After the existing `header-actions` div (line 25-28), add the version button:

```html
        <div class="header-actions">
          <el-button
            v-if="node.node_type === 'episode'"
            size="small"
            text
            @click="showVersions = true"
          >
            <el-icon><Clock /></el-icon>
            历史版本
          </el-button>
          <el-tag v-if="node.is_completed" type="success" size="small" effect="plain">已完成</el-tag>
          <span v-if="saveStatus" class="save-status">{{ saveStatus }}</span>
        </div>
```

After the closing `</template>` of the main content, before `</template>` root close, add:

```html
    <VersionHistoryDialog
      v-if="node?.node_type === 'episode'"
      v-model="showVersions"
      :project-id="projectId"
      :node-id="node.id"
      @restored="emit('version-restored')"
    />
```

In `<script setup>`, add:

```typescript
import { Clock } from '@element-plus/icons-vue'
import VersionHistoryDialog from './VersionHistoryDialog.vue'

// Add new prop
const props = defineProps<{
  node: ScriptNode | null
  scriptType: 'explanatory' | 'dynamic'
  projectId: number  // NEW
}>()

// Add new emit
const emit = defineEmits<{
  (e: 'save', data: { title?: string; content?: string; speaker?: string; visual_desc?: string }): void
  (e: 'version-restored'): void  // NEW
}>()

const showVersions = ref(false)
```

- [ ] **Step 2: Pass projectId prop from DramaWorkbenchView**

In `DramaWorkbenchView.vue`, find the `<ScriptEditor` usage and add `:project-id="projectId"`:

```html
        <ScriptEditor
          :node="dramaStore.currentNode"
          :script-type="dramaStore.currentProject?.script_type || 'dynamic'"
          :project-id="projectId"
          @save="handleSaveNode"
          @version-restored="handleVersionRestored"
        />
```

Add the handler:

```typescript
async function handleVersionRestored() {
  // Reload the node to reflect restored content
  await dramaStore.fetchNodes(projectId.value)
  if (dramaStore.currentNode) {
    const updated = dramaStore.nodes.find(n => n.id === dramaStore.currentNode?.id)
    if (updated) dramaStore.selectNode(updated)
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/drama/ScriptEditor.vue frontend/src/views/DramaWorkbenchView.vue
git commit -m "feat(drama): add version history button and dialog to editor"
```

---

### Task 8: Frontend — Auto-Snapshot on AI Apply and Node Switch

**Files:**
- Modify: `frontend/src/views/DramaWorkbenchView.vue:280-360`

- [ ] **Step 1: Modify handleApplyAiText to create snapshot first**

Replace `handleApplyAiText` (line 357-360):

```typescript
async function handleApplyAiText(text: string) {
  if (!dramaStore.currentNode) return
  // Snapshot before AI apply (only for episode nodes)
  if (dramaStore.currentNode.node_type === 'episode') {
    try {
      await createNodeVersion(projectId.value, dramaStore.currentNode.id, 'ai_apply')
    } catch {
      // Snapshot failure should not block apply
    }
  }
  handleSaveNode({ content: text })
}
```

Add import at top:

```typescript
import { createNodeVersion } from '@/api/drama'
```

- [ ] **Step 2: Modify handleSelectNode to snapshot on switch**

Replace `handleSelectNode` (line 281-283):

```typescript
// Track loaded content for dirty checking
const loadedNodeContent = ref<string | null>(null)

watch(() => dramaStore.currentNode, (node) => {
  loadedNodeContent.value = node?.content ?? null
})

async function handleSelectNode(node: ScriptNode) {
  const prev = dramaStore.currentNode
  // Snapshot if switching away from a dirty episode
  if (
    prev &&
    prev.node_type === 'episode' &&
    prev.id !== node.id &&
    prev.content !== loadedNodeContent.value
  ) {
    try {
      await createNodeVersion(projectId.value, prev.id, 'switch')
    } catch {
      // Snapshot failure should not block switch
    }
  }
  dramaStore.selectNode(node)
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/DramaWorkbenchView.vue
git commit -m "feat(drama): auto-snapshot on AI apply and node switch"
```

---

### Task 9: Build, Deploy, and Verify

- [ ] **Step 1: Rebuild backend**

```bash
docker compose build backend && docker compose up -d backend
```

Verify table created:
```bash
docker compose exec backend python -c "
from app.core.database import engine
from app.models import ScriptNodeVersion
import asyncio
async def check():
    async with engine.begin() as conn:
        from sqlalchemy import inspect
        def get_tables(conn):
            inspector = inspect(conn)
            return inspector.get_table_names()
        tables = await conn.run_sync(get_tables)
        print('script_node_versions' in tables)
asyncio.run(check())
"
```

Expected: `True`

- [ ] **Step 2: Rebuild frontend**

```bash
docker compose build frontend && docker compose up -d frontend
```

- [ ] **Step 3: Manual verification checklist**

1. Open a drama project workbench
2. Select an episode node — "历史版本" button visible in editor header
3. Select a non-episode node — button hidden
4. Click "历史版本" — dialog opens, shows versions (or empty for old projects)
5. Create a new project, go through wizard, confirm outline — initial versions created
6. Use AI to expand/rewrite an episode, click "应用" — old content saved as version
7. Open "历史版本" — see the ai_apply version
8. Click a version to expand and preview content
9. Click "恢复此版本" — confirm dialog appears, content restores, editor updates

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(drama): complete episode version history feature"
```
