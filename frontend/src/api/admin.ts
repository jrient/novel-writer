import request from './request'

export interface AdminUser {
  id: number
  username: string
  email: string
  nickname: string | null
  avatar_url: string | null
  is_active: boolean
  is_superuser: boolean
  github_id: string | null
  wechat_openid: string | null
  created_at: string
  updated_at: string | null
  last_login_at: string | null
  project_count: number
  total_tokens: number
  has_api_key: boolean
}

export interface AdminUserListResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface AdminUserUpdate {
  nickname?: string
  email?: string
  is_superuser?: boolean
}

export interface AdminUserCreate {
  username: string
  email: string
  password: string
}

export interface ApiKeyResponse {
  api_key: string
}

export interface AdminStats {
  total_users: number
  active_users: number
  superuser_count: number
  total_projects: number
  total_tokens: number
}

export interface ListUsersParams {
  page?: number
  page_size?: number
  search?: string
  is_active?: boolean
  is_superuser?: boolean
}

// 获取用户列表
export function getUsers(params: ListUsersParams = {}): Promise<AdminUserListResponse> {
  return request.get<AdminUserListResponse>('/admin/users', { params })
}

// 获取用户详情
export function getUser(id: number): Promise<AdminUser> {
  return request.get<AdminUser>(`/admin/users/${id}`)
}

// 编辑用户
export function updateUser(id: number, data: AdminUserUpdate): Promise<AdminUser> {
  return request.put<AdminUser>(`/admin/users/${id}`, data)
}

// 启用/禁用用户
export function toggleUserActive(id: number): Promise<AdminUser> {
  return request.post<AdminUser>(`/admin/users/${id}/toggle-active`)
}

// 重置用户密码
export function resetUserPassword(id: number, newPassword: string): Promise<void> {
  return request.post(`/admin/users/${id}/reset-password`, { new_password: newPassword })
}

// 创建用户
export function createUser(data: AdminUserCreate): Promise<AdminUser> {
  return request.post<AdminUser>('/admin/users', data)
}

// 生成/重新生成 API Key
export function generateApiKey(userId: number): Promise<ApiKeyResponse> {
  return request.post<ApiKeyResponse>(`/admin/users/${userId}/api-key`)
}

// 获取现有 API Key
export function getApiKey(userId: number): Promise<ApiKeyResponse> {
  return request.get<ApiKeyResponse>(`/admin/users/${userId}/api-key`)
}

// 获取系统统计
export function getStats(): Promise<AdminStats> {
  return request.get<AdminStats>('/admin/stats')
}

// ========== Token 使用统计 ==========

export interface UserTokenSummary {
  user_id: number
  username: string
  nickname: string | null
  total_tokens: number
  input_tokens: number
  output_tokens: number
  call_count: number
}

export interface ProviderTokenSummary {
  provider: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  call_count: number
}

export interface TokenUsageStats {
  total_tokens: number
  total_input_tokens: number
  total_output_tokens: number
  total_calls: number
  by_provider: ProviderTokenSummary[]
  by_user: UserTokenSummary[]
}

export interface TokenUsageRecord {
  id: number
  user_id: number
  username: string
  project_id: number | null
  provider: string
  model: string
  action: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  created_at: string
}

export interface TokenUsageListResponse {
  items: TokenUsageRecord[]
  total: number
  page: number
  page_size: number
}

// 获取 Token 使用统计
export function getTokenUsageStats(days: number = 30): Promise<TokenUsageStats> {
  return request.get<TokenUsageStats>('/admin/token-usage/stats', { params: { days } })
}

export interface DailyTokenUsage {
  date: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  call_count: number
}

// 获取每日 Token 趋势
export function getDailyTokenUsage(days: number = 30): Promise<DailyTokenUsage[]> {
  return request.get<DailyTokenUsage[]>('/admin/token-usage/daily', { params: { days } })
}

// 获取 Token 使用记录
export function getTokenUsageRecords(params: {
  page?: number
  page_size?: number
  user_id?: number
  provider?: string
} = {}): Promise<TokenUsageListResponse> {
  return request.get<TokenUsageListResponse>('/admin/token-usage/records', { params })
}

// ========== 项目管理 ==========

export interface AdminProject {
  id: number
  title: string
  description: string | null
  genre: string | null
  status: string
  current_word_count: number
  target_word_count: number
  owner_id: number
  owner_username: string
  owner_nickname: string | null
  owner_email: string
  created_at: string
  updated_at: string | null
}

export interface AdminProjectListResponse {
  items: AdminProject[]
  total: number
  page: number
  page_size: number
}

// 获取所有用户的项目列表
export function getAllProjects(params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
  user_id?: number
} = {}): Promise<AdminProjectListResponse> {
  return request.get<AdminProjectListResponse>('/admin/projects', { params })
}
