import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean
}

const ACCESS_TOKEN_KEY = "access_token"
const REFRESH_TOKEN_KEY = "refresh_token"
const CURRENT_SESSION_ID_KEY = "current_session_id"

const apiClient = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
})

const refreshClient = axios.create({
  baseURL: "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
})

let refreshPromise: Promise<string | null> | null = null

function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

function persistTokens(accessToken: string, refreshToken: string, sessionId?: number | null) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  if (sessionId != null) {
    localStorage.setItem(CURRENT_SESSION_ID_KEY, String(sessionId))
  }
}

function clearStoredAuth() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(CURRENT_SESSION_ID_KEY)
}

function redirectToLogin() {
  if (window.location.pathname !== "/login") {
    window.location.href = "/login"
  }
}

async function refreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise
  }

  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearStoredAuth()
    return null
  }

  refreshPromise = refreshClient
    .post("/auth/refresh/", { refresh: refreshToken })
    .then((response) => {
      const { access, refresh, session_id } = response.data as {
        access: string
        refresh: string
        session_id?: number | null
      }
      persistTokens(access, refresh, session_id)
      return access
    })
    .catch(() => {
      clearStoredAuth()
      return null
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  const currentSessionId = localStorage.getItem(CURRENT_SESSION_ID_KEY)
  if (currentSessionId) {
    config.headers["X-Session-ID"] = currentSessionId
  }

  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined
    const statusCode = error.response?.status
    const url = originalRequest?.url || ""
    const isAuthBootstrapRequest = [
      "/auth/login/",
      "/auth/login/send-code/",
      "/auth/login/email-code/",
      "/auth/password-reset/send-code/",
      "/auth/password-reset/verify-code/",
      "/auth/password-reset/confirm/",
      "/auth/register/",
      "/auth/register/send-code/",
      "/auth/register/verify-code/",
      "/auth/refresh/",
    ].some((path) => url.includes(path))

    if (statusCode !== 401 || !originalRequest || originalRequest._retry || isAuthBootstrapRequest) {
      if (statusCode === 401 && isAuthBootstrapRequest) {
        clearStoredAuth()
      }
      return Promise.reject(error)
    }

    originalRequest._retry = true
    const newAccessToken = await refreshAccessToken()

    if (!newAccessToken) {
      redirectToLogin()
      return Promise.reject(error)
    }

    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
    return apiClient(originalRequest)
  },
)

export { clearStoredAuth, persistTokens, getAccessToken, getRefreshToken }
export default apiClient
