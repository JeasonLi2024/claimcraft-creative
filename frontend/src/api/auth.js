import api from './index'

export const login = (data) => api.post('/auth/login/', data)
export const register = (data) => api.post('/auth/register/', data)
export const refreshToken = (data) => api.post('/auth/refresh/', data)
export const getMe = () => api.get('/auth/me/')
