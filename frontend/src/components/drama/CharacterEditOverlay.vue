<template>
  <teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="overlay-backdrop" @click.self="handleCancel">
        <div class="overlay-card">
          <div class="overlay-header">
            <h3 class="overlay-title">{{ isNew ? '添加角色' : '编辑角色' }}</h3>
          </div>

          <div class="overlay-body">
            <div class="form-item">
              <label class="form-label">角色名称</label>
              <el-input
                ref="nameInputRef"
                v-model="draft.name"
                placeholder="输入角色名称"
                maxlength="100"
                @keydown.enter.ctrl="handleSave"
                @keydown.esc="handleCancel"
              />
            </div>

            <div class="form-item">
              <label class="form-label">角色描述</label>
              <el-input
                v-model="draft.description"
                type="textarea"
                :rows="6"
                placeholder="描述角色的性格、外貌、背景等..."
                maxlength="2000"
                show-word-limit
                @keydown.enter.ctrl="handleSave"
                @keydown.esc="handleCancel"
              />
            </div>
          </div>

          <div class="overlay-footer">
            <p class="hint-text">按 Esc 取消，Ctrl+Enter 保存</p>
            <div class="actions">
              <el-button @click="handleCancel">取消</el-button>
              <el-button type="primary" :disabled="!canSave" @click="handleSave">保存</el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { CharacterSetting } from '@/api/drama'

const props = defineProps<{
  visible: boolean
  character: CharacterSetting | null
}>()

const emit = defineEmits<{
  (e: 'save', character: CharacterSetting): void
  (e: 'cancel'): void
}>()

const nameInputRef = ref<{ focus: () => void } | null>(null)

const draft = ref<CharacterSetting>({
  id: '',
  name: '',
  description: '',
})

const isNew = computed(() => !props.character?.name)
const canSave = computed(() => draft.value.name.trim().length > 0)

// Watch visible to initialize draft and focus input
watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      // Initialize draft from props.character
      if (props.character) {
        draft.value = {
          id: props.character.id,
          name: props.character.name,
          description: props.character.description,
        }
      } else {
        draft.value = {
          id: '',
          name: '',
          description: '',
        }
      }
      // Focus name input after DOM update
      await nextTick()
      nameInputRef.value?.focus()
    }
  },
)

function handleSave() {
  const trimmedName = draft.value.name.trim()
  if (!trimmedName) return

  emit('save', {
    id: draft.value.id,
    name: trimmedName,
    description: draft.value.description.trim(),
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.overlay-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.overlay-card {
  width: 480px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.overlay-header {
  padding: 16px 20px;
  border-bottom: 1px solid #E0DFDC;
}

.overlay-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
}

.overlay-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
}

.overlay-footer {
  padding: 16px 20px;
  border-top: 1px solid #E0DFDC;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hint-text {
  margin: 0;
  font-size: 12px;
  color: #9A9A9A;
}

.actions {
  display: flex;
  gap: 8px;
}

/* Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.fade-enter-active .overlay-card,
.fade-leave-active .overlay-card {
  transition: transform 0.2s ease;
}

.fade-enter-from .overlay-card,
.fade-leave-to .overlay-card {
  transform: scale(0.95);
}
</style>