import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/projects',
  },
  {
    path: '/projects',
    name: 'ProjectList',
    component: () => import('@/views/ProjectListView.vue'),
    meta: { title: '我的项目' },
  },
  {
    path: '/project/:id',
    name: 'Workbench',
    component: () => import('@/views/WorkbenchView.vue'),
    meta: { title: '创作工作台' },
  },
  {
    path: '/wizard',
    name: 'CreationWizard',
    component: () => import('@/views/CreationWizardView.vue'),
    meta: { title: '创作向导' },
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

// 动态页面标题
router.afterEach((to) => {
  const title = (to.meta.title as string) || 'AI小说创作平台'
  document.title = `${title} - AI小说创作平台`
})

export default router
