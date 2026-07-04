import { defineStore } from 'pinia'
import { login as apiLogin, register as apiRegister, getMe } from '../api/auth'

// ClaimCraft 认证状态管理
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('access_token') || null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
  },
  actions: {
    async login(credentials) {
      const res = await apiLogin(credentials)
      this.token = res.data.access
      localStorage.setItem('access_token', res.data.access)
      localStorage.setItem('refresh_token', res.data.refresh)
      await this.fetchMe()
      return res
    },
    async register(userData) {
      const res = await apiRegister(userData)
      // 注册成功后自动登录
      await this.login({ username: userData.username, password: userData.password })
      return res
    },
    async fetchMe() {
      if (!this.token) return
      try {
        const res = await getMe()
        this.user = res.data
      } catch {
        this.logout()
      }
    },
    logout() {
      this.user = null
      this.token = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    },
    async initialize() {
      if (this.token) {
        await this.fetchMe()
      }
    },
  },
})
