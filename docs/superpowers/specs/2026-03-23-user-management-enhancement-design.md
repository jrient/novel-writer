# 用户管理增强：添加用户与 API Key 功能

## 概述

为管理后台增加两个功能：
1. **添加用户**：管理员可直接创建用户
2. **API Key 免密认证**：为 AI 工具（如 OpenClaw）提供长效认证方式

## 需求

### 添加用户
- 管理员可创建新用户
- 必填字段：用户名、邮箱、密码
- 创建后用户直接激活（`is_active=True`）

### API Key 免密认证
- 每个用户一个固定的 API Key
- **仅支持 Header 方式认证**（避免 URL 参数泄露风险）
- 可生成、重新生成

## Schema 定义

### AdminUserCreate

```python
# backend/app/schemas/admin.py
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

### AdminUserResponse 新增字段

```python
# backend/app/schemas/admin.py
# 在现有 AdminUserResponse 类中新增
has_api_key: bool = False  # 是否已生成 API Key
```

### ApiKeyResponse

```python
# backend/app/schemas/admin.py
class ApiKeyResponse(BaseModel):
    """API Key 响应模型"""
    api_key: str
```

## 数据模型

### User 模型新增字段

```python
# backend/app/models/user.py
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

- `api_key`：64字符随机字符串，生成方式 `secrets.token_urlsafe(48)`
- `api_key_created_at`：记录 Key 创建时间，便于审计
- `api_key_last_used_at`：记录最后使用时间，便于监控异常使用

## 后端 API

### 1. 创建用户

```
POST /api/v1/admin/users
```

权限：仅管理员

请求体：
```json
{
  "username": "string (必填, 3-50字符)",
  "email": "string (必填, 有效邮箱)",
  "password": "string (必填, 6-100字符)"
}
```

响应：`AdminUserResponse`

错误响应：
```json
{"detail": "用户名已被使用"}
{"detail": "邮箱已被使用"}
```

### 2. 生成/重新生成 API Key

```
POST /api/v1/admin/users/{user_id}/api-key
```

权限：仅管理员

响应：
```json
{
  "api_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

行为：
- 每次调用会覆盖旧的 Key
- 返回明文 Key（只显示一次，后续无法查看）
- 同时更新 `api_key_created_at` 字段

### 3. 免密认证中间件

修改 `get_current_user` 函数，支持两种认证方式：

1. **JWT Token**（优先）：`Authorization: Bearer <jwt_token>`
2. **API Key**（备选）：`X-API-Key: <api_key>` Header

> **安全说明**：仅支持 Header 方式传递 API Key，避免 URL 参数泄露到日志/浏览器历史中。

认证流程：
1. 优先检查 `Authorization` Header 中的 JWT Token
2. 若无 JWT Token，检查 `X-API-Key` Header
3. 若提供 `api_key`，查询 User 表匹配 `api_key` 字段
4. 匹配成功更新 `api_key_last_used_at` 并返回用户，失败返回 401

**实现代码**：

```python
# backend/app/routers/auth.py
from fastapi import Header

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户（支持 JWT Token 或 API Key）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
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

## 前端界面

### 1. 用户管理表格

**新增列**：
- 「API Key」列：显示「已生成」或「-」

**新增按钮**：
- 筛选栏右侧：「添加用户」按钮
- 操作栏：「生成 Key」按钮

### 2. 添加用户对话框

```
标题：添加用户
字段：
  - 用户名（必填，3-50字符）
  - 邮箱（必填，有效邮箱格式）
  - 密码（必填，6位以上）
按钮：取消 / 确定
```

校验：
- 用户名唯一性检查
- 邮箱唯一性检查
- 密码长度至少6位

### 3. API Key 操作流程

**生成/重新生成**：
1. 点击「生成 Key」按钮
2. 弹出确认对话框（重新生成时提示「将覆盖旧 Key」）
3. 确认后调用 API
4. 成功后弹出结果对话框：
   - 显示 API Key（明文）
   - 「复制 Key」按钮
   - 「复制使用示例」按钮（显示 curl 命令示例）
5. 关闭对话框后刷新列表

**使用示例对话框内容**：
```
API Key: sk_xxxxxxxxxxxx

使用方式（HTTP Header）：
X-API-Key: sk_xxxxxxxxxxxx

curl 示例：
curl -H "X-API-Key: sk_xxxxxxxxxxxx" https://your-host/api/v1/projects
```

## 实现清单

### 后端
- [ ] User 模型新增 `api_key`, `api_key_created_at`, `api_key_last_used_at` 字段
- [ ] 数据库迁移：`alembic revision --autogenerate -m "add_api_key_to_user"`
- [ ] Schema 新增 `AdminUserCreate`, `ApiKeyResponse`
- [ ] `AdminUserResponse` 新增 `has_api_key` 字段
- [ ] `POST /api/v1/admin/users` 端点
- [ ] `POST /api/v1/admin/users/{id}/api-key` 端点
- [ ] 修改 `get_current_user` 支持 `X-API-Key` Header 认证

### 前端
- [ ] `frontend/src/api/admin.ts` 新增 API 函数
- [ ] `AdminUser` 接口新增 `has_api_key: boolean` 字段
- [ ] 用户管理表格新增「API Key」列
- [ ] 添加用户对话框组件
- [ ] API Key 生成/复制对话框
- [ ] 操作栏新增「生成 Key」按钮