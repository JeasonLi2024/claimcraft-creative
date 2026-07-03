import axios from 'axios'

// axios 实例：baseURL 指向 Django 后端 API
const api = axios.create({ baseURL: 'http://localhost:8000/api' })

export default api
