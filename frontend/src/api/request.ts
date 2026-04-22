import axios from 'axios'
import { ElMessage } from 'element-plus'

// Token 存储 key
const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const USER_KEY = 'user'

// 创建 axios 实例
const instance = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 获取存储的 token
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

// 设置 token
export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

// 清除 token
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 获取存储的用户信息
export function getStoredUser(): any {
  const user = localStorage.getItem(USER_KEY)
  return user ? JSON.parse(user) : null
}

// 设置用户信息
export function setStoredUser(user: any): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

// 检查是否在登录/注册页面
function isAuthPage(): boolean {
  const path = window.location.pathname
  return path === '/login' || path === '/register'
}

// 共享 refresh 流程：多个请求同时 401 时只发一次刷新请求
let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessTokenShared(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return null
    try {
      const resp = await axios.post('/api/v1/auth/refresh', {}, {
        headers: { Authorization: `Bearer ${refreshToken}` },
      })
      const { access_token, refresh_token } = resp.data
      setTokens(access_token, refresh_token)
      return access_token as string
    } catch {
      return null
    }
  })()
  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

/**
 * 带鉴权的 fetch。用于 SSE 流式 / blob 下载等 axios 不适用的场景。
 * - 自动从 localStorage 读取 access_token 写入 Authorization
 * - 收到 401 时通过 refresh_token 刷新并自动重试一次
 * - 刷新失败则清空登录态并跳转 /login
 */
export async function authedFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const buildHeaders = (token: string | null): Headers => {
    const headers = new Headers(init.headers)
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    return headers
  }

  let response = await fetch(url, { ...init, headers: buildHeaders(getAccessToken()) })

  if (response.status === 401) {
    const newToken = await refreshAccessTokenShared()
    if (newToken) {
      response = await fetch(url, { ...init, headers: buildHeaders(newToken) })
      if (response.status === 401) {
        clearTokens()
        if (!isAuthPage()) window.location.href = '/login'
      }
    } else {
      clearTokens()
      if (!isAuthPage()) window.location.href = '/login'
    }
  }

  return response
}

// 请求拦截器 - 添加 Token
instance.interceptors.request.use(
  (config) => {
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 处理错误和 Token 刷新
instance.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    const originalRequest = error.config

    // 401 错误且未尝试过刷新
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = getRefreshToken()
      if (refreshToken) {
        try {
          // 尝试刷新 token
          const response = await axios.post('/api/v1/auth/refresh', {}, {
            headers: {
              Authorization: `Bearer ${refreshToken}`,
            },
          })

          const { access_token, refresh_token } = response.data
          setTokens(access_token, refresh_token)

          // 重试原请求
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return instance(originalRequest)
        } catch {
          // 刷新失败，清除登录状态
          clearTokens()
          // 只在非认证页面跳转到登录页
          if (!isAuthPage()) {
            window.location.href = '/login'
          }
          return Promise.reject(error)
        }
      } else {
        // 没有 refresh token，清除状态
        clearTokens()
        // 只在非认证页面跳转到登录页
        if (!isAuthPage()) {
          window.location.href = '/login'
        }
      }
    }

    // 在认证页面不显示 401 错误消息
    if (error.response?.status === 401 && isAuthPage()) {
      return Promise.reject(error)
    }

    // 统一错误处理
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '请求失败，请稍后重试'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

// 封装请求方法
export const request = {
  get<T>(url: string, config?: object): Promise<T> {
    return instance.get(url, config) as Promise<T>
  },
  post<T>(url: string, data?: object, config?: object): Promise<T> {
    return instance.post(url, data, config) as Promise<T>
  },
  put<T>(url: string, data?: object, config?: object): Promise<T> {
    return instance.put(url, data, config) as Promise<T>
  },
  delete<T>(url: string, config?: object): Promise<T> {
    return instance.delete(url, config) as Promise<T>
  },
}

export default request