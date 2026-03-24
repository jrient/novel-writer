<template>
  <div class="admin-container">
    <div class="admin-header">
      <h1>管理后台</h1>
      <el-button @click="$router.push('/projects')" :icon="Back">返回项目</el-button>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="5">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.total_users }}</div>
          <div class="stat-label">用户总数</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.active_users }}</div>
          <div class="stat-label">活跃用户</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.superuser_count }}</div>
          <div class="stat-label">管理员数</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ stats.total_projects }}</div>
          <div class="stat-label">项目总数</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ formatTokenCount(stats.total_tokens) }}</div>
          <div class="stat-label">Token 总用量</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 标签页 -->
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- 用户管理 -->
      <el-tab-pane label="用户管理" name="users">
        <el-card class="filter-card">
          <el-row :gutter="16" align="middle">
            <el-col :span="6">
              <el-input
                v-model="filters.search"
                placeholder="搜索用户名/邮箱/昵称"
                clearable
                @clear="loadUsers"
                @keyup.enter="loadUsers"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </el-col>
            <el-col :span="4">
              <el-select v-model="filters.is_active" placeholder="用户状态" clearable @change="loadUsers">
                <el-option label="已启用" :value="true" />
                <el-option label="已禁用" :value="false" />
              </el-select>
            </el-col>
            <el-col :span="4">
              <el-select v-model="filters.is_superuser" placeholder="用户角色" clearable @change="loadUsers">
                <el-option label="管理员" :value="true" />
                <el-option label="普通用户" :value="false" />
              </el-select>
            </el-col>
            <el-col :span="6">
              <el-button type="primary" @click="loadUsers">搜索</el-button>
              <el-button type="success" @click="openAddUserDialog">添加用户</el-button>
            </el-col>
          </el-row>
        </el-card>

        <el-card class="table-card">
          <el-table :data="users" v-loading="loading" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column prop="email" label="邮箱" min-width="180" />
            <el-table-column prop="nickname" label="昵称" width="120">
              <template #default="{ row }">{{ row.nickname || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                  {{ row.is_active ? '正常' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="角色" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_superuser ? 'warning' : 'info'" size="small">
                  {{ row.is_superuser ? '管理员' : '用户' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="project_count" label="项目数" width="80" align="center" />
            <el-table-column label="Token 用量" width="110" align="center">
              <template #default="{ row }">{{ formatTokenCount(row.total_tokens) }}</template>
            </el-table-column>
            <el-table-column label="API Key" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.has_api_key" type="success" size="small">已生成</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="注册时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="最后登录" width="170">
              <template #default="{ row }">{{ row.last_login_at ? formatTime(row.last_login_at) : '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="300" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
                <el-button
                  size="small"
                  :type="row.is_active ? 'danger' : 'success'"
                  @click="handleToggleActive(row)"
                >
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
                <el-button size="small" type="warning" @click="openResetPasswordDialog(row)">
                  重置密码
                </el-button>
                <el-button size="small" :type="row.has_api_key ? 'primary' : 'info'" @click="handleApiKey(row)">
                  {{ row.has_api_key ? '查看Key' : '生成Key' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.pageSize"
              :total="pagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="loadUsers"
              @current-change="loadUsers"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- Token 使用统计 -->
      <el-tab-pane label="Token 用量" name="tokens">
        <!-- 时间范围选择 -->
        <el-card class="filter-card">
          <el-row :gutter="16" align="middle">
            <el-col :span="6">
              <el-select v-model="tokenDays" @change="loadTokenStats">
                <el-option label="近 7 天" :value="7" />
                <el-option label="近 30 天" :value="30" />
                <el-option label="近 90 天" :value="90" />
                <el-option label="近 365 天" :value="365" />
              </el-select>
            </el-col>
          </el-row>
        </el-card>

        <!-- Token 统计概览 -->
        <el-row :gutter="16" class="stats-row">
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-value">{{ formatTokenCount(tokenStats.total_tokens) }}</div>
              <div class="stat-label">总 Token</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-value">{{ formatTokenCount(tokenStats.total_input_tokens) }}</div>
              <div class="stat-label">输入 Token</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-value">{{ formatTokenCount(tokenStats.total_output_tokens) }}</div>
              <div class="stat-label">输出 Token</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" class="stat-card">
              <div class="stat-value">{{ tokenStats.total_calls }}</div>
              <div class="stat-label">调用次数</div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 每日趋势图 -->
        <el-card class="table-card" v-if="dailyUsage.length">
          <template #header><strong>每日 Token 用量趋势</strong></template>
          <div class="chart-container">
            <div class="chart-bars">
              <div
                v-for="day in dailyUsage"
                :key="day.date"
                class="chart-bar-group"
                :title="`${day.date}\nToken: ${day.total_tokens.toLocaleString()}\n调用: ${day.call_count} 次`"
              >
                <div
                  class="chart-bar"
                  :style="{ height: getBarHeight(day.total_tokens) + 'px' }"
                >
                  <span class="chart-bar-value" v-if="day.total_tokens > 0">
                    {{ formatTokenCount(day.total_tokens) }}
                  </span>
                </div>
                <div class="chart-bar-label">{{ day.date.slice(5) }}</div>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 按提供商统计 -->
        <el-card class="table-card" v-if="tokenStats.by_provider.length">
          <template #header><strong>按提供商统计</strong></template>
          <el-table :data="tokenStats.by_provider" stripe>
            <el-table-column prop="provider" label="提供商" width="150">
              <template #default="{ row }">
                <el-tag size="small">{{ row.provider }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="总 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.total_tokens) }}</template>
            </el-table-column>
            <el-table-column label="输入 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.input_tokens) }}</template>
            </el-table-column>
            <el-table-column label="输出 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.output_tokens) }}</template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="120" />
          </el-table>
        </el-card>

        <!-- 按用户统计 -->
        <el-card class="table-card" v-if="tokenStats.by_user.length">
          <template #header><strong>用户 Token 排行（Top 20）</strong></template>
          <el-table :data="tokenStats.by_user" stripe>
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column prop="nickname" label="昵称" width="120">
              <template #default="{ row }">{{ row.nickname || '-' }}</template>
            </el-table-column>
            <el-table-column label="总 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.total_tokens) }}</template>
            </el-table-column>
            <el-table-column label="输入 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.input_tokens) }}</template>
            </el-table-column>
            <el-table-column label="输出 Token" width="150">
              <template #default="{ row }">{{ formatTokenCount(row.output_tokens) }}</template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="120" />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" @click="viewUserRecords(row.user_id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 使用记录 -->
        <el-card class="table-card">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <strong>使用记录</strong>
              <div>
                <el-select
                  v-model="tokenRecordFilters.provider"
                  placeholder="提供商"
                  clearable
                  style="width: 140px; margin-right: 8px;"
                  @change="loadTokenRecords"
                >
                  <el-option label="openai" value="openai" />
                  <el-option label="anthropic" value="anthropic" />
                  <el-option label="ollama" value="ollama" />
                </el-select>
                <el-button
                  v-if="tokenRecordFilters.user_id"
                  size="small"
                  @click="tokenRecordFilters.user_id = undefined; loadTokenRecords()"
                >
                  清除用户筛选
                </el-button>
              </div>
            </div>
          </template>
          <el-table :data="tokenRecords" v-loading="tokenRecordsLoading" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户" width="120" />
            <el-table-column prop="provider" label="提供商" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.provider }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model" label="模型" width="160" />
            <el-table-column prop="action" label="操作" width="120" />
            <el-table-column label="输入" width="100" align="right">
              <template #default="{ row }">{{ row.input_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="输出" width="100" align="right">
              <template #default="{ row }">{{ row.output_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="合计" width="100" align="right">
              <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
            </el-table-column>
            <el-table-column label="时间" min-width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="tokenRecordPagination.page"
              v-model:page-size="tokenRecordPagination.pageSize"
              :total="tokenRecordPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="loadTokenRecords"
              @current-change="loadTokenRecords"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑用户" width="480px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="editForm.is_superuser" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleEditUser">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="resetPasswordDialogVisible" title="重置密码" width="420px">
      <p style="margin-bottom: 16px; color: #909399;">
        即将重置用户 <strong>{{ resetPasswordUser?.username }}</strong> 的密码
      </p>
      <el-form :model="resetPasswordForm" label-width="80px">
        <el-form-item label="新密码">
          <el-input
            v-model="resetPasswordForm.newPassword"
            type="password"
            show-password
            placeholder="请输入新密码（至少6位）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPasswordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetPasswordLoading" @click="handleResetPassword">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加用户对话框 -->
    <el-dialog v-model="addUserDialogVisible" title="添加用户" width="420px">
      <el-form :model="addUserForm" label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="addUserForm.username" placeholder="3-50字符" />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="addUserForm.email" placeholder="有效邮箱地址" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input
            v-model="addUserForm.password"
            type="password"
            show-password
            placeholder="至少6位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addUserDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addUserLoading" @click="handleAddUser">确定</el-button>
      </template>
    </el-dialog>

    <!-- API Key 结果对话框 -->
    <el-dialog v-model="apiKeyDialogVisible" title="API Key" width="550px">
      <div style="background: #f5f7fa; padding: 12px; border-radius: 4px; margin-bottom: 16px;">
        <code style="word-break: break-all; font-size: 14px;">{{ apiKeyResult }}</code>
      </div>

      <el-divider content-position="left">使用方法</el-divider>

      <div style="margin-bottom: 16px;">
        <div style="font-weight: 500; margin-bottom: 8px;">方式一：HTTP Header（推荐）</div>
        <div style="background: #fafafa; padding: 8px 12px; border-radius: 4px; font-family: monospace; font-size: 13px;">
          X-API-Key: {{ apiKeyResult }}
        </div>
      </div>

      <div style="margin-bottom: 16px;">
        <div style="font-weight: 500; margin-bottom: 8px;">方式二：curl 示例</div>
        <div style="background: #fafafa; padding: 8px 12px; border-radius: 4px; font-family: monospace; font-size: 12px; word-break: break-all;">
          curl -H "X-API-Key: {{ apiKeyResult }}" {{ apiUrl }}/projects
        </div>
      </div>

      <template #footer>
        <el-button @click="copyApiKey">复制 Key</el-button>
        <el-button type="primary" @click="copyApiKeyExample">复制 curl 示例</el-button>
        <el-button type="warning" @click="handleRegenerateApiKey">重新生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Search, Back } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getUsers,
  getStats,
  updateUser,
  toggleUserActive,
  resetUserPassword,
  createUser,
  generateApiKey,
  getApiKey,
  getTokenUsageStats,
  getTokenUsageRecords,
  getDailyTokenUsage,
  type AdminUser,
  type AdminStats,
  type TokenUsageStats,
  type TokenUsageRecord,
  type DailyTokenUsage,
  type AdminUserCreate,
} from '@/api/admin'

const activeTab = ref('users')
const loading = ref(false)
const users = ref<AdminUser[]>([])
const stats = ref<AdminStats>({
  total_users: 0,
  active_users: 0,
  superuser_count: 0,
  total_projects: 0,
  total_tokens: 0,
})

const filters = reactive({
  search: '',
  is_active: undefined as boolean | undefined,
  is_superuser: undefined as boolean | undefined,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

// 编辑
const editDialogVisible = ref(false)
const editLoading = ref(false)
const editUserId = ref(0)
const editForm = reactive({
  username: '',
  nickname: '',
  email: '',
  is_superuser: false,
})

// 重置密码
const resetPasswordDialogVisible = ref(false)
const resetPasswordLoading = ref(false)
const resetPasswordUser = ref<AdminUser | null>(null)
const resetPasswordForm = reactive({ newPassword: '' })

// 添加用户
const addUserDialogVisible = ref(false)
const addUserLoading = ref(false)
const addUserForm = reactive({
  username: '',
  email: '',
  password: '',
})

// API Key
const apiKeyDialogVisible = ref(false)
const apiKeyResult = ref('')
const apiKeyForUser = ref<AdminUser | null>(null)
const apiUrl = window.location.origin + '/api/v1'

// Token 统计
const tokenDays = ref(30)
const tokenStats = ref<TokenUsageStats>({
  total_tokens: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  total_calls: 0,
  by_provider: [],
  by_user: [],
})
const tokenRecords = ref<TokenUsageRecord[]>([])
const tokenRecordsLoading = ref(false)
const tokenRecordFilters = reactive({
  provider: undefined as string | undefined,
  user_id: undefined as number | undefined,
})
const dailyUsage = ref<DailyTokenUsage[]>([])
const tokenRecordPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatTokenCount(count: number): string {
  if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M'
  if (count >= 1000) return (count / 1000).toFixed(1) + 'K'
  return count.toString()
}

async function loadStats() {
  try {
    stats.value = await getStats()
  } catch { /* ignore */ }
}

async function loadUsers() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filters.search) params.search = filters.search
    if (filters.is_active !== undefined) params.is_active = filters.is_active
    if (filters.is_superuser !== undefined) params.is_superuser = filters.is_superuser

    const res = await getUsers(params)
    users.value = res.items
    pagination.total = res.total
  } finally {
    loading.value = false
  }
}

function openEditDialog(user: AdminUser) {
  editUserId.value = user.id
  editForm.username = user.username
  editForm.nickname = user.nickname || ''
  editForm.email = user.email
  editForm.is_superuser = user.is_superuser
  editDialogVisible.value = true
}

async function handleEditUser() {
  editLoading.value = true
  try {
    await updateUser(editUserId.value, {
      nickname: editForm.nickname,
      email: editForm.email,
      is_superuser: editForm.is_superuser,
    })
    ElMessage.success('用户信息已更新')
    editDialogVisible.value = false
    loadUsers()
    loadStats()
  } finally {
    editLoading.value = false
  }
}

async function handleToggleActive(user: AdminUser) {
  const action = user.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定要${action}用户 "${user.username}" 吗？`, '确认操作', {
      type: 'warning',
    })
    await toggleUserActive(user.id)
    ElMessage.success(`已${action}用户`)
    loadUsers()
    loadStats()
  } catch { /* cancelled */ }
}

function openResetPasswordDialog(user: AdminUser) {
  resetPasswordUser.value = user
  resetPasswordForm.newPassword = ''
  resetPasswordDialogVisible.value = true
}

async function handleResetPassword() {
  if (resetPasswordForm.newPassword.length < 6) {
    ElMessage.warning('密码至少需要6位')
    return
  }
  resetPasswordLoading.value = true
  try {
    await resetUserPassword(resetPasswordUser.value!.id, resetPasswordForm.newPassword)
    ElMessage.success('密码已重置')
    resetPasswordDialogVisible.value = false
  } finally {
    resetPasswordLoading.value = false
  }
}

function openAddUserDialog() {
  addUserForm.username = ''
  addUserForm.email = ''
  addUserForm.password = ''
  addUserDialogVisible.value = true
}

async function handleAddUser() {
  if (addUserForm.username.length < 3) {
    ElMessage.warning('用户名至少需要3个字符')
    return
  }
  if (addUserForm.password.length < 6) {
    ElMessage.warning('密码至少需要6位')
    return
  }
  addUserLoading.value = true
  try {
    await createUser(addUserForm as AdminUserCreate)
    ElMessage.success('用户创建成功')
    addUserDialogVisible.value = false
    loadUsers()
    loadStats()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建失败')
  } finally {
    addUserLoading.value = false
  }
}

async function handleApiKey(user: AdminUser) {
  if (user.has_api_key) {
    // 查看现有 Key
    try {
      const result = await getApiKey(user.id)
      apiKeyResult.value = result.api_key
      apiKeyForUser.value = user
      apiKeyDialogVisible.value = true
    } catch {
      ElMessage.error('获取 API Key 失败')
    }
  } else {
    // 生成新 Key
    try {
      await ElMessageBox.confirm(
        `确定要为用户 "${user.username}" 生成 API Key 吗？`,
        '确认操作',
        { type: 'warning' }
      )
      const result = await generateApiKey(user.id)
      apiKeyResult.value = result.api_key
      apiKeyForUser.value = user
      apiKeyDialogVisible.value = true
      loadUsers()
    } catch { /* cancelled */ }
  }
}

async function handleRegenerateApiKey() {
  if (!apiKeyForUser.value) return
  try {
    await ElMessageBox.confirm(
      `确定要为用户 "${apiKeyForUser.value.username}" 重新生成 API Key 吗？旧 Key 将立即失效。`,
      '确认操作',
      { type: 'warning' }
    )
    const result = await generateApiKey(apiKeyForUser.value.id)
    apiKeyResult.value = result.api_key
    loadUsers()
    ElMessage.success('API Key 已重新生成')
  } catch { /* cancelled */ }
}

function copyApiKey() {
  navigator.clipboard.writeText(apiKeyResult.value)
  ElMessage.success('已复制 API Key')
}

function copyApiKeyExample() {
  const example = `curl -H "X-API-Key: ${apiKeyResult.value}" ${window.location.origin}/api/v1/projects`
  navigator.clipboard.writeText(example)
  ElMessage.success('已复制使用示例')
}

// Token 相关
function getBarHeight(tokens: number): number {
  const max = Math.max(...dailyUsage.value.map(d => d.total_tokens), 1)
  return Math.max(4, Math.round((tokens / max) * 160))
}

async function loadTokenStats() {
  try {
    const [statsData, dailyData] = await Promise.all([
      getTokenUsageStats(tokenDays.value),
      getDailyTokenUsage(tokenDays.value),
    ])
    tokenStats.value = statsData
    dailyUsage.value = dailyData
  } catch { /* ignore */ }
}

async function loadTokenRecords() {
  tokenRecordsLoading.value = true
  try {
    const params: Record<string, any> = {
      page: tokenRecordPagination.page,
      page_size: tokenRecordPagination.pageSize,
    }
    if (tokenRecordFilters.provider) params.provider = tokenRecordFilters.provider
    if (tokenRecordFilters.user_id) params.user_id = tokenRecordFilters.user_id

    const res = await getTokenUsageRecords(params)
    tokenRecords.value = res.items
    tokenRecordPagination.total = res.total
  } finally {
    tokenRecordsLoading.value = false
  }
}

function viewUserRecords(userId: number) {
  tokenRecordFilters.user_id = userId
  tokenRecordPagination.page = 1
  loadTokenRecords()
}

function handleTabChange(tab: string) {
  if (tab === 'tokens') {
    loadTokenStats()
    loadTokenRecords()
  }
}

onMounted(() => {
  loadStats()
  loadUsers()
})
</script>

<style scoped>
.admin-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.admin-header h1 {
  margin: 0;
  font-size: 24px;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.filter-card {
  margin-bottom: 16px;
}

.table-card {
  margin-bottom: 16px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.chart-container {
  overflow-x: auto;
  padding: 8px 0;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  min-height: 200px;
  padding-top: 24px;
}

.chart-bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 28px;
  cursor: pointer;
}

.chart-bar {
  width: 100%;
  max-width: 40px;
  background: linear-gradient(180deg, #409eff, #79bbff);
  border-radius: 3px 3px 0 0;
  position: relative;
  transition: background 0.2s;
}

.chart-bar-group:hover .chart-bar {
  background: linear-gradient(180deg, #337ecc, #409eff);
}

.chart-bar-value {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: #606266;
  white-space: nowrap;
}

.chart-bar-label {
  font-size: 10px;
  color: #909399;
  margin-top: 4px;
  white-space: nowrap;
}
</style>
