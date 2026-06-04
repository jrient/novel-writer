<template>
  <div class="canon-view">
    <!-- 顶部 header -->
    <div class="canon-header">
      <div class="header-left">
        <el-button text :icon="ArrowLeft" @click="goBack">返回</el-button>
        <h2 class="header-title">原作设定校对</h2>
        <el-text v-if="job" type="info" size="small">
          上次任务：{{ jobStatusLabel(job.status) }}
          <span v-if="job.updated_at"> · {{ formatTime(job.updated_at) }}</span>
        </el-text>
      </div>
      <div class="header-right">
        <el-button @click="openCreateDialog" :disabled="extracting">手动新增</el-button>
        <el-button type="primary" :loading="extracting" @click="handleExtract">
          {{ extracting ? '提取中…' : '提取设定' }}
        </el-button>
      </div>
    </div>

    <!-- 提取进度 -->
    <div v-if="extracting" class="progress-bar">
      <el-text type="primary" size="small">{{ phaseLabel }}</el-text>
      <el-progress
        :percentage="progressPct"
        :status="failedChunks > 0 ? 'warning' : (progressPct >= 100 ? 'success' : undefined)"
        :stroke-width="14"
        style="margin-top: 6px"
      />
      <el-text v-if="chunkTotal > 0" type="info" size="small" style="margin-top: 4px; display: block">
        {{ chunkDone }}/{{ chunkTotal }} 分块完成
        <span v-if="failedChunks > 0" style="color: #f56c6c">，{{ failedChunks }} 分块失败</span>
      </el-text>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated style="margin-top: 24px" />

    <!-- 空状态 -->
    <el-empty
      v-else-if="entities.length === 0"
      description="尚未提取，点击上方提取设定"
      style="margin-top: 48px"
    />

    <!-- 实体分组列表（上下堆叠） -->
    <div v-else class="entity-groups">
      <div
        v-for="group in groupedEntities"
        :key="group.type"
        class="entity-group"
      >
        <div class="group-title">
          {{ entityTypeLabel(group.type) }}
          <el-tag size="small" type="info" round>{{ group.items.length }}</el-tag>
        </div>

        <div class="entity-cards">
          <el-card
            v-for="entity in group.items"
            :key="entity.id"
            class="entity-card"
            shadow="hover"
          >
            <div class="card-head">
              <div class="card-name">
                <span class="name-text">{{ entity.canonical_name }}</span>
                <el-tag :type="importanceTagType(entity.importance)" size="small" effect="dark">
                  {{ importanceLabel(entity.importance) }}
                </el-tag>
                <el-tag :type="reviewTagType(entity.review_status)" size="small">
                  {{ reviewLabel(entity.review_status) }}
                </el-tag>
                <el-text type="info" size="small">置信 {{ formatConfidence(entity.confidence) }}</el-text>
              </div>
              <div class="card-ops">
                <el-button text size="small" :icon="Edit" @click="openEditDialog(entity)">编辑</el-button>
                <el-popconfirm
                  title="确认删除该设定？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="handleDelete(entity)"
                >
                  <template #reference>
                    <el-button text size="small" type="danger" :icon="Delete">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>

            <div v-if="entity.aliases.length" class="card-aliases">
              <el-tag
                v-for="alias in entity.aliases"
                :key="alias"
                size="small"
                effect="plain"
                style="margin-right: 4px"
              >{{ alias }}</el-tag>
            </div>

            <div v-if="entity.summary" class="card-summary">{{ entity.summary }}</div>

            <!-- 溯源 -->
            <el-collapse v-if="entity.source_refs.length" class="card-sources">
              <el-collapse-item :name="entity.id">
                <template #title>
                  <el-text type="info" size="small">溯源原文（{{ entity.source_refs.length }}）</el-text>
                </template>
                <div
                  v-for="(ref, idx) in entity.source_refs"
                  :key="idx"
                  class="source-item"
                >
                  <el-text v-if="ref.chapter !== undefined && ref.chapter !== null" type="info" size="small">
                    来源：{{ ref.chapter }}
                  </el-text>
                  <blockquote v-if="ref.quote" class="source-quote">{{ ref.quote }}</blockquote>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-card>
        </div>
      </div>
    </div>

    <!-- 编辑 / 新增 抽屉 -->
    <el-drawer
      v-model="showFormDrawer"
      :title="editingEntity ? '编辑设定' : '手动新增设定'"
      size="460px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="84px" label-position="top">
        <el-form-item label="类型">
          <el-select v-model="form.entity_type" style="width: 100%" :disabled="!!editingEntity">
            <el-option
              v-for="t in entityTypes"
              :key="t"
              :label="entityTypeLabel(t)"
              :value="t"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.canonical_name" placeholder="设定的标准名称" />
        </el-form-item>
        <el-form-item label="别名">
          <el-select
            v-model="form.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            :reserve-keyword="false"
            placeholder="输入后回车添加别名"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="重要度">
          <el-select v-model="form.importance" style="width: 100%">
            <el-option
              v-for="imp in importanceLevels"
              :key="imp"
              :label="importanceLabel(imp)"
              :value="imp"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="简介">
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="5"
            placeholder="对该设定的描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFormDrawer = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Edit, Delete } from '@element-plus/icons-vue'
import { canonApi } from '@/api/canon'
import type {
  CanonEntity,
  CanonEntityCreate,
  CanonEntityType,
  CanonImportance,
  CanonJob,
} from '@/api/canon'

const route = useRoute()
const router = useRouter()
const refId = Number(route.params.id)

const loading = ref(true)
const job = ref<CanonJob | null>(null)
const entities = ref<CanonEntity[]>([])

const extracting = ref(false)
const phase = ref<'idle' | 'chunked' | 'progress' | 'merged' | 'done'>('idle')
const chunkTotal = ref(0)
const chunkDone = ref(0)
const failedChunks = ref(0)
let eventSource: EventSource | null = null

const entityTypes: CanonEntityType[] = [
  'character', 'location', 'ability', 'faction', 'worldrule', 'event',
]
const importanceLevels: CanonImportance[] = ['critical', 'major', 'minor']

// ===== 表单（编辑/新增）=====
const showFormDrawer = ref(false)
const editingEntity = ref<CanonEntity | null>(null)
const saving = ref(false)
const form = ref<{
  entity_type: CanonEntityType
  canonical_name: string
  aliases: string[]
  importance: CanonImportance
  summary: string
}>({
  entity_type: 'character',
  canonical_name: '',
  aliases: [],
  importance: 'major',
  summary: '',
})

const groupedEntities = computed(() => {
  return entityTypes
    .map((type) => ({
      type,
      items: entities.value.filter((e) => e.entity_type === type),
    }))
    .filter((g) => g.items.length > 0)
})

const progressPct = computed(() => {
  if (phase.value === 'merged' || phase.value === 'done') return 100
  if (!chunkTotal.value) return 0
  return Math.min(99, Math.round((chunkDone.value / chunkTotal.value) * 100))
})

const phaseLabel = computed(() => {
  const m: Record<string, string> = {
    idle: '准备中…',
    chunked: '分块中…',
    progress: '提取中…',
    merged: '归并中…',
    done: '完成',
  }
  return m[phase.value] ?? '处理中…'
})

function goBack() {
  router.back()
}

function entityTypeLabel(type: CanonEntityType): string {
  const m: Record<CanonEntityType, string> = {
    character: '人物',
    location: '地点',
    ability: '能力',
    faction: '势力',
    worldrule: '世界观规则',
    event: '关键事件',
  }
  return m[type] ?? type
}

function importanceLabel(imp: CanonImportance): string {
  const m: Record<CanonImportance, string> = {
    critical: '核心',
    major: '重要',
    minor: '次要',
  }
  return m[imp] ?? imp
}

function importanceTagType(imp: CanonImportance): 'danger' | 'warning' | 'info' {
  const m: Record<CanonImportance, 'danger' | 'warning' | 'info'> = {
    critical: 'danger',
    major: 'warning',
    minor: 'info',
  }
  return m[imp] ?? 'info'
}

function reviewLabel(status: string): string {
  const m: Record<string, string> = {
    ai_extracted: 'AI提取',
    user_verified: '已确认',
    user_edited: '已编辑',
    user_added: '手动新增',
  }
  return m[status] ?? status
}

function reviewTagType(status: string): 'info' | 'success' | 'primary' | 'warning' {
  const m: Record<string, 'info' | 'success' | 'primary' | 'warning'> = {
    ai_extracted: 'info',
    user_verified: 'success',
    user_edited: 'primary',
    user_added: 'warning',
  }
  return m[status] ?? 'info'
}

function jobStatusLabel(status: string): string {
  const m: Record<string, string> = {
    pending: '等待中',
    processing: '提取中',
    done: '完成',
    failed: '失败',
  }
  return m[status] ?? status
}

function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

async function loadJob() {
  try {
    job.value = await canonApi.getJob(refId)
  } catch {
    // 无任务记录时静默
    job.value = null
  }
}

async function loadEntities() {
  try {
    entities.value = await canonApi.listEntities(refId)
  } catch {
    // 错误已由拦截器提示
  }
}

function resetProgress() {
  phase.value = 'idle'
  chunkTotal.value = 0
  chunkDone.value = 0
  failedChunks.value = 0
}

async function handleExtract() {
  if (extracting.value) return
  resetProgress()
  extracting.value = true
  try {
    await canonApi.extract(refId)
    await startSSE()
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      // 已有进行中的任务，直接接 SSE 看进度
      await startSSE()
    } else {
      extracting.value = false
      // 错误消息已由拦截器提示
    }
  }
}

async function startSSE() {
  closeSSE()  // 幂等：先关闭可能存在的旧连接，杜绝重复订阅
  try {
    const ticketRes = await canonApi.getStreamTicket(refId)
    const url = canonApi.getStreamUrl(refId, ticketRes.ticket)
    eventSource = new EventSource(url)

    eventSource.onmessage = async (e) => {
      let payload: Record<string, unknown>
      try {
        payload = JSON.parse(e.data)
      } catch {
        // 跳过畸形/非 JSON 帧（心跳、代理注入等）
        return
      }

      switch (payload.event as string) {
        case 'subscribed':
          break
        case 'snapshot':
          // 订阅时后端补发的当前任务快照，作为进度基线（消除订阅竞态/支持刷新恢复）
          if (typeof payload.chunk_total === 'number') chunkTotal.value = payload.chunk_total
          if (typeof payload.chunk_done === 'number') chunkDone.value = payload.chunk_done
          if (typeof payload.failed === 'number') failedChunks.value = payload.failed
          if (payload.status === 'pending') phase.value = 'chunked'
          else if (payload.status === 'processing') phase.value = 'progress'
          break
        case 'chunked':
          phase.value = 'chunked'
          chunkTotal.value = (payload.chunk_total as number) ?? 0
          break
        case 'progress':
          phase.value = 'progress'
          if (typeof payload.chunk_done === 'number') chunkDone.value = payload.chunk_done
          if (typeof payload.failed === 'number') failedChunks.value = payload.failed
          break
        case 'merged':
          phase.value = 'merged'
          break
        case 'done':
          phase.value = 'done'
          closeSSE()
          extracting.value = false
          await loadJob()
          await loadEntities()
          ElMessage.success(`提取完成，共 ${(payload.entity_count as number) ?? entities.value.length} 个设定`)
          break
        case 'failed':
          closeSSE()
          extracting.value = false
          await loadJob()
          ElMessage.error(`提取失败：${(payload.error as string) ?? '未知错误'}`)
          break
      }
    }

    eventSource.onerror = async () => {
      // 若已被 done/failed 分支主动 close（eventSource 置空），忽略尾随的 error，避免重复处理。
      if (!eventSource) return
      // 连接中断：可能是正常完成时服务端关流先于 done 帧到达，也可能是真断连。
      // 与 DB 对账，避免把“已完成”误判为“静默停止”而漏刷新列表。
      closeSSE()
      extracting.value = false
      await loadJob()
      if (job.value?.status === 'done') {
        await loadEntities()
        ElMessage.success('提取完成')
      } else if (job.value?.status === 'failed') {
        ElMessage.error(`提取失败：${job.value.error ?? '未知错误'}`)
      } else if (job.value?.status === 'processing' || job.value?.status === 'pending') {
        ElMessage.warning('进度连接中断，可点击“提取设定”重新接入')
      }
    }
  } catch {
    extracting.value = false
  }
}

function closeSSE() {
  eventSource?.close()
  eventSource = null
}

function openCreateDialog() {
  editingEntity.value = null
  form.value = {
    entity_type: 'character',
    canonical_name: '',
    aliases: [],
    importance: 'major',
    summary: '',
  }
  showFormDrawer.value = true
}

function openEditDialog(entity: CanonEntity) {
  editingEntity.value = entity
  form.value = {
    entity_type: entity.entity_type,
    canonical_name: entity.canonical_name,
    aliases: [...entity.aliases],
    importance: entity.importance,
    summary: entity.summary ?? '',
  }
  showFormDrawer.value = true
}

async function handleSave() {
  if (!form.value.canonical_name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    if (editingEntity.value) {
      await canonApi.updateEntity(refId, editingEntity.value.id, {
        canonical_name: form.value.canonical_name.trim(),
        aliases: form.value.aliases,
        summary: form.value.summary || null,
        importance: form.value.importance,
      })
      ElMessage.success('已更新')
    } else {
      const payload: CanonEntityCreate = {
        entity_type: form.value.entity_type,
        canonical_name: form.value.canonical_name.trim(),
        aliases: form.value.aliases,
        summary: form.value.summary || null,
        attributes: {},
        source_refs: [],
        importance: form.value.importance,
      }
      await canonApi.createEntity(refId, payload)
      ElMessage.success('已新增')
    }
    showFormDrawer.value = false
    await loadEntities()
  } catch {
    // 错误已由拦截器提示
  } finally {
    saving.value = false
  }
}

async function handleDelete(entity: CanonEntity) {
  try {
    await canonApi.deleteEntity(refId, entity.id)
    ElMessage.success('已删除')
    await loadEntities()
  } catch {
    // 错误已由拦截器提示
  }
}

onMounted(async () => {
  if (Number.isNaN(refId)) {
    ElMessage.error('无效的原作 ID')
    router.replace('/projects')
    return
  }
  loading.value = true
  await Promise.all([loadJob(), loadEntities()])
  loading.value = false
  // 若上次任务仍在进行中，接入 SSE 跟进
  if (job.value && (job.value.status === 'pending' || job.value.status === 'processing')) {
    extracting.value = true
    chunkTotal.value = job.value.chunk_total
    chunkDone.value = job.value.chunk_done
    failedChunks.value = job.value.failed_chunks
    phase.value = 'progress'
    await startSSE()
  }
})

onBeforeUnmount(() => {
  closeSSE()
})
</script>

<style scoped>
.canon-view {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}

.canon-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-title {
  margin: 0;
  font-size: 20px;
  color: #2c2c2c;
}

.header-right {
  display: flex;
  gap: 8px;
}

.progress-bar {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f7f6f3;
  border: 1px solid #e0dfdc;
  border-radius: 8px;
}

.entity-groups {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.entity-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #2c2c2c;
  padding-bottom: 6px;
  border-bottom: 2px solid #f0ede6;
}

.entity-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.entity-card :deep(.el-card__body) {
  padding: 14px 16px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.card-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.name-text {
  font-size: 15px;
  font-weight: 600;
  color: #2c2c2c;
}

.card-ops {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.card-aliases {
  margin-top: 8px;
}

.card-summary {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #5c5c5c;
  white-space: pre-wrap;
}

.card-sources {
  margin-top: 8px;
  border-top: none;
}

.card-sources :deep(.el-collapse-item__header) {
  height: 32px;
  line-height: 32px;
  border-bottom: none;
}

.source-item {
  margin-bottom: 10px;
}

.source-quote {
  margin: 4px 0 0;
  padding: 8px 12px;
  background: #f7f6f3;
  border-left: 3px solid #6b7b8d;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #5c5c5c;
  white-space: pre-wrap;
}
</style>
