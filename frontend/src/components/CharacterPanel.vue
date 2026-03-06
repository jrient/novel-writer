<template>
  <div class="character-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">角色管理</span>
      <el-button size="small" type="primary" :icon="Plus" @click="showCreateDialog = true">
        新建角色
      </el-button>
    </div>

    <!-- 角色类型筛选 -->
    <div class="filter-bar">
      <el-radio-group v-model="filterRoleType" size="small" @change="handleFilter">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="protagonist">主角</el-radio-button>
        <el-radio-button label="antagonist">反派</el-radio-button>
        <el-radio-button label="supporting">配角</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 角色列表 -->
    <div class="character-list">
      <div v-if="characterStore.loading" class="loading-state">
        <el-skeleton :rows="2" animated />
      </div>

      <div v-else-if="filteredCharacters.length === 0" class="empty-state">
        <el-empty description="暂无角色" :image-size="60" />
      </div>

      <div
        v-else
        v-for="character in filteredCharacters"
        :key="character.id"
        class="character-card"
        :class="{ active: currentCharacter?.id === character.id }"
        @click="selectCharacter(character)"
      >
        <div class="avatar-section">
          <el-avatar :size="48" :src="character.avatar_url || undefined">
            {{ character.name.charAt(0) }}
          </el-avatar>
        </div>
        <div class="info-section">
          <div class="name-row">
            <span class="name">{{ character.name }}</span>
            <el-tag :type="roleTagType(character.role_type)" size="small">
              {{ roleLabel(character.role_type) }}
            </el-tag>
          </div>
          <div class="meta-row">
            <span v-if="character.age">{{ character.age }}</span>
            <span v-if="character.gender">{{ character.gender }}</span>
            <span v-if="character.occupation">{{ character.occupation }}</span>
          </div>
        </div>
        <div class="actions">
          <el-button text size="small" :icon="Edit" @click.stop="editCharacter(character)" />
          <el-button text size="small" type="danger" :icon="Delete" @click.stop="confirmDelete(character)" />
        </div>
      </div>
    </div>

    <!-- 角色详情/编辑对话框 -->
    <el-dialog
      v-model="showEditDialog"
      :title="editingCharacter ? '编辑角色' : '新建角色'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="formData" label-width="80px" label-position="left">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="姓名" required>
              <el-input v-model="formData.name" placeholder="角色姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型">
              <el-select v-model="formData.role_type" style="width: 100%">
                <el-option label="主角" value="protagonist" />
                <el-option label="反派" value="antagonist" />
                <el-option label="配角" value="supporting" />
                <el-option label="次要角色" value="minor" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="年龄">
              <el-input v-model="formData.age" placeholder="如: 25岁" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="性别">
              <el-input v-model="formData.gender" placeholder="男/女" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="身份">
              <el-input v-model="formData.occupation" placeholder="职业/身份" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="外貌">
          <el-input v-model="formData.appearance" type="textarea" :rows="2" placeholder="角色外貌描写..." />
        </el-form-item>

        <el-form-item label="性格">
          <el-input v-model="formData.personality_traits" type="textarea" :rows="2" placeholder="性格特点..." />
        </el-form-item>

        <el-form-item label="背景">
          <el-input v-model="formData.background" type="textarea" :rows="3" placeholder="角色背景故事..." />
        </el-form-item>

        <el-form-item label="成长弧线">
          <el-input v-model="formData.growth_arc" type="textarea" :rows="2" placeholder="角色发展轨迹..." />
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="formData.notes" type="textarea" :rows="2" placeholder="其他备注..." />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCharacter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import { useCharacterStore } from '@/stores/character'
import type { Character, CreateCharacterData, UpdateCharacterData } from '@/api/character'

const props = defineProps<{
  projectId: number
}>()

const characterStore = useCharacterStore()

const filterRoleType = ref('')
const currentCharacter = computed(() => characterStore.currentCharacter)

const filteredCharacters = computed(() => {
  if (!filterRoleType.value) return characterStore.characters
  return characterStore.characters.filter(c => c.role_type === filterRoleType.value)
})

// 对话框状态
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const editingCharacter = ref<Character | null>(null)
const saving = ref(false)

// 表单数据
const formData = ref<CreateCharacterData & UpdateCharacterData>({
  name: '',
  role_type: 'supporting',
  age: '',
  gender: '',
  occupation: '',
  appearance: '',
  personality_traits: '',
  background: '',
  growth_arc: '',
  notes: '',
})

function roleTagType(role: string) {
  const map: Record<string, string> = {
    protagonist: 'success',
    antagonist: 'danger',
    supporting: 'warning',
    minor: 'info',
  }
  return map[role] || 'info'
}

function roleLabel(role: string) {
  const map: Record<string, string> = {
    protagonist: '主角',
    antagonist: '反派',
    supporting: '配角',
    minor: '次要',
  }
  return map[role] || role
}

function handleFilter() {
  characterStore.fetchCharacters(props.projectId, filterRoleType.value)
}

function selectCharacter(character: Character) {
  characterStore.setCurrentCharacter(character)
}

function editCharacter(character: Character) {
  editingCharacter.value = character
  formData.value = {
    name: character.name,
    role_type: character.role_type || 'supporting',
    age: character.age || '',
    gender: character.gender || '',
    occupation: character.occupation || '',
    appearance: character.appearance || '',
    personality_traits: character.personality_traits || '',
    background: character.background || '',
    growth_arc: character.growth_arc || '',
    notes: character.notes || '',
  }
  showEditDialog.value = true
}

async function saveCharacter() {
  if (!formData.value.name) return

  saving.value = true
  try {
    if (editingCharacter.value) {
      await characterStore.updateCurrentCharacter(
        props.projectId,
        editingCharacter.value.id,
        formData.value
      )
    } else {
      await characterStore.createNewCharacter(props.projectId, formData.value)
    }
    showEditDialog.value = false
    showCreateDialog.value = false
    resetForm()
  } finally {
    saving.value = false
  }
}

async function confirmDelete(character: Character) {
  await ElMessageBox.confirm(`确定要删除角色「${character.name}」吗？`, '删除确认', {
    type: 'warning',
  })
  await characterStore.removeCharacter(props.projectId, character.id)
}

function resetForm() {
  editingCharacter.value = null
  formData.value = {
    name: '',
    role_type: 'supporting',
    age: '',
    gender: '',
    occupation: '',
    appearance: '',
    personality_traits: '',
    background: '',
    growth_arc: '',
    notes: '',
  }
}

// 监听对话框打开
watch(showEditDialog, (val) => {
  if (!val) resetForm()
})

watch(showCreateDialog, (val) => {
  if (val) {
    resetForm()
    showEditDialog.value = true
  }
})

onMounted(() => {
  characterStore.fetchCharacters(props.projectId)
})
</script>

<style scoped>
.character-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #fafaf9;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  background: white;
  border-bottom: 1px solid #e7e5e4;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #1c1917;
}

.filter-bar {
  padding: 16px 32px;
  background: white;
  border-bottom: 1px solid #f0ede6;
}

:deep(.filter-bar .el-radio-button__inner) {
  background-color: transparent;
  border-color: #e7e5e4;
  color: #57534e;
  border-radius: 8px;
  font-weight: 500;
}

:deep(.filter-bar .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: transparent;
  color: white;
}

.character-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 32px;
}

.character-card {
  display: flex;
  align-items: center;
  padding: 16px;
  margin-bottom: 12px;
  background-color: white;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #e7e5e4;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.character-card:hover {
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
  border-color: #667eea;
  transform: translateY(-1px);
}

.character-card.active {
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.15);
}

.avatar-section {
  flex-shrink: 0;
  margin-right: 14px;
}

.info-section {
  flex: 1;
  min-width: 0;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.name {
  font-size: 15px;
  font-weight: 600;
  color: #1c1917;
}

.meta-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #a8a29e;
}

.meta-row span:not(:last-child)::after {
  content: '·';
  margin-left: 8px;
}

.actions {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.character-card:hover .actions {
  opacity: 1;
}

.loading-state,
.empty-state {
  padding: 24px;
}
</style>
