import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/projects',
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { title: '注册', guest: true },
  },
  {
    path: '/projects',
    name: 'ProjectList',
    component: () => import('@/views/ProjectListView.vue'),
    meta: { title: '我的项目', requiresAuth: true },
  },
  {
    path: '/project/:id',
    name: 'Workbench',
    component: () => import('@/views/WorkbenchView.vue'),
    meta: { title: '创作工作台', requiresAuth: true },
  },
  {
    path: '/wizard',
    name: 'CreationWizard',
    component: () => import('@/views/CreationWizardView.vue'),
    meta: { title: '创作向导', requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { title: '管理后台', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/drama',
    name: 'DramaList',
    component: () => import('@/views/DramaListView.vue'),
    meta: { title: '我的剧本', requiresAuth: true },
  },
  {
    path: '/drama/create',
    name: 'DramaCreate',
    component: () => import('@/views/DramaCreateView.vue'),
    meta: { title: '创建剧本', requiresAuth: true },
  },
  {
    path: '/drama/wizard/:id',
    name: 'DramaWizard',
    component: () => import('@/views/DramaWizardView.vue'),
    meta: { title: 'AI剧本引导', requiresAuth: true },
  },
  {
    path: '/drama/workbench/:id',
    name: 'DramaWorkbench',
    component: () => import('@/views/DramaWorkbenchView.vue'),
    meta: { title: '剧本工作台', requiresAuth: true },
  },
  {
    path: '/expansion',
    name: 'ExpansionList',
    component: () => import('@/views/ExpansionListView.vue'),
    meta: { title: '文本扩写', requiresAuth: true },
  },
  {
    path: '/expansion/create',
    name: 'ExpansionCreate',
    component: () => import('@/views/ExpansionCreateView.vue'),
    meta: { title: '创建扩写项目', requiresAuth: true },
  },
  {
    path: '/expansion/analyze/:id',
    name: 'ExpansionAnalyze',
    component: () => import('@/views/ExpansionAnalyzeView.vue'),
    meta: { title: '文本分析', requiresAuth: true },
  },
  {
    path: '/expansion/workbench/:id',
    name: 'ExpansionWorkbench',
    component: () => import('@/views/ExpansionWorkbenchView.vue'),
    meta: { title: '扩写工作台', requiresAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/projects',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // 初始化用户状态
  if (!userStore.initialized) {
    await userStore.init()
  }

  // 需要认证的路由
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  // 需要管理员权限的路由
  if (to.meta.requiresAdmin && !userStore.is_superuser) {
    next({ name: 'ProjectList' })
    return
  }

  // 游客路由（已登录用户不能访问）
  if (to.meta.guest && userStore.isLoggedIn) {
    next({ name: 'ProjectList' })
    return
  }

  next()
})

// 动态页面标题
router.afterEach((to) => {
  const title = (to.meta.title as string) || 'AI小说创作平台'
  document.title = `${title} - AI小说创作平台`
})

export default router