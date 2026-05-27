<template>
  <div class="prose-create">
    <h2>新建散文改写项目</h2>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="上传剧本" prop="file">
        <el-upload
          class="script-uploader"
          :auto-upload="false"
          :multiple="false"
          :limit="1"
          accept=".txt,.docx"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :file-list="fileList"
        >
          <el-button type="primary" plain>选择文件</el-button>
          <template #tip>
            <div class="el-upload__tip">支持 .txt 和 .docx 格式，文件内容按段落拆分为场景</div>
          </template>
        </el-upload>
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
        <el-input v-model="form.title" placeholder="留空则自动以文件名生成" />
      </el-form-item>

      <el-form-item label="题材">
        <el-select
          v-model="form.genre"
          clearable
          placeholder="可选"
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
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, UploadFile, UploadFiles } from 'element-plus'
import { proseApi } from '@/api/prose'

const router = useRouter()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive({
  file: null as File | null,
  premise: '',
  title: '',
  genre: '',
})

const fileList = ref<UploadFile[]>([])

const rules = {
  file: [{ required: true, validator: (_: any, __: any, cb: any) => {
    form.file ? cb() : cb(new Error('请上传剧本文件'))
  }, trigger: 'change' }],
  premise: [
    { required: true, message: '请输入故事梗概', trigger: 'blur' },
    { min: 5, max: 500, message: '梗概长度 5-500 字', trigger: 'blur' },
  ],
}

const genres = ['都市言情', '悬疑', '古风', '现实', '职场', '家庭', '其他']

function handleFileChange(_file: UploadFile, files: UploadFiles) {
  const last = files[files.length - 1]
  form.file = last?.raw ?? null
}

function handleFileRemove() {
  form.file = null
  fileList.value = []
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const res = await proseApi.create({
      file: form.file!,
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
</script>

<style scoped>
.prose-create {
  padding: 24px;
  max-width: 640px;
  margin: 0 auto;
}
.script-uploader {
  width: 100%;
}
</style>
