<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>AI 小说创作平台</h1>
        <p>登录您的账号</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名或邮箱"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="login-btn"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="oauth-section">
        <el-divider>
          <span class="divider-text">其他登录方式</span>
        </el-divider>
        <div class="oauth-buttons">
          <el-button
            v-if="githubEnabled"
            @click="handleGithubLogin"
          >
            <el-icon><Platform /></el-icon>
            GitHub 登录
          </el-button>
          <el-button
            v-if="wechatEnabled"
            @click="handleWechatLogin"
          >
            <el-icon><ChatDotRound /></el-icon>
            微信登录
          </el-button>
        </div>
      </div>

      <div class="login-footer">
        <span>还没有账号？</span>
        <router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Platform, ChatDotRound } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { getGithubAuthorizeUrl, getWechatAuthorizeUrl } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const githubEnabled = ref(false)
const wechatEnabled = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名或邮箱', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
  ],
}

async function handleLogin() {
  const valid = await formRef.value?.validate()
  if (!valid) return

  loading.value = true
  try {
    await userStore.login(form)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string
    router.push(redirect || '/projects')
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}

async function handleGithubLogin() {
  try {
    const { authorize_url } = await getGithubAuthorizeUrl()
    window.open(authorize_url, '_blank', 'width=600,height=800')
  } catch {
    ElMessage.error('获取 GitHub 授权链接失败')
  }
}

async function handleWechatLogin() {
  try {
    const { authorize_url } = await getWechatAuthorizeUrl()
    window.open(authorize_url, '_blank', 'width=600,height=800')
  } catch {
    ElMessage.error('获取微信授权链接失败')
  }
}

// 监听 OAuth 回调
function handleOAuthMessage(event: MessageEvent) {
  if (event.data?.type === 'oauth-success') {
    const { access_token, refresh_token, user } = event.data.data
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    localStorage.setItem('user', JSON.stringify(user))
    userStore.fetchUser()
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string
    router.push(redirect || '/projects')
  }
}

onMounted(() => {
  window.addEventListener('message', handleOAuthMessage)

  // 检查 OAuth 配置（通过尝试获取授权 URL 来判断是否启用）
  // 这里简化处理，实际应该通过后端 API 获取配置
  githubEnabled.value = true
  wechatEnabled.value = true
})
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  font-size: 24px;
  color: #333;
  margin-bottom: 8px;
}

.login-header p {
  color: #666;
  font-size: 14px;
}

.login-btn {
  width: 100%;
}

.oauth-section {
  margin-top: 20px;
}

.divider-text {
  color: #999;
  font-size: 12px;
}

.oauth-buttons {
  display: flex;
  justify-content: center;
  gap: 12px;
}

.login-footer {
  text-align: center;
  margin-top: 24px;
  color: #666;
  font-size: 14px;
}

.login-footer a {
  color: #409eff;
  margin-left: 4px;
}

.login-footer a:hover {
  text-decoration: underline;
}
</style>