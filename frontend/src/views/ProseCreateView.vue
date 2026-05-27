<template>
  <div class="prose-create" style="padding: 24px; max-width: 640px; margin: 0 auto">
    <h2>新建散文改写项目</h2>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="来源剧本" prop="script_project_id">
        <el-select
          v-model="form.script_project_id"
          filterable
          placeholder="请选择剧本"
          style="width: 100%"
          :loading="loadingProjects"
        >
          <el-option
            v-for="sp in scriptProjects"
            :key="sp.id"
            :label="sp.title"
            :value="sp.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="故事梗概" prop="premise">
        <el-input
          v-model="form.premise"
          type="textarea"
          :rows="3"
          placeholder="用一句话描述故事的核心，例如：都市白领因一次偶遇邂逅前任，重燃旧情"
        />
      </el-form-item>

      <el-form-item label="项目标题">
        <el-input v-model="form.title" placeholder="留空则自动生成" />
      </el-form-item>

      <el-form-item label="题材">
        <el-select
          v-model="form.genre"
          clearable
          placeholder="可选，留空自动继承剧本题材"
          style="width: 100%"
        >
          <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          开始改写
        </el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { proseApi } from '@/api/prose'
import { getDramaProjects } from '@/api/drama'

const router = useRouter()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const loadingProjects = ref(false)

const form = reactive({
  script_project_id: null as number | null,
  premise: '',
  title: '',
  genre: '',
})

const rules = {
  script_project_id: [{ required: true, message: '请选择来源剧本', trigger: 'change' }],
  premise: [
    { required: true, message: '请输入故事梗概', trigger: 'blur' },
    { min: 5, max: 500, message: '梗概长度 5-500 字', trigger: 'blur' },
  ],
}

const genres = ['都市言情', '悬疑', '古风', '现实', '职场', '家庭', '其他']

interface ScriptProjectItem {
  id: number
  title: string
}

const scriptProjects = ref<ScriptProjectItem[]>([])

async function loadScriptProjects() {
  loadingProjects.value = true
  try {
    const projects = await getDramaProjects()
    scriptProjects.value = projects.map((p) => ({ id: p.id, title: p.title }))
  } catch {
    ElMessage.warning('无法加载剧本列表，请确认有已创建的剧本')
  } finally {
    loadingProjects.value = false
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const res = await proseApi.create({
      script_project_id: form.script_project_id!,
      premise: form.premise,
      title: form.title || undefined,
      genre: form.genre || undefined,
    })
    ElMessage.success('项目已创建，正在生成中…')
    router.push(`/prose/${res.id}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadScriptProjects)
</script>

<style scoped>
.prose-create {
  padding: 24px;
  max-width: 640px;
  margin: 0 auto;
}
</style>
