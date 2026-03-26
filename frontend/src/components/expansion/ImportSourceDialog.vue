<template>
  <el-dialog
    v-model="visible"
    title="从平台导入"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-tabs v-model="activeTab">
      <!-- 从小说导入 -->
      <el-tab-pane label="从小说导入" name="novel">
        <div class="import-form">
          <el-form label-width="80px">
            <el-form-item label="选择小说">
              <el-select
                v-model="selectedNovelId"
                placeholder="请选择小说项目"
                style="width: 100%"
                @change="handleNovelSelect"
              >
                <el-option
                  v-for="project in novelProjects"
                  :key="project.id"
                  :label="project.title"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item v-if="selectedNovelId && chapters.length > 0" label="选择章节">
              <el-checkbox-group v-model="selectedChapterIds" class="chapter-list">
                <el-checkbox
                  v-for="chapter in chapters"
                  :key="chapter.id"
                  :label="chapter.id"
                  class="chapter-item"
                >
                  {{ chapter.title || `第${chapter.chapter_number}章` }}
                  <span class="word-count">({{ chapter.word_count || 0 }} 字)</span>
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <el-form-item v-if="selectedChapterIds.length > 0" label="统计">
              <div class="stats-info">
                已选择 {{ selectedChapterIds.length }} 章，共 {{ totalWordCount.toLocaleString() }} 字
              </div>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 从剧本导入 -->
      <el-tab-pane label="从剧本导入" name="drama">
        <div class="import-form">
          <el-form label-width="80px">
            <el-form-item label="选择剧本">
              <el-select
                v-model="selectedDramaId"
                placeholder="请选择剧本项目"
                style="width: 100%"
                @change="handleDramaSelect"
              >
                <el-option
                  v-for="project in dramaProjects"
                  :key="project.id"
                  :label="project.title"
                  :value="project.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item v-if="selectedDramaProject" label="剧本信息">
              <div class="drama-info">
                <div class="info-row">
                  <span class="label">类型：</span>
                  <span>{{ selectedDramaProject.script_type === 'explanatory' ? '解说漫' : '动态漫' }}</span>
                </div>
                <div class="info-row">
                  <span class="label">状态：</span>
                  <span>{{ dramaStatusLabel(selectedDramaProject.status) }}</span>
                </div>
              </div>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="importing" :disabled="!canImport" @click="handleImport">
        确认导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

interface Project {
  id: number
  title: string
}

interface Chapter {
  id: number
  chapter_number: number
  title: string | null
  word_count: number
}

interface DramaProject {
  id: number
  title: string
  script_type: string
  status: string
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'import': [data: { source: 'novel' | 'drama'; projectId: number; chapterIds?: number[] }]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const activeTab = ref<'novel' | 'drama'>('novel')
const novelProjects = ref<Project[]>([])
const dramaProjects = ref<DramaProject[]>([])
const chapters = ref<Chapter[]>([])
const selectedNovelId = ref<number | null>(null)
const selectedDramaId = ref<number | null>(null)
const selectedChapterIds = ref<number[]>([])
const importing = ref(false)

const selectedDramaProject = computed(() => {
  if (!selectedDramaId.value) return null
  return dramaProjects.value.find((p) => p.id === selectedDramaId.value) || null
})

const totalWordCount = computed(() => {
  return chapters.value
    .filter((c) => selectedChapterIds.value.includes(c.id))
    .reduce((sum, c) => sum + (c.word_count || 0), 0)
})

const canImport = computed(() => {
  if (activeTab.value === 'novel') {
    return selectedNovelId.value && selectedChapterIds.value.length > 0
  }
  return selectedDramaId.value !== null
})

function dramaStatusLabel(status: string): string {
  const map: Record<string, string> = {
    drafting: '草稿',
    outlined: '已大纲',
    writing: '创作中',
    completed: '已完成',
  }
  return map[status] || status
}

async function fetchNovelProjects() {
  try {
    const res = await request.get<{ items: Project[] }>('/projects/')
    novelProjects.value = res.items || []
  } catch {
    ElMessage.error('获取小说列表失败')
  }
}

async function fetchDramaProjects() {
  try {
    const res = await request.get<DramaProject[]>('/drama/')
    dramaProjects.value = res || []
  } catch {
    ElMessage.error('获取剧本列表失败')
  }
}

async function handleNovelSelect(projectId: number) {
  selectedChapterIds.value = []
  chapters.value = []
  if (!projectId) return

  try {
    const res = await request.get<{ items: Chapter[] }>(`/projects/${projectId}/chapters/`)
    chapters.value = res.items || []
  } catch {
    ElMessage.error('获取章节列表失败')
  }
}

function handleDramaSelect() {
  // Drama selected, no additional data needed
}

async function handleImport() {
  importing.value = true
  try {
    if (activeTab.value === 'novel' && selectedNovelId.value) {
      emit('import', {
        source: 'novel',
        projectId: selectedNovelId.value,
        chapterIds: selectedChapterIds.value,
      })
    } else if (activeTab.value === 'drama' && selectedDramaId.value) {
      emit('import', {
        source: 'drama',
        projectId: selectedDramaId.value,
      })
    }
    handleClose()
  } finally {
    importing.value = false
  }
}

function handleClose() {
  visible.value = false
  selectedNovelId.value = null
  selectedDramaId.value = null
  selectedChapterIds.value = []
  chapters.value = []
}

watch(visible, (val) => {
  if (val) {
    fetchNovelProjects()
    fetchDramaProjects()
  }
})
</script>

<style scoped>
.import-form {
  min-height: 200px;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.chapter-item {
  display: flex;
  align-items: center;
}

.word-count {
  font-size: 12px;
  color: #9E9E9E;
  margin-left: 8px;
}

.stats-info {
  font-size: 14px;
  color: #6B7B8D;
  font-weight: 500;
}

.drama-info {
  background: #F5F5F5;
  padding: 12px;
  border-radius: 8px;
}

.info-row {
  display: flex;
  gap: 8px;
  font-size: 14px;
  line-height: 1.8;
}

.info-row .label {
  color: #9E9E9E;
}
</style>