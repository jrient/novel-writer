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
- 支持两种认证方式：Header 和 URL 参数
- 可生成、重新生成、删除

## 数据模型

### User 模型新增字段

```python
# backend/app/models/user.py
api_key: Mapped[Optional[str]] = mapped_column(
    String(64), nullable=True, unique=True, index=True, comment="API Key"
)
```

- 类型：64字符随机字符串
- 生成方式：`secrets.token_urlsafe(48)`
- 唯一约束：确保不同用户的 Key 不重复
- 可为空：用户可以没有 API Key
- 索引：加速认证查询

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

### 3. 删除 API Key

```
DELETE /api/v1/admin/users/{user_id}/api-key
```

权限：仅管理员

响应：
```json
{
  "detail": "API Key 已删除"
}
```

### 4. 免密认证中间件

修改 `get_current_user` 函数，支持两种认证方式：

1. **Header 方式**（现有）：`Authorization: Bearer <jwt_token>`
2. **URL 参数方式**（新增）：`?api_key=<api_key>`

认证流程：
1. 优先检查 Header 中的 JWT Token
2. 若无 Header Token，检查 URL 参数 `api_key`
3. 若提供 `api_key`，查询 User 表匹配 `api_key` 字段
4. 匹配成功返回对应用户，失败返回 401

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
   - 「复制完整 URL」按钮（格式：`{base_url}/api/v1/...?api_key={key}`）
5. 关闭对话框后刷新列表

**删除**：
- 不提供删除按钮（API Key 为空即为「无 Key」状态）
- 如需删除，可通过「重新生成」后不使用，或后续增加删除功能

## 实现清单

### 后端
- [ ] User 模型新增 `api_key` 字段
- [ ] 数据库迁移脚本
- [ ] Schema 新增 `AdminUserCreate`
- [ ] `POST /api/v1/admin/users` 端点
- [ ] `POST /api/v1/admin/users/{id}/api-key` 端点
- [ ] `DELETE /api/v1/admin/users/{id}/api-key` 端点
- [ ] 修改 `get_current_user` 支持 `api_key` 参数认证
- [ ] AdminUserResponse 新增 `has_api_key` 字段

### 前端
- [ ] `frontend/src/api/admin.ts` 新增 API 函数
- [ ] 用户管理表格新增「API Key」列
- [ ] 添加用户对话框组件
- [ ] API Key 生成/复制对话框
- [ ] 操作栏新增「生成 Key」按钮