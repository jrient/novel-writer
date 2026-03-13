<template>
  <div class="event-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">事件管理</span>
      <div class="header-actions">
        <el-button size="small" @click="showPlotlineDialog = true">
          <el-icon><Connection /></el-icon> 剧情线
        </el-button>
        <el-button size="small" type="primary" :icon="Plus" @click="openCreateEvent">
          新增事件
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-row">
        <span class="filter-label">剧情线</span>
        <div class="plotline-filters">
          <el-tag
            class="plotline-tag clickable"
            :effect="eventStore.filterPlotlineId === null ? 'dark' : 'plain'"
            @click="eventStore.filterPlotlineId = null"
          >全部</el-tag>
          <el-tag
            v-for="pl in eventStore.plotlines"
            :key="pl.id"
            class="plotline-tag clickable"
            :color="eventStore.filterPlotlineId === pl.id ? pl.color : undefined"
            :effect="eventStore.filterPlotlineId === pl.id ? 'dark' : 'plain'"
            @click="eventStore.filterPlotlineId = pl.id"
          >
            <span class="plotline-dot" :style="{ backgroundColor: pl.color }"></span>
            {{ pl.name }}
          </el-tag>
        </div>
      </div>
      <div class="filter-row">
        <span class="filter-label">类型</span>
        <el-radio-group v-model="eventStore.filterEventType" size="small">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="plot_point">情节</el-radio-button>
          <el-radio-button label="turning_point">转折</el-radio-button>
          <el-radio-button label="revelation">揭示</el-radio-button>
          <el-radio-button label="conflict">冲突</el-radio-button>
          <el-radio-button label="resolution">解决</el-radio-button>
          <el-radio-button label="foreshadowing">伏笔</el-radio-button>
          <el-radio-button label="callback">回收</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 事件列表 -->
    <div class="event-list">
      <div v-if="eventStore.loading" class="loading-state">
        <el-skeleton :rows="3" animated />
      </div>

      <div v-else-if="eventStore.filteredEvents.length === 0" class="empty-state">
        <el-empty description="暂无事件" :image-size="60">
          <el-button type="primary" size="small" @click="openCreateEvent">创建第一个事件</el-button>
        </el-empty>
      </div>

      <div
        v-else
        v-for="event in eventStore.filteredEvents"
        :key="event.id"
        class="event-card"
        @click="viewEventChain(event)"
      >
        <div class="event-card-header">
          <div class="event-title-row">
            <el-tag size="small" :type="eventTypeTagType(event.event_type)" effect="dark" class="type-tag">
              {{ eventTypeLabel(event.event_type) }}
            </el-tag>
            <span class="event-title">{{ event.title }}</span>
          </div>
          <div class="event-badges">
            <el-tag size="small" :type="importanceTagType(event.importance)" effect="plain">
              {{ importanceLabel(event.importance) }}
            </el-tag>
            <el-tag size="small" :type="statusTagType(event.status)" effect="plain">
              {{ statusLabel(event.status) }}
            </el-tag>
          </div>
        </div>

        <div v-if="event.description" class="event-desc">{{ event.description }}</div>

        <div class="event-meta">
          <span v-if="event.time_label" class="meta-item">
            <el-icon><Timer /></el-icon> {{ event.time_label }}
          </span>
          <span v-if="event.character_ids.length" class="meta-item">
            <el-icon><User /></el-icon> {{ event.character_ids.length }}角色
          </span>
          <span v-if="event.cause_event_ids.length" class="meta-item cause">
            ← {{ event.cause_event_ids.length }}前因
          </span>
          <span v-if="event.effect_event_ids.length" class="meta-item effect">
            → {{ event.effect_event_ids.length }}后果
          </span>
        </div>

        <div v-if="event.plotline_ids.length" class="event-plotlines">
          <span
            v-for="plId in event.plotline_ids"
            :key="plId"
            class="plotline-dot-label"
          >
            <span class="plotline-dot" :style="{ backgroundColor: getPlotlineColor(plId) }"></span>
            {{ getPlotlineName(plId) }}
          </span>
        </div>

        <div class="event-actions">
          <el-button text size="small" :icon="Edit" @click.stop="openEditEvent(event)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click.stop="confirmDeleteEvent(event)">删除</el-button>
        </div>
      </div>
    </div>

    <!-- 事件编辑对话框 -->
    <el-dialog
      :close-on-press-escape="false"
      v-model="showEventDialog"
      :title="editingEvent ? '编辑事件' : '新建事件'"
      width="680px"
      :close-on-click-modal="false"
    >
      <el-form :model="eventForm" label-width="80px" label-position="left">
        <el-form-item label="标题" required>
          <el-input v-model="eventForm.title" placeholder="事件标题" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="eventForm.description" type="textarea" :rows="3" placeholder="事件详细描述..." />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="类型">
              <el-select v-model="eventForm.event_type" style="width: 100%">
                <el-option label="情节点" value="plot_point" />
                <el-option label="转折点" value="turning_point" />
                <el-option label="揭示" value="revelation" />
                <el-option label="冲突" value="conflict" />
                <el-option label="解决" value="resolution" />
                <el-option label="伏笔" value="foreshadowing" />
                <el-option label="回收" value="callback" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="eventForm.status" style="width: 100%">
                <el-option label="计划中" value="planned" />
                <el-option label="已写" value="written" />
                <el-option label="已修订" value="revised" />
                <el-option label="已放弃" value="dropped" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="重要程度">
              <el-select v-model="eventForm.importance" style="width: 100%">
                <el-option label="关键" value="critical" />
                <el-option label="重要" value="major" />
                <el-option label="次要" value="minor" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="时间顺序">
              <el-input-number v-model="eventForm.timeline_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="时间标签">
              <el-input v-model="eventForm.time_label" placeholder="如：第三天清晨" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="剧情线">
          <el-select v-model="eventForm.plotline_ids" multiple style="width: 100%" placeholder="选择剧情线">
            <el-option
              v-for="pl in eventStore.plotlines"
              :key="pl.id"
              :label="pl.name"
              :value="pl.id"
            >
              <span class="plotline-dot" :style="{ backgroundColor: pl.color }"></span>
              {{ pl.name }}
            </el-option>
          </el-select>
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="锚定类型">
              <el-select v-model="eventForm.anchor_type" clearable style="width: 100%" placeholder="选择锚定">
                <el-option label="地图" value="map" />
                <el-option label="部分" value="part" />
                <el-option label="章节" value="chapter" />
                <el-option label="场景" value="scene" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="锚定ID">
              <el-input v-model="eventForm.anchor_id" placeholder="锚定目标ID" :disabled="!eventForm.anchor_type" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="前因事件">
              <el-select v-model="eventForm.cause_event_ids" multiple style="width: 100%" placeholder="选择前因事件">
                <el-option
                  v-for="ev in availableCauseEvents"
                  :key="ev.id"
                  :label="ev.title"
                  :value="ev.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="后果事件">
              <el-select v-model="eventForm.effect_event_ids" multiple style="width: 100%" placeholder="选择后果事件">
                <el-option
                  v-for="ev in availableEffectEvents"
                  :key="ev.id"
                  :label="ev.title"
                  :value="ev.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="标签">
          <el-select
            v-model="eventForm.tags"
            multiple
            filterable
            allow-create
            default-first-option
            style="width: 100%"
            placeholder="输入标签并回车"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEventDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>

    <!-- 剧情线管理对话框 -->
    <el-dialog
      v-model="showPlotlineDialog"
      title="剧情线管理"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="plotline-manager">
        <div class="plotline-add-row">
          <el-input v-model="newPlotlineName" placeholder="新剧情线名称" size="small" style="flex: 1" />
          <el-color-picker v-model="newPlotlineColor" size="small" />
          <el-button size="small" type="primary" :disabled="!newPlotlineName.trim()" @click="addPlotline">添加</el-button>
        </div>

        <div v-if="eventStore.plotlines.length === 0" class="plotline-empty">
          暂无剧情线，请添加
        </div>

        <div v-for="pl in eventStore.plotlines" :key="pl.id" class="plotline-item">
          <template v-if="editingPlotlineId === pl.id">
            <el-input v-model="editPlotlineForm.name" size="small" style="flex: 1" />
            <el-color-picker v-model="editPlotlineForm.color" size="small" />
            <el-button size="small" type="primary" text @click="savePlotlineEdit(pl.id)">保存</el-button>
            <el-button size="small" text @click="editingPlotlineId = null">取消</el-button>
          </template>
          <template v-else>
            <span class="plotline-dot" :style="{ backgroundColor: pl.color }"></span>
            <span class="plotline-name">{{ pl.name }}</span>
            <span v-if="pl.description" class="plotline-desc">{{ pl.description }}</span>
            <div class="plotline-actions">
              <el-button text size="small" :icon="Edit" @click="startEditPlotline(pl)" />
              <el-button text size="small" type="danger" :icon="Delete" @click="confirmDeletePlotline(pl)" />
            </div>
          </template>
        </div>
      </div>
    </el-dialog>

    <!-- 因果链对话框 -->
    <el-dialog
      v-model="showChainDialog"
      title="因果链"
      width="600px"
    >
      <div v-if="eventStore.currentChain" class="chain-view">
        <div v-if="eventStore.currentChain.causes.length" class="chain-section">
          <h4>前因事件</h4>
          <div v-for="ev in eventStore.currentChain.causes" :key="ev.id" class="chain-event cause">
            <el-tag size="small" :type="eventTypeTagType(ev.event_type)" effect="dark">{{ eventTypeLabel(ev.event_type) }}</el-tag>
            <span>{{ ev.title }}</span>
          </div>
        </div>

        <div class="chain-section current">
          <h4>当前事件</h4>
          <div class="chain-event">
            <el-tag size="small" :type="eventTypeTagType(eventStore.currentChain.current.event_type)" effect="dark">
              {{ eventTypeLabel(eventStore.currentChain.current.event_type) }}
            </el-tag>
            <strong>{{ eventStore.currentChain.current.title }}</strong>
          </div>
          <p v-if="eventStore.currentChain.current.description" class="chain-desc">
            {{ eventStore.currentChain.current.description }}
          </p>
        </div>

        <div v-if="eventStore.currentChain.effects.length" class="chain-section">
          <h4>后果事件</h4>
          <div v-for="ev in eventStore.currentChain.effects" :key="ev.id" class="chain-event effect">
            <el-tag size="small" :type="eventTypeTagType(ev.event_type)" effect="dark">{{ eventTypeLabel(ev.event_type) }}</el-tag>
            <span>{{ ev.title }}</span>
          </div>
        </div>

        <div v-if="!eventStore.currentChain.causes.length && !eventStore.currentChain.effects.length" class="chain-empty">
          该事件暂无关联的因果链
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete, Timer, User, Connection } from '@element-plus/icons-vue'
import { useEventStore } from '@/stores/event'
import type { StoryEvent, CreateEventData, UpdateEventData, Plotline } from '@/api/event'

const props = defineProps<{
  projectId: number
}>()

const eventStore = useEventStore()

// 对话框状态
const showEventDialog = ref(false)
const showPlotlineDialog = ref(false)
const showChainDialog = ref(false)
const editingEvent = ref<StoryEvent | null>(null)
const saving = ref(false)

// 事件表单
const defaultEventForm = (): CreateEventData & { plotline_ids: number[]; cause_event_ids: number[]; effect_event_ids: number[]; tags: string[] } => ({
  title: '',
  description: '',
  event_type: 'plot_point',
  status: 'planned',
  importance: 'major',
  timeline_order: 0,
  time_label: '',
  anchor_type: undefined,
  anchor_id: undefined,
  plotline_ids: [],
  character_ids: [],
  cause_event_ids: [],
  effect_event_ids: [],
  tags: [],
})
const eventForm = ref(defaultEventForm())

// 剧情线表单
const newPlotlineName = ref('')
const newPlotlineColor = ref('#6B7B8D')
const editingPlotlineId = ref<number | null>(null)
const editPlotlineForm = ref({ name: '', color: '', description: '' })

// 计算可选因果事件（排除当前编辑事件）
const availableCauseEvents = computed(() => {
  return eventStore.events.filter(e => e.id !== editingEvent.value?.id)
})
const availableEffectEvents = computed(() => {
  return eventStore.events.filter(e => e.id !== editingEvent.value?.id)
})

// ============ 标签映射 ============

function eventTypeLabel(type: string) {
  const map: Record<string, string> = {
    plot_point: '情节', turning_point: '转折', revelation: '揭示',
    conflict: '冲突', resolution: '解决', foreshadowing: '伏笔', callback: '回收',
  }
  return map[type] || type
}

function eventTypeTagType(type: string) {
  const map: Record<string, string> = {
    plot_point: '', turning_point: 'warning', revelation: 'success',
    conflict: 'danger', resolution: 'info', foreshadowing: 'warning', callback: 'success',
  }
  return map[type] || ''
}

function importanceLabel(imp: string) {
  const map: Record<string, string> = { critical: '关键', major: '重要', minor: '次要' }
  return map[imp] || imp
}

function importanceTagType(imp: string) {
  const map: Record<string, string> = { critical: 'danger', major: 'warning', minor: 'info' }
  return map[imp] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { planned: '计划中', written: '已写', revised: '已修订', dropped: '已放弃' }
  return map[status] || status
}

function statusTagType(status: string) {
  const map: Record<string, string> = { planned: 'info', written: 'success', revised: '', dropped: 'danger' }
  return map[status] || 'info'
}

function getPlotlineColor(id: number) {
  return eventStore.getPlotlineById(id)?.color || '#999'
}

function getPlotlineName(id: number) {
  return eventStore.getPlotlineById(id)?.name || '未知'
}

// ============ 事件操作 ============

function openCreateEvent() {
  editingEvent.value = null
  eventForm.value = defaultEventForm()
  // 自动设置 timeline_order 为当前最大值 + 1
  const maxOrder = eventStore.events.reduce((max, e) => Math.max(max, e.timeline_order), -1)
  eventForm.value.timeline_order = maxOrder + 1
  showEventDialog.value = true
}

function openEditEvent(event: StoryEvent) {
  editingEvent.value = event
  eventForm.value = {
    title: event.title,
    description: event.description || '',
    event_type: event.event_type,
    status: event.status,
    importance: event.importance,
    timeline_order: event.timeline_order,
    time_label: event.time_label || '',
    anchor_type: event.anchor_type || undefined,
    anchor_id: event.anchor_id || undefined,
    plotline_ids: [...event.plotline_ids],
    character_ids: [...event.character_ids],
    cause_event_ids: [...event.cause_event_ids],
    effect_event_ids: [...event.effect_event_ids],
    tags: [...event.tags],
  }
  showEventDialog.value = true
}

async function saveEvent() {
  if (!eventForm.value.title.trim()) {
    ElMessage.warning('请输入事件标题')
    return
  }
  saving.value = true
  try {
    if (editingEvent.value) {
      await eventStore.updateEvent(props.projectId, editingEvent.value.id, eventForm.value as UpdateEventData)
      ElMessage.success('事件已更新')
    } else {
      await eventStore.createNewEvent(props.projectId, eventForm.value as CreateEventData)
      ElMessage.success('事件已创建')
    }
    showEventDialog.value = false
  } catch {
    // error handled by interceptor
  } finally {
    saving.value = false
  }
}

async function confirmDeleteEvent(event: StoryEvent) {
  try {
    await ElMessageBox.confirm(`确定删除事件「${event.title}」？`, '确认删除', { type: 'warning' })
    await eventStore.removeEvent(props.projectId, event.id)
    ElMessage.success('事件已删除')
  } catch {
    // cancelled
  }
}

async function viewEventChain(event: StoryEvent) {
  try {
    await eventStore.fetchEventChain(props.projectId, event.id)
    showChainDialog.value = true
  } catch {
    // error handled by interceptor
  }
}

// ============ 剧情线操作 ============

async function addPlotline() {
  if (!newPlotlineName.value.trim()) return
  try {
    await eventStore.createNewPlotline(props.projectId, {
      name: newPlotlineName.value.trim(),
      color: newPlotlineColor.value,
    })
    newPlotlineName.value = ''
    newPlotlineColor.value = '#6B7B8D'
    ElMessage.success('剧情线已添加')
  } catch {
    // error handled by interceptor
  }
}

function startEditPlotline(pl: Plotline) {
  editingPlotlineId.value = pl.id
  editPlotlineForm.value = { name: pl.name, color: pl.color, description: pl.description || '' }
}

async function savePlotlineEdit(id: number) {
  try {
    await eventStore.updatePlotline(props.projectId, id, editPlotlineForm.value)
    editingPlotlineId.value = null
    ElMessage.success('剧情线已更新')
  } catch {
    // error handled by interceptor
  }
}

async function confirmDeletePlotline(pl: Plotline) {
  try {
    await ElMessageBox.confirm(`确定删除剧情线「${pl.name}」？`, '确认删除', { type: 'warning' })
    await eventStore.removePlotline(props.projectId, pl.id)
    ElMessage.success('剧情线已删除')
  } catch {
    // cancelled
  }
}

// ============ 初始化 ============

onMounted(async () => {
  await Promise.all([
    eventStore.fetchPlotlines(props.projectId),
    eventStore.fetchEvents(props.projectId),
  ])
})
</script>

<style scoped>
.event-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  flex-shrink: 0;
  margin-bottom: 16px;
  padding: 12px;
  background: white;
  border-radius: 8px;
  border: 1px solid #E0DFDC;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-label {
  font-size: 13px;
  color: #7A7A7A;
  white-space: nowrap;
  min-width: 42px;
}

.plotline-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.plotline-tag.clickable {
  cursor: pointer;
}

.plotline-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.event-list {
  flex: 1;
  overflow-y: auto;
}

.loading-state,
.empty-state {
  padding: 40px 0;
  text-align: center;
}

.event-card {
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.event-card:hover {
  border-color: #6B7B8D;
  box-shadow: 0 2px 8px rgba(107, 123, 141, 0.1);
}

.event-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 6px;
}

.event-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-tag {
  flex-shrink: 0;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
}

.event-badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.event-desc {
  font-size: 13px;
  color: #7A7A7A;
  margin-bottom: 8px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.event-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #999;
  margin-bottom: 6px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 2px;
}

.meta-item.cause {
  color: #E6A23C;
}

.meta-item.effect {
  color: #409EFF;
}

.event-plotlines {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.plotline-dot-label {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #5C5C5C;
}

.event-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 4px;
}

/* 剧情线管理 */
.plotline-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plotline-add-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.plotline-empty {
  text-align: center;
  color: #999;
  padding: 20px;
}

.plotline-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #F7F6F3;
  border-radius: 6px;
}

.plotline-name {
  font-weight: 500;
  flex: 1;
}

.plotline-desc {
  color: #999;
  font-size: 12px;
  flex: 1;
}

.plotline-actions {
  display: flex;
  gap: 2px;
  margin-left: auto;
}

/* 因果链视图 */
.chain-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chain-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #7A7A7A;
}

.chain-section.current h4 {
  color: #2C2C2C;
}

.chain-event {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #F7F6F3;
  margin-bottom: 4px;
}

.chain-event.cause {
  border-left: 3px solid #E6A23C;
}

.chain-event.effect {
  border-left: 3px solid #409EFF;
}

.chain-desc {
  font-size: 13px;
  color: #7A7A7A;
  margin: 4px 0 0 0;
  line-height: 1.5;
}

.chain-empty {
  text-align: center;
  color: #999;
  padding: 20px;
}

:deep(.el-radio-button__inner) {
  padding: 5px 10px;
  font-size: 12px;
}
</style>
