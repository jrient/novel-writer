import request, { setTokens, setStoredUser, clearTokens, getStoredUser, getAccessToken } from './request'

export { getAccessToken }

export interface User {
  id: number
  username: string
  email: string
  nickname: string | null
  avatar_url: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
  last_login_at: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  invitation_code: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface OAuthAuthorizeResponse {
  authorize_url: string
}

// 登录
export async function login(data: LoginRequest): Promise<TokenResponse> {
  const formData = new FormData()
  formData.append('username', data.username)
  formData.append('password', data.password)

  const response = await request.post<TokenResponse>('/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  })

  setTokens(response.access_token, response.refresh_token)
  return response
}

// JSON 格式登录
export async function loginJson(data: LoginRequest): Promise<TokenResponse> {
  const response = await request.post<TokenResponse>('/auth/login/json', data)
  setTokens(response.access_token, response.refresh_token)
  return response
}

// 注册
export async function register(data: RegisterRequest): Promise<TokenResponse> {
  const response = await request.post<TokenResponse>('/auth/register', data)
  setTokens(response.access_token, response.refresh_token)
  return response
}

// 登出
export async function logout(): Promise<void> {
  try {
    await request.post('/auth/logout')
  } finally {
    clearToken()
  }
}

// 清除本地登录状态
export function clearToken(): void {
  clearTokens()
}

// 获取当前用户信息
export async function getCurrentUser(): Promise<User> {
  const user = await request.get<User>('/auth/me')
  setStoredUser(user)
  return user
}

// 更新用户信息
export async function updateUser(data: { nickname?: string; avatar_url?: string }): Promise<User> {
  const user = await request.put<User>('/auth/me', data)
  setStoredUser(user)
  return user
}

// 修改密码
export async function changePassword(data: { old_password: string; new_password: string }): Promise<void> {
  await request.put('/auth/password', data)
}

// 刷新 Token
export async function refreshToken(): Promise<TokenResponse | null> {
  try {
    const response = await request.post<TokenResponse>('/auth/refresh')
    setTokens(response.access_token, response.refresh_token)
    return response
  } catch {
    clearTokens()
    return null
  }
}

// 获取存储的用户
export function getStoredUserInfo(): User | null {
  return getStoredUser()
}

// GitHub 登录
export async function getGithubAuthorizeUrl(): Promise<OAuthAuthorizeResponse> {
  return request.get<OAuthAuthorizeResponse>('/auth/github')
}

// 微信登录
export async function getWechatAuthorizeUrl(): Promise<OAuthAuthorizeResponse> {
  return request.get<OAuthAuthorizeResponse>('/auth/wechat')
}

// 邀请码相关
export interface Invitation {
  id: number
  code: string
  is_used: boolean
  used_by: number | null
  used_at: string | null
  expires_at: string | null
  created_by: number
  created_at: string
}

export async function createInvitations(count: number, expiresDays?: number): Promise<Invitation[]> {
  return request.post<Invitation[]>('/auth/invitations', {
    count,
    expires_days: expiresDays,
  })
}

export async function getInvitations(): Promise<Invitation[]> {
  return request.get<Invitation[]>('/auth/invitations')
}

export async function deleteInvitation(id: number): Promise<void> {
  await request.delete(`/auth/invitations/${id}`)
}