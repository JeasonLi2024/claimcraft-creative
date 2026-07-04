import axios from 'axios'
import router from '../router'

// axios 实例：baseURL 使用相对路径，dev 由 vite proxy 代理到后端，prod 同源
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：注入 JWT
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 → 清除 token + 跳转登录
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      // 避免在登录页本身触发跳转
      if (router.currentRoute.value.name !== 'login') {
        router.push('/login')
      }
    }
    return Promise.reject(err)
  }
)

export default api
