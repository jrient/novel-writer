<template>
  <div class="adaptation-create">
    <h2>新建剧本改编</h2>

    <!-- 区块 1：标题 + 导入/粘贴 -->
    <el-card class="block">
      <template #header><strong>① 导入剧本</strong></template>
      <el-form label-width="100px">
        <el-form-item label="标题">
          <el-input v-model="title" placeholder="给这次改编起个名字" />
        </el-form-item>
        <el-form-item label="来源">
          <el-radio-group v-model="sourceMode">
            <el-radio value="paste">粘贴文本</el-radio>
            <el-radio value="upload">上传文件</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="sourceMode === 'paste'" label="原文">
          <el-input v-model="rawText" type="textarea" :rows="10" />
        </el-form-item>
        <el-form-item v-else label="文件">
          <el-upload :auto-upload="false" :on-change="onFileChange" :limit="1" :file-list="fileList">
            <el-button>选择 .txt / .docx</el-button>
          </el-upload>
        </el-form-item>
        <el-button type="primary" :loading="creating" @click="onCreate">创建项目</el-button>
      </el-form>
    </el-card>

    <!-- 区块 2：抽实体 + 映射表 -->
    <el-card v-if="project" class="block">
      <template #header>
        <div class="block-head">
          <strong>② 实体映射</strong>
          <div>
            <el-button :loading="extracting" @click="onExtract">AI 抽实体</el-button>
            <el-button :loading="suggesting" @click="onSuggest">AI 建议替换</el-button>
          </div>
        </div>
      </template>
      <el-table :data="mappings" size="small" empty-text="尚未抽取，点击「AI 抽实体」">
        <el-table-column prop="entity_type" label="类型" width="100">
          <template #default="{row}">
            <el-select v-model="row.entity_type" size="small">
              <el-option v-for="t in entityTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="原文" width="180">
          <template #default="{row}"><el-input v-model="row.original_text" size="small" /></template>
        </el-table-column>
        <el-table-column label="替换为" width="180">
          <template #default="{row}">
            <el-input v-model="row.replacement_text" size="small" placeholder="留空=待 AI 建议" />
          </template>
        </el-table-column>
        <el-table-column label="锁定" width="60">
          <template #default="{row}"><el-checkbox v-model="row.locked" /></template>
        </el-table-column>
        <el-table-column label="备注">
          <template #default="{row}"><el-input v-model="row.notes" size="small" /></template>
        </el-table-column>
        <el-table-column label="" width="60">
          <template #default="{$index}">
            <el-button link type="danger" @click="mappings.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="block-actions">
        <el-button size="small" @click="addMapping">添加一行</el-button>
        <el-button size="small" type="primary" @click="saveMappings">保存映射</el-button>
      </div>
    </el-card>

    <!-- 区块 3：强度 + 意图 + 设定 -->
    <el-card v-if="project" class="block">
      <template #header><strong>③ 改编强度与设定</strong></template>
      <el-form label-width="100px">
        <el-form-item label="强度">
          <el-slider v-model="intensity" :min="1" :max="3" :marks="{1:'替换', 2:'润色', 3:'重铸'}" />
        </el-form-item>
        <el-form-item label="改编意图">
          <el-input v-model="intent" type="textarea" :rows="2" placeholder="如：改成 1990 年代上海背景" />
        </el-form-item>
        <el-form-item label="新设定">
          <el-input v-model="eraTarget" type="textarea" :rows="3" placeholder="新时代/世界设定的细节描述" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块 4：切场预览 -->
    <el-card v-if="project" class="block">
      <template #header>
        <div class="block-head">
          <strong>④ 场切分预览</strong>
          <el-button :loading="splitting" @click="onSplit">{{ project.scene_boundaries.length ? '重新切场' : '开始切场' }}</el-button>
        </div>
      </template>
      <el-collapse v-if="project.scene_boundaries.length">
        <el-collapse-item v-for="b in project.scene_boundaries" :key="b.index" :title="`场 ${b.index + 1}：${b.title}`">
          <div class="scene-preview">字符 {{ b.start }} - {{ b.end }}（{{ b.end - b.start }} 字）</div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="尚未切场" />
    </el-card>

    <div v-if="project && project.scene_boundaries.length" class="footer-actions">
      <el-button size="large" type="primary" @click="goWorkbench">进入工作台开始改编 →</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adaptationApi, type AdaptationProject, type EntityType, type MappingEntry } from '@/api/adaptation'

const router = useRouter()

const sourceMode = ref<'paste' | 'upload'>('paste')
const title = ref('')
const rawText = ref('')
const fileList = ref<any[]>([])
const intensity = ref(2)
const intent = ref('')
const eraTarget = ref('')

const project = ref<AdaptationProject | null>(null)
const mappings = ref<MappingEntry[]>([])
const entityTypes: EntityType[] = ['person', 'place', 'prop', 'era_term', 'other']

const creating = ref(false)
const extracting = ref(false)
const suggesting = ref(false)
const splitting = ref(false)

function onFileChange(file: any) { fileList.value = [file] }

async function onCreate() {
  if (!title.value.trim()) { ElMessage.warning('请填标题'); return }
  creating.value = true
  try {
    let r
    if (sourceMode.value === 'paste') {
      r = await adaptationApi.createWithText({
        title: title.value, raw_text: rawText.value,
        intent: intent.value || undefined, intensity: intensity.value,
        era_target: eraTarget.value || undefined,
      })
    } else {
      const fm = new FormData()
      fm.append('title', title.value)
      fm.append('intensity', String(intensity.value))
      if (intent.value) fm.append('intent', intent.value)
      if (eraTarget.value) fm.append('era_target', eraTarget.value)
      fm.append('file', fileList.value[0]?.raw)
      r = await adaptationApi.createWithUpload(fm)
    }
    project.value = r as any
    mappings.value = (r as any).mappings || []
    ElMessage.success('项目已创建，可继续抽实体/切场')
  } finally { creating.value = false }
}

async function onExtract() {
  if (!project.value) return
  extracting.value = true
  try {
    const r = await adaptationApi.extract(project.value.id)
    project.value = r as any; mappings.value = (r as any).mappings
    ElMessage.success(`抽出 ${(r as any).mappings.length} 条`)
  } finally { extracting.value = false }
}

async function onSuggest() {
  if (!project.value) return
  suggesting.value = true
  try {
    await saveMappings()
    const r = await adaptationApi.suggestMappings(project.value.id)
    mappings.value = r as any
  } finally { suggesting.value = false }
}

function addMapping() {
  mappings.value.push({entity_type: 'person', original_text: '', replacement_text: '', locked: false, notes: '', order_index: mappings.value.length})
}

async function saveMappings() {
  if (!project.value) return
  for (let i = 0; i < mappings.value.length; i++) mappings.value[i].order_index = i
  await adaptationApi.putMappings(project.value.id, mappings.value)
  await adaptationApi.update(project.value.id, {
    intent: intent.value, intensity: intensity.value, era_target: eraTarget.value,
  })
  ElMessage.success('已保存')
}

async function onSplit() {
  if (!project.value) return
  await saveMappings()
  splitting.value = true
  try {
    const r = await adaptationApi.split(project.value.id)
    project.value = r as any
    ElMessage.success(`切出 ${(r as any).scene_boundaries.length} 场`)
  } finally { splitting.value = false }
}

function goWorkbench() {
  if (!project.value) return
  router.push(`/adaptation/workbench/${project.value.id}`)
}
</script>

<style scoped>
.adaptation-create { padding: 24px; max-width: 1000px; margin: 0 auto; }
.block { margin-bottom: 16px; }
.block-head { display: flex; justify-content: space-between; align-items: center; }
.block-actions { margin-top: 12px; display: flex; gap: 8px; }
.scene-preview { color: #606266; }
.footer-actions { display: flex; justify-content: center; padding: 16px 0; }
</style>
