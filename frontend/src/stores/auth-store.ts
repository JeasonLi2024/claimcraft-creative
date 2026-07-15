import { create } from "zustand"
import { authApi } from "@/lib/api"
import { clearStoredAuth, persistTokens } from "@/lib/api-client"
import type { AuthResponse, LoginDTO, LoginEmailCodeDTO, RegisterDTO, User } from "@/types"

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  currentSessionId: number | null
  isAuthenticated: boolean
  isLoading: boolean
  isInitialized: boolean
  setAuthSession: (payload: {
    user: User
    accessToken: string
    refreshToken: string
    sessionId: number | null
  }) => void
  applyAuthResponse: (payload: AuthResponse) => void
  setUser: (user: User | null) => void
  clearAuth: () => void
  login: (data: LoginDTO) => Promise<void>
  loginWithEmailCode: (data: LoginEmailCodeDTO) => Promise<void>
  register: (data: RegisterDTO) => Promise<void>
  fetchMe: () => Promise<void>
  initialize: () => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  accessToken: localStorage.getItem("access_token"),
  refreshToken: localStorage.getItem("refresh_token"),
  currentSessionId: (() => {
    const value = localStorage.getItem("current_session_id")
    return value ? Number(value) : null
  })(),
  isAuthenticated: !!localStorage.getItem("access_token"),
  isLoading: false,
  isInitialized: false,

  setAuthSession: ({ user, accessToken, refreshToken, sessionId }) => {
    persistTokens(accessToken, refreshToken, sessionId)
    set({
      user,
      accessToken,
      refreshToken,
      currentSessionId: sessionId,
      isAuthenticated: true,
    })
  },

  setUser: (user) => set({ user }),

  applyAuthResponse: (payload: AuthResponse) => {
    get().setAuthSession({
      user: payload.user,
      accessToken: payload.access,
      refreshToken: payload.refresh,
      sessionId: payload.session_id,
    })
  },

  clearAuth: () => {
    clearStoredAuth()
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      currentSessionId: null,
      isAuthenticated: false,
    })
  },

  login: async (data) => {
    set({ isLoading: true })
    try {
      const res = await authApi.login(data)
      get().applyAuthResponse(res)
    } finally {
      set({ isLoading: false })
    }
  },

  loginWithEmailCode: async (data) => {
    set({ isLoading: true })
    try {
      const res = await authApi.loginWithEmailCode(data)
      get().applyAuthResponse(res)
    } finally {
      set({ isLoading: false })
    }
  },

  register: async (data) => {
    set({ isLoading: true })
    try {
      await authApi.register(data)
      await get().login({ account: data.username, password: data.password })
    } finally {
      set({ isLoading: false })
    }
  },

  fetchMe: async () => {
    const token = get().accessToken
    if (!token) return
    try {
      const user = await authApi.me()
      set({ user })
    } catch {
      get().clearAuth()
    }
  },

  initialize: async () => {
    if (get().isInitialized) return

    const token = get().accessToken
    if (!token) {
      set({ isInitialized: true, isAuthenticated: false })
      return
    }

    try {
      await get().fetchMe()
      set({ isInitialized: true, isAuthenticated: true })
    } catch {
      get().clearAuth()
      set({ isInitialized: true, isAuthenticated: false })
    }
  },

  logout: async () => {
    const refreshToken = get().refreshToken
    try {
      if (refreshToken) {
        await authApi.logout(refreshToken)
      }
    } finally {
      get().clearAuth()
    }
  },
}))
