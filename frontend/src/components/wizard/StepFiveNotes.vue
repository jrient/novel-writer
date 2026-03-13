<template>
  <div class="step-five">
    <div class="step-header">
      <h2>伏笔与灵感</h2>
      <p class="step-desc">记录你的创作灵感、伏笔设计，方便后续写作时参考（可选）</p>
    </div>

    <div class="notes-section">
      <div class="section-header">
        <h3>笔记列表</h3>
        <el-button type="primary" text @click="addNote('note')">
          <el-icon><Plus /></el-icon> 添加笔记
        </el-button>
      </div>

      <div class="note-types">
        <el-button
          :type="activeType === 'all' ? 'primary' : 'default'"
          size="small"
          @click="activeType = 'all'"
        >
          全部 ({{ wizardStore.notes.length }})
        </el-button>
        <el-button
          :type="activeType === 'foreshadowing' ? 'primary' : 'default'"
          size="small"
          @click="activeType = 'foreshadowing'"
        >
          伏笔 ({{ foreshadowingCount }})
        </el-button>
        <el-button
          :type="activeType === 'inspiration' ? 'primary' : 'default'"
          size="small"
          @click="activeType = 'inspiration'"
        >
          灵感 ({{ inspirationCount }})
        </el-button>
        <el-button
          :type="activeType === 'note' ? 'primary' : 'default'"
          size="small"
          @click="activeType = 'note'"
        >
          笔记 ({{ noteCount }})
        </el-button>
      </div>

      <div v-if="filteredNotes.length === 0" class="empty-notes">
        <el-empty description="暂无笔记">
          <div class="empty-actions">
            <el-button type="primary" size="small" @click="addNote('note')">
              添加笔记
            </el-button>
            <el-button size="small" @click="addNote('foreshadowing')">
              添加伏笔
            </el-button>
            <el-button size="small" @click="addNote('inspiration')">
              添加灵感
            </el-button>
          </div>
        </el-empty>
      </div>

      <div v-else class="notes-list">
        <div
          v-for="(note, index) in filteredNotes"
          :key="index"
          class="note-card"
          :class="note.note_type"
        >
          <div class="note-header">
            <el-tag :type="getNoteTagType(note.note_type)" size="small">
              {{ getNoteTypeName(note.note_type) }}
            </el-tag>
            <div class="note-actions">
              <el-button
                v-if="note.status === 'active'"
                type="success"
                text
                size="small"
                @click="resolveNote(index)"
              >
                已解决
              </el-button>
              <el-button
                type="danger"
                text
                size="small"
                @click="removeNote(index)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <el-input
            v-model="note.title"
            placeholder="标题"
            class="note-title"
          />
          <el-input
            v-model="note.content"
            type="textarea"
            :rows="3"
            placeholder="详细内容..."
            class="note-content"
          />
          <div v-if="note.note_type === 'foreshadowing'" class="note-status">
            <el-tag
              :type="note.status === 'active' ? 'warning' : 'success'"
              size="small"
            >
              {{ note.status === 'active' ? '待埋设' : note.status === 'resolved' ? '已回收' : '已放弃' }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 跳过提示 -->
    <div class="skip-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>这一步是可选的，你也可以在写作过程中随时添加笔记</span>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回修改</el-button>
      <el-button type="primary" size="large" @click="handleNext">
        下一步：确认创建
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Delete, ArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import { generateUUID } from '@/api/wizard'

const wizardStore = useWizardStore()
const activeType = ref<'all' | 'foreshadowing' | 'inspiration' | 'note'>('all')

const filteredNotes = computed(() => {
  if (activeType.value === 'all') {
    return wizardStore.notes
  }
  return wizardStore.notes.filter(n => n.note_type === activeType.value)
})

const foreshadowingCount = computed(() => wizardStore.notes.filter(n => n.note_type === 'foreshadowing').length)
const inspirationCount = computed(() => wizardStore.notes.filter(n => n.note_type === 'inspiration').length)
const noteCount = computed(() => wizardStore.notes.filter(n => n.note_type === 'note').length)

function addNote(type: 'foreshadowing' | 'inspiration' | 'note') {
  wizardStore.addNote({
    id: generateUUID(),
    note_type: type,
    title: '',
    content: '',
    status: 'active',
    related_chapter_ids: [],
  })
}

function removeNote(index: number) {
  // 需要找到在原数组中的索引
  const note = filteredNotes.value[index]
  const originalIndex = wizardStore.notes.indexOf(note)
  if (originalIndex !== -1) {
    wizardStore.removeNote(originalIndex)
  }
}

function resolveNote(index: number) {
  const note = filteredNotes.value[index]
  note.status = 'resolved'
}

function getNoteTagType(type: string) {
  switch (type) {
    case 'foreshadowing': return 'warning'
    case 'inspiration': return 'success'
    default: return 'info'
  }
}

function getNoteTypeName(type: string) {
  switch (type) {
    case 'foreshadowing': return '伏笔'
    case 'inspiration': return '灵感'
    default: return '笔记'
  }
}

function handleNext() {
  wizardStore.nextStep()
}
</script>

<style scoped>
.step-five {
  max-width: 900px;
  margin: 0 auto;
}

.step-header {
  text-align: center;
  margin-bottom: 32px;
}

.step-header h2 {
  font-size: 24px;
  font-weight: 600;
  color: #2C2C2C;
  margin-bottom: 8px;
  font-family: 'Noto Serif SC', serif;
}

.step-desc {
  font-size: 14px;
  color: #7A7A7A;
}

.notes-section {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
}

.note-types {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.empty-notes {
  padding: 40px 0;
}

.empty-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.notes-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.note-card {
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #E0DFDC;
}

.note-card.foreshadowing {
  border-left: 4px solid #E6A23C;
}

.note-card.inspiration {
  border-left: 4px solid #67C23A;
}

.note-card.note {
  border-left: 4px solid #909399;
}

.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.note-actions {
  display: flex;
  gap: 4px;
}

.note-title {
  margin-bottom: 12px;
}

.note-title :deep(.el-input__wrapper) {
  font-weight: 500;
}

.note-content :deep(.el-textarea__inner) {
  min-height: 80px;
}

.note-status {
  margin-top: 8px;
}

.skip-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 20px;
  font-size: 13px;
  color: #9E9E9E;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>