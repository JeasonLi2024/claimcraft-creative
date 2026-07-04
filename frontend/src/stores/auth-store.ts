import { create } from "zustand"
import { authApi } from "@/lib/api"
import type { User, LoginDTO, RegisterDTO } from "@/types"

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  login: (data: LoginDTO) => Promise<void>
  register: (data: RegisterDTO) => Promise<void>
  fetchMe: () => Promise<void>
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  isAuthenticated: !!localStorage.getItem("access_token"),
  isLoading: false,

  setAuth: (user, token) => {
    localStorage.setItem("access_token", token)
    set({ user, token, isAuthenticated: true })
  },

  clearAuth: () => {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    set({ user: null, token: null, isAuthenticated: false })
  },

  login: async (data) => {
    set({ isLoading: true })
    try {
      const res = await authApi.login(data)
      get().setAuth({ id: 0, username: "", email: "" } as User, res.access)
      await get().fetchMe()
    } finally {
      set({ isLoading: false })
    }
  },

  register: async (data) => {
    set({ isLoading: true })
    try {
      await authApi.register(data)
      await get().login({ username: data.username, password: data.password })
    } finally {
      set({ isLoading: false })
    }
  },

  fetchMe: async () => {
    const token = get().token
    if (!token) return
    try {
      const user = await authApi.me()
      set({ user })
    } catch {
      get().clearAuth()
    }
  },

  initialize: async () => {
    const token = get().token
    if (token) {
      await get().fetchMe()
    }
  },
}))
