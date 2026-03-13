import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginRequest, RegisterRequest } from '@/api/auth'
import {
  login as loginApi,
  loginJson as loginJsonApi,
  register as registerApi,
  logout as logoutApi,
  getCurrentUser,
  getStoredUserInfo,
  clearToken,
  getAccessToken,
} from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  // 状态
  const user = ref<User | null>(getStoredUserInfo())
  const loading = ref(false)
  const initialized = ref(false)

  // 计算属性
  const isLoggedIn = computed(() => !!user.value)
  const is_superuser = computed(() => user.value?.is_superuser ?? false)

  // 初始化 - 从服务器获取用户信息
  async function init() {
    if (initialized.value) return

    // 如果没有 token，直接标记为已初始化，不请求服务器
    const token = getAccessToken()
    if (!token) {
      user.value = null
      initialized.value = true
      return
    }

    // 有 token，尝试获取用户信息
    try {
      const userData = await getCurrentUser()
      user.value = userData
    } catch {
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  // 登录
  async function login(credentials: LoginRequest) {
    loading.value = true
    try {
      await loginApi(credentials)
      user.value = await getCurrentUser()
      return true
    } catch (error) {
      throw error
    } finally {
      loading.value = false
    }
  }

  // JSON 格式登录
  async function loginJson(credentials: LoginRequest) {
    loading.value = true
    try {
      await loginJsonApi(credentials)
      user.value = await getCurrentUser()
      return true
    } catch (error) {
      throw error
    } finally {
      loading.value = false
    }
  }

  // 注册
  async function register(data: RegisterRequest) {
    loading.value = true
    try {
      await registerApi(data)
      user.value = await getCurrentUser()
      return true
    } catch (error) {
      throw error
    } finally {
      loading.value = false
    }
  }

  // 登出
  async function logout() {
    try {
      await logoutApi()
    } finally {
      user.value = null
      clearToken()
    }
  }

  // 更新用户信息
  async function fetchUser() {
    try {
      user.value = await getCurrentUser()
    } catch {
      user.value = null
    }
  }

  return {
    user,
    loading,
    initialized,
    isLoggedIn,
    is_superuser,
    init,
    login,
    loginJson,
    register,
    logout,
    fetchUser,
  }
})