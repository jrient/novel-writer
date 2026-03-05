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
  },
  {
    path: '/project/:id',
    name: 'Workbench',
    component: () => import('@/views/WorkbenchView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
