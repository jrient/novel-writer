import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建 axios 实例
const instance = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
instance.interceptors.request.use(
  (config) => {
    // 可在此处添加 token 等认证信息
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
instance.interceptors.response.use(
  (response) => {
    // 直接返回响应数据
    return response.data
  },
  (error) => {
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

// 封装请求方法，返回正确的类型
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