import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getProjects,
  createProject,
  getProject,
  updateProject,
  deleteProject,
} from '@/api/project'
import type { Project, CreateProjectData, UpdateProjectData } from '@/api/project'

export const useProjectStore = defineStore('project', () => {
  // 状态
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)

  // 获取项目列表
  async function fetchProjects(status?: string) {
    loading.value = true
    try {
      projects.value = await getProjects(status)
    } finally {
      loading.value = false
    }
  }

  // 获取单个项目详情
  async function fetchProject(id: number) {
    loading.value = true
    try {
      currentProject.value = await getProject(id)
    } finally {
      loading.value = false
    }
  }

  // 创建新项目
  async function createNewProject(data: CreateProjectData) {
    const project = await createProject(data)
    projects.value.unshift(project)
    return project
  }

  // 更新项目信息
  async function updateCurrentProject(id: number, data: UpdateProjectData) {
    const updated = await updateProject(id, data)
    // 同步更新列表中的项目
    const index = projects.value.findIndex((p) => p.id === id)
    if (index !== -1) {
      projects.value[index] = updated
    }
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  // 删除项目
  async function removeProject(id: number) {
    await deleteProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) {
      currentProject.value = null
    }
  }

  return {
    projects,
    currentProject,
    loading,
    fetchProjects,
    fetchProject,
    createNewProject,
    updateCurrentProject,
    removeProject,
  }
})
