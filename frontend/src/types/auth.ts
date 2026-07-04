export interface User {
  id: number
  username: string
  email: string
}

export interface LoginDTO {
  username: string
  password: string
}

export interface RegisterDTO {
  username: string
  email: string
  password: string
}

export interface AuthResponse {
  access: string
  refresh: string
}
