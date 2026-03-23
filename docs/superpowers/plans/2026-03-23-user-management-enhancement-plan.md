# 用户管理增强：添加用户与 API Key 功能 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为管理后台增加添加用户功能和 API Key 免密认证功能

**Architecture:** 后端在 User 模型新增 API Key 相关字段，修改认证中间件支持 X-API-Key Header；前端在用户管理界面增加添加用户对话框和 API Key 管理功能

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, Vue 3, Element Plus, TypeScript

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/models/user.py` | 修改 | 新增 api_key 相关字段 |
| `backend/app/schemas/admin.py` | 修改 | 新增 AdminUserCreate, ApiKeyResponse, has_api_key 字段 |
| `backend/app/routers/admin.py` | 修改 | 新增创建用户和生成 API Key 端点 |
| `backend/app/routers/auth.py` | 修改 | get_current_user 支持 X-API-Key Header |
| `frontend/src/api/admin.ts` | 修改 | 新增 API 函数和类型 |
| `frontend/src/views/AdminView.vue` | 修改 | 添加用户对话框和 API Key 管理界面 |

---

## Task 1: User 模型新增 API Key 字段

**Files:**
- Modify: `backend/app/models/user.py`

- [ ] **Step 1: 在 User 模型中添加三个新字段**

在 `backend/app/models/user.py` 的 User 类中，在 `wechat_unionid` 字段后添加（文件已导入 `datetime`，无需额外导入）：

```python
    # API Key 认证
    api_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True, comment="API Key"
    )
    api_key_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="API Key 创建时间"
    )
    api_key_last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="API Key 最后使用时间"
    )
```

确保文件顶部导入了 `datetime`：
```python
from datetime import datetime
```

- [ ] **Step 2: 创建数据库迁移**

```bash
cd /data/project/novel-writer && docker compose exec backend alembic revision --autogenerate -m "add_api_key_to_user"
```

- [ ] **Step 3: 执行迁移**

```bash
cd /data/project/novel-writer && docker compose exec backend alembic upgrade head
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/models/user.py backend/alembic/versions/
git commit -m "feat(models): User 新增 api_key 相关字段

- api_key: 64字符随机字符串
- api_key_created_at: API Key 创建时间
- api_key_last_used_at: API Key 最后使用时间

Constraint: API Key 仅通过 X-API-Key Header 传递
Confidence: high
Scope-risk: narrow"
```

---

## Task 2: Schema 新增类型和字段

**Files:**
- Modify: `backend/app/schemas/admin.py`

- [ ] **Step 1: 新增 AdminUserCreate Schema**

在 `backend/app/schemas/admin.py` 文件中，在 `AdminUserResponse` 类之前添加（文件已导入 `re` 模块，无需额外导入）：

```python
class AdminUserCreate(BaseModel):
    """管理员创建用户模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('无效的邮箱格式')
        return v
```

- [ ] **Step 2: AdminUserResponse 新增 has_api_key 字段**

在 `AdminUserResponse` 类中，在 `total_tokens` 字段后添加：

```python
    has_api_key: bool = False  # 是否已生成 API Key
```

- [ ] **Step 3: 新增 ApiKeyResponse Schema**

在文件末尾添加：

```python
class ApiKeyResponse(BaseModel):
    """API Key 响应模型"""
    api_key: str
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/schemas/admin.py
git commit -m "feat(schemas): 新增 AdminUserCreate 和 ApiKeyResponse

- AdminUserCreate: 管理员创建用户请求体
- ApiKeyResponse: API Key 响应
- AdminUserResponse 新增 has_api_key 字段

Confidence: high
Scope-risk: narrow"
```

---

## Task 3: 后端新增创建用户端点

**Files:**
- Modify: `backend/app/routers/admin.py`

- [ ] **Step 1: 添加必要的导入**

在 `backend/app/routers/admin.py` 文件顶部，确保有以下导入：

```python
from sqlalchemy import or_
from app.core.security import get_password_hash
from app.schemas.admin import (
    AdminUserResponse,
    AdminUserUpdate,
    AdminUserListResponse,
    AdminUserCreate,  # 新增
    AdminResetPassword,
    AdminStatsResponse,
    # ... 其他导入保持不变
)
```

- [ ] **Step 2: 新增创建用户端点**

在 `list_users` 函数之前添加：

```python
@router.post("/users", response_model=AdminUserResponse, summary="创建用户")
async def create_user(
    user_data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建新用户（仅管理员）"""
    # 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已被使用")

    # 检查邮箱是否已存在
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    # 创建用户
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        nickname=user_data.username,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 构建响应
    response = AdminUserResponse.model_validate(user)
    response.project_count = 0
    response.has_api_key = False
    return response
```

- [ ] **Step 3: 更新 get_user 和 update_user 函数**

在 `get_user` 函数中，在返回前添加 `has_api_key` 字段：

```python
    user_data = AdminUserResponse.model_validate(user)
    user_data.project_count = project_count
    user_data.has_api_key = bool(user.api_key)  # 新增
    return user_data
```

在 `update_user` 函数中，在返回前添加 `has_api_key` 字段：

```python
    response = AdminUserResponse.model_validate(user)
    response.project_count = project_count
    response.has_api_key = bool(user.api_key)  # 新增
    return response
```

- [ ] **Step 4: 更新 list_users 函数**

在构建 `items` 列表的循环中，添加 `has_api_key` 字段：

```python
    items = []
    for user in users:
        user_data = AdminUserResponse.model_validate(user)
        user_data.project_count = project_counts.get(user.id, 0)
        user_data.total_tokens = token_counts.get(user.id, 0)
        user_data.has_api_key = bool(user.api_key)  # 新增
        items.append(user_data)
```

- [ ] **Step 5: 更新 toggle_user_active 函数**

在返回前添加 `has_api_key` 字段：

```python
    response = AdminUserResponse.model_validate(user)
    response.project_count = project_count
    response.has_api_key = bool(user.api_key)  # 新增
    return response
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/admin.py
git commit -m "feat(admin): 新增创建用户端点

POST /api/v1/admin/users - 管理员创建用户

同时更新各端点返回 has_api_key 字段

Confidence: high
Scope-risk: narrow"
```

---

## Task 4: 后端新增生成 API Key 端点

**Files:**
- Modify: `backend/app/routers/admin.py`

- [ ] **Step 1: 添加 secrets 导入**

在文件顶部添加：

```python
import secrets
from datetime import datetime
from app.schemas.admin import ApiKeyResponse
```

- [ ] **Step 2: 新增生成 API Key 端点**

在 `reset_user_password` 函数之后添加：

```python
@router.post("/users/{user_id}/api-key", response_model=ApiKeyResponse, summary="生成/重新生成 API Key")
async def generate_api_key(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """生成或重新生成用户的 API Key（仅管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 生成 64 字符的 API Key
    api_key = secrets.token_urlsafe(48)
    user.api_key = api_key
    user.api_key_created_at = datetime.utcnow()
    await db.commit()

    return ApiKeyResponse(api_key=api_key)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/routers/admin.py
git commit -m "feat(admin): 新增生成 API Key 端点

POST /api/v1/admin/users/{id}/api-key

使用 secrets.token_urlsafe(48) 生成 64 字符 API Key

Confidence: high
Scope-risk: narrow"
```

---

## Task 5: 修改认证中间件支持 API Key

**Files:**
- Modify: `backend/app/routers/auth.py`

- [ ] **Step 1: 添加 Header 导入**

在 `backend/app/routers/auth.py` 文件顶部，修改导入：

```python
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
```

- [ ] **Step 2: 修改 get_current_user 函数**

将 `get_current_user` 函数修改为：

```python
async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户（支持 JWT Token 或 API Key）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 优先 JWT Token
    if token:
        user_id = verify_token(token)
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user and user.is_active:
                return user

    # 其次 API Key
    if x_api_key:
        result = await db.execute(
            select(User).where(User.api_key == x_api_key)
        )
        user = result.scalar_one_or_none()
        if user and user.is_active:
            # 节流更新最后使用时间（避免高并发下的频繁写库）
            if not user.api_key_last_used_at or \
               (datetime.utcnow() - user.api_key_last_used_at).total_seconds() > 300:
                user.api_key_last_used_at = datetime.utcnow()
                await db.commit()
            return user

    raise credentials_exception
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/routers/auth.py
git commit -m "feat(auth): get_current_user 支持 X-API-Key Header 认证

- 优先 JWT Token，其次 X-API-Key Header
- API Key 认证时节流更新 last_used_at（间隔 5 分钟）

Constraint: API Key 仅通过 Header 传递，不支持 URL 参数
Rejected: URL 参数方式 | 安全风险（日志泄露）
Confidence: high
Scope-risk: narrow"
```

---

## Task 6: 前端 API 函数和类型

**Files:**
- Modify: `frontend/src/api/admin.ts`

- [ ] **Step 1: AdminUser 接口新增 has_api_key 字段**

在 `AdminUser` 接口中，在 `total_tokens` 字段后添加：

```typescript
  has_api_key: boolean
```

- [ ] **Step 2: 新增 AdminUserCreate 接口**

在 `AdminUserUpdate` 接口后添加：

```typescript
export interface AdminUserCreate {
  username: string
  email: string
  password: string
}
```

- [ ] **Step 3: 新增 ApiKeyResponse 接口**

在 `AdminUserCreate` 接口后添加：

```typescript
export interface ApiKeyResponse {
  api_key: string
}
```

- [ ] **Step 4: 新增创建用户函数**

在 `resetUserPassword` 函数后添加：

```typescript
// 创建用户
export function createUser(data: AdminUserCreate): Promise<AdminUser> {
  return request.post<AdminUser>('/admin/users', data)
}
```

- [ ] **Step 5: 新增生成 API Key 函数**

在 `createUser` 函数后添加：

```typescript
// 生成/重新生成 API Key
export function generateApiKey(userId: number): Promise<ApiKeyResponse> {
  return request.post<ApiKeyResponse>(`/admin/users/${userId}/api-key`)
}
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/admin.ts
git commit -m "feat(api): 前端新增创建用户和生成 API Key 函数

- createUser: 创建用户
- generateApiKey: 生成/重新生成 API Key
- AdminUser 新增 has_api_key 字段

Confidence: high
Scope-risk: narrow"
```

---

## Task 7: 前端界面 - 添加用户对话框

**Files:**
- Modify: `frontend/src/views/AdminView.vue`

- [ ] **Step 1: 导入新的 API 函数**

在 script 部分的 import 中添加 `createUser` 和 `generateApiKey`：

```typescript
import {
  getUsers,
  getStats,
  updateUser,
  toggleUserActive,
  resetUserPassword,
  createUser,      // 新增
  generateApiKey,  // 新增
  getTokenUsageStats,
  getTokenUsageRecords,
  getDailyTokenUsage,
  type AdminUser,
  type AdminStats,
  type TokenUsageStats,
  type TokenUsageRecord,
  type DailyTokenUsage,
  type AdminUserCreate,  // 新增
} from '@/api/admin'
```

- [ ] **Step 2: 添加状态变量**

在 `resetPasswordForm` 变量后添加：

```typescript
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
```

- [ ] **Step 3: 添加处理函数**

在 `handleResetPassword` 函数后添加：

```typescript
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

async function handleGenerateApiKey(user: AdminUser) {
  try {
    await ElMessageBox.confirm(
      user.has_api_key
        ? `确定要为用户 "${user.username}" 重新生成 API Key 吗？旧 Key 将立即失效。`
        : `确定要为用户 "${user.username}" 生成 API Key 吗？`,
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

function copyApiKey() {
  navigator.clipboard.writeText(apiKeyResult.value)
  ElMessage.success('已复制 API Key')
}

function copyApiKeyExample() {
  const example = `curl -H "X-API-Key: ${apiKeyResult.value}" ${window.location.origin}/api/v1/projects`
  navigator.clipboard.writeText(example)
  ElMessage.success('已复制使用示例')
}
```

- [ ] **Step 4: 添加「添加用户」按钮**

在筛选栏的 `<el-col :span="2">` 后添加一个按钮列：

```vue
            <el-col :span="3">
              <el-button type="success" @click="openAddUserDialog">添加用户</el-button>
            </el-col>
```

修改前一行：
```vue
            <el-col :span="2">
```
改为：
```vue
            <el-col :span="2">
```

调整筛选栏布局，将搜索框从 span="8" 改为 span="6"。

- [ ] **Step 5: 添加 API Key 列**

在 `el-table` 中，在「Token 用量」列后添加：

```vue
            <el-table-column label="API Key" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.has_api_key" type="success" size="small">已生成</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
```

- [ ] **Step 6: 操作栏添加「生成 Key」按钮**

在操作栏的「重置密码」按钮后添加：

```vue
                <el-button size="small" type="info" @click="handleGenerateApiKey(row)">
                  生成Key
                </el-button>
```

- [ ] **Step 7: 添加对话框模板**

在重置密码对话框后添加两个新对话框：

```vue
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
    <el-dialog v-model="apiKeyDialogVisible" title="API Key 已生成" width="500px">
      <el-alert
        type="warning"
        title="请立即复制保存，此 Key 只会显示一次"
        :closable="false"
        show-icon
        style="margin-bottom: 16px;"
      />
      <div style="background: #f5f7fa; padding: 12px; border-radius: 4px; margin-bottom: 16px;">
        <code style="word-break: break-all;">{{ apiKeyResult }}</code>
      </div>
      <div style="color: #909399; font-size: 13px; margin-bottom: 12px;">
        <strong>使用方式：</strong>在请求头添加 <code>X-API-Key: {{ apiKeyResult }}</code>
      </div>
      <template #footer>
        <el-button @click="copyApiKey">复制 Key</el-button>
        <el-button type="primary" @click="copyApiKeyExample">复制使用示例</el-button>
      </template>
    </el-dialog>
```

- [ ] **Step 8: 提交**

```bash
git add frontend/src/views/AdminView.vue
git commit -m "feat(admin): 前端新增添加用户和 API Key 管理功能

- 添加用户对话框
- API Key 生成和复制功能
- 用户列表新增 API Key 状态列

Confidence: high
Scope-risk: narrow"
```

---

## Task 8: 测试和验证

**Files:**
- None (测试操作)

- [ ] **Step 1: 启动后端服务**

```bash
cd /data/project/novel-writer && docker compose up -d backend
```

- [ ] **Step 2: 启动前端服务**

```bash
cd /data/project/novel-writer/frontend && npm run dev
```

- [ ] **Step 3: 手动测试添加用户**

1. 以管理员身份登录
2. 进入管理后台
3. 点击「添加用户」按钮
4. 填写用户名、邮箱、密码
5. 提交后确认用户出现在列表中

- [ ] **Step 4: 手动测试 API Key 生成**

1. 点击某用户的「生成Key」按钮
2. 确认弹出 API Key 显示框
3. 复制 API Key
4. 使用 curl 测试：
```bash
curl -H "X-API-Key: <复制的key>" http://localhost:8000/api/v1/projects
```
5. 确认返回项目列表而非 401 错误

- [ ] **Step 5: 提交最终版本**

```bash
git add -A
git commit -m "feat: 用户管理增强功能完成

- 管理员可添加用户
- 用户可生成 API Key 用于免密认证
- API Key 通过 X-API-Key Header 认证

Closes: 用户管理增强设计文档"
```