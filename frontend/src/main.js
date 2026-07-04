import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './styles/main.css'

// 创建 Vue 应用，挂载 router 与 pinia，引入全局样式
const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// 初始化认证状态（拉取当前用户信息）后再挂载应用
const authStore = useAuthStore()
authStore.initialize().finally(() => {
  app.mount('#app')
})
