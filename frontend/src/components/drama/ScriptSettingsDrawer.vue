<template>
  <el-drawer
    v-model="drawerVisible"
    title="剧本设置"
    direction="rtl"
    :modal="false"
    size="360px"
    class="settings-drawer"
  >
    <!-- Save status indicator -->
    <div class="save-status">
      <span v-if="saving" class="saving">保存中...</span>
      <span v-else class="saved">已保存 ✓</span>
    </div>

    <el-collapse v-model="activeCollapse" class="settings-collapse">
      <!-- Panel 1: Character Settings -->
      <el-collapse-item title="人物设定" name="characters">
        <div class="character-list">
          <div v-for="char in localSettings.characters" :key="char.id" class="character-item">
            <div class="character-info">
              <span class="character-name">{{ char.name || '未命名角色' }}</span>
              <span class="character-desc">{{ char.description || '无描述' }}</span>
            </div>
            <div class="character-actions">
              <el-button text size="small" @click="handleEditCharacter(char)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text size="small" type="danger" @click="handleRemoveCharacter(char.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          <el-button type="primary" text class="add-character-btn" @click="handleAddCharacter">
            <el-icon><Plus /></el-icon>
            添加角色
          </el-button>
        </div>
      </el-collapse-item>

      <!-- Panel 2: World Setting -->
      <el-collapse-item title="世界观/背景" name="world_setting">
        <el-input
          v-model="localSettings.world_setting"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="描述故事发生的时代背景、地点、社会环境..."
          @input="scheduleSave"
        />
      </el-collapse-item>

      <!-- Panel 3: Tone/Style -->
      <el-collapse-item title="风格/基调" name="tone">
        <el-input
          v-model="localSettings.tone"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="描述写作风格，如幽默、严肃、悬疑、浪漫..."
          @input="scheduleSave"
        />
      </el-collapse-item>

      <!-- Panel 4: Plot Anchors -->
      <el-collapse-item title="核心剧情要素" name="plot_anchors">
        <el-input
          v-model="localSettings.plot_anchors"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="描述核心剧情线索、关键转折点、重要事件..."
          @input="scheduleSave"
        />
      </el-collapse-item>

      <!-- Panel 5: Persistent Directive -->
      <el-collapse-item title="持久化AI指令" name="persistent_directive">
        <el-input
          v-model="localSettings.persistent_directive"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="输入对所有AI生成内容生效的指令..."
          @input="scheduleSave"
        />
      </el-collapse-item>
    </el-collapse>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Edit, Delete, Plus } from '@element-plus/icons-vue'
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

// Local state to avoid mutating props directly
const localSettings = ref<ProjectSettings>({ ...defaultProjectSettings })
const saving = ref(false)
const activeCollapse = ref<string[]>(['characters'])

// Computed for drawer visibility
const drawerVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

// Debounce timer
let saveTimer: ReturnType<typeof setTimeout> | null = null

// Sync from props when drawer opens or settings change
watch(
  () => props.visible,
  (val) => {
    if (val) {
      // Reset local state when drawer opens
      localSettings.value = { ...props.settings }
    }
  },
)

watch(
  () => props.settings,
  (newSettings) => {
    if (props.visible) {
      localSettings.value = { ...newSettings }
    }
  },
  { deep: true },
)

// Debounced save (500ms)
function scheduleSave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
  }
  saving.value = true
  saveTimer = setTimeout(() => {
    saveNow()
  }, 500)
}

// Immediate save
function saveNow() {
  emit('save', { ...localSettings.value })
  saving.value = false
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
}

// Add new character
function handleAddCharacter() {
  const newChar: CharacterSetting = {
    id: crypto.randomUUID(),
    name: '',
    description: '',
  }
  localSettings.value.characters.push(newChar)
  emit('edit-character', newChar)
}

// Edit existing character
function handleEditCharacter(char: CharacterSetting) {
  emit('edit-character', char)
}

// Remove character
function handleRemoveCharacter(id: string) {
  localSettings.value.characters = localSettings.value.characters.filter((c) => c.id !== id)
  scheduleSave()
}

// Update character from external source
function updateCharacter(updated: CharacterSetting) {
  const index = localSettings.value.characters.findIndex((c) => c.id === updated.id)
  if (index !== -1) {
    localSettings.value.characters[index] = { ...updated }
    saveNow()
  }
}

// Expose methods for external use
defineExpose({
  saveNow,
  updateCharacter,
})
</script>

<style scoped>
.settings-drawer {
  --el-drawer-padding-primary: 16px;
}

.save-status {
  display: flex;
  justify-content: flex-end;
  padding: 8px 0;
  font-size: 12px;
}

.saving {
  color: #E6A23C;
}

.saved {
  color: #67C23A;
}

.settings-collapse {
  border: none;
}

.settings-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
  background: transparent;
  border-bottom: 1px solid #E0DFDC;
}

.settings-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.settings-collapse :deep(.el-collapse-item__content) {
  padding: 12px 0;
}

.character-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.character-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: #F7F6F3;
  border-radius: 8px;
}

.character-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.character-name {
  font-size: 13px;
  font-weight: 500;
  color: #2C2C2C;
}

.character-desc {
  font-size: 12px;
  color: #7A7A7A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.character-actions {
  display: flex;
  gap: 4px;
}

.add-character-btn {
  width: 100%;
  justify-content: center;
  margin-top: 4px;
}

:deep(.el-textarea__inner) {
  font-size: 13px;
  line-height: 1.6;
  color: #2C2C2C;
  background: #F7F6F3;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
}

:deep(.el-textarea__inner:focus) {
  border-color: #6B7B8D;
}
</style>