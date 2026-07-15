export interface UserPreferences {
  workflow_reminders: boolean
  export_reminder: boolean
  compact_case_cards: boolean
  default_case_mode: "complain" | "respond"
  default_template_type: "platform" | "regulatory" | "arbitration"
}

export interface UserSummary {
  id: number
  username: string
  email: string
  display_name: string
  email_verified: boolean
  avatar_url: string
}

export interface User extends UserSummary {
  bio: string
  locale: string
  timezone: string
  avatar_updated_at: string | null
  date_joined: string | null
  last_login: string | null
  preferences: UserPreferences
}

export interface UserProfileUpdateDTO {
  display_name?: string
  bio?: string
  locale?: string
  timezone?: string
}

export interface LoginDTO {
  account: string
  password: string
}

export interface RegisterDTO {
  username: string
  email: string
  password: string
  password_confirm: string
}

export interface AuthResponse {
  access: string
  refresh: string
  access_expires_in: number
  refresh_expires_in: number
  session_id: number
  user: User
}

export interface RefreshResponse {
  access: string
  refresh: string
  access_expires_in: number
  refresh_expires_in: number
  session_id: number | null
}

export interface LogoutAllResponse {
  detail: string
  revoked_sessions: number
}

export interface ChangePasswordDTO {
  old_password: string
  new_password: string
  new_password_confirm: string
  logout_other_sessions?: boolean
  current_session_id?: number | null
}

export interface ChangePasswordResponse {
  detail: string
  revoked_other_sessions: number
}

export interface AvatarMutationResponse {
  detail: string
  user: User
}

export type EmailVerificationScene =
  | "register_email"
  | "login_email"
  | "verify_current_email"
  | "change_email"
  | "reset_password"
  | "change_password_email"

export interface EmailCodeSendDTO {
  email: string
}

export interface EmailCodeSendResponse {
  detail: string
  scene: EmailVerificationScene
  target_email: string
  expires_at: string
  provider: string
}

export interface EmailCodeVerifyDTO {
  code: string
}

export interface RegisterEmailCodeVerifyDTO extends EmailCodeVerifyDTO {
  email: string
}

export interface EmailCodeVerifyResponse {
  detail: string
  scene: EmailVerificationScene
  target_email: string
  verified_at?: string | null
}

export interface LoginEmailCodeDTO extends EmailCodeVerifyDTO {
  email: string
}

export interface PasswordResetVerifyDTO extends EmailCodeVerifyDTO {
  email: string
}

export interface PasswordResetConfirmDTO {
  email: string
  new_password: string
  new_password_confirm: string
}

export interface PasswordResetConfirmResponse {
  detail: string
  revoked_sessions: number
}

export interface EmailChangeRequestDTO {
  new_email: string
}

export interface EmailChangeConfirmDTO extends EmailCodeVerifyDTO {
  new_email: string
}

export interface EmailUserMutationResponse {
  detail: string
  user: User
}

export interface UserSession {
  id: number
  device_name: string
  device_type: string
  created_at: string
  last_seen_at: string | null
  expires_at: string | null
  revoked_at: string | null
  is_current: boolean
}
