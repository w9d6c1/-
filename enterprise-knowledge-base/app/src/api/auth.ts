import client from './client'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: {
    id: number
    username: string
    phone: string | null
    display_name: string | null
    email: string | null
    role: string
    department: string | null
    is_active: boolean
    created_at: string
  }
}

export interface UserInfo {
  id: number
  username: string
  phone: string | null
  display_name: string | null
  email: string | null
  role: string
  department: string | null
  is_active: boolean
  created_at: string
}

export async function loginByPassword(params: LoginParams): Promise<LoginResult> {
  const form = new URLSearchParams()
  form.set('username', params.username)
  form.set('password', params.password)
  const { data } = await client.post<LoginResult>('/admin/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await client.get<UserInfo>('/admin/auth/me')
  return data
}

export interface SendCodeResult {
  status: string
  code?: string
}

export async function sendCode(phone: string): Promise<SendCodeResult> {
  const { data } = await client.post<SendCodeResult>('/admin/auth/send-code', { phone })
  return data
}

export async function phoneLogin(phone: string, code: string): Promise<LoginResult> {
  const { data } = await client.post<LoginResult>('/admin/auth/phone-login', { phone, code })
  return data
}

export async function createUser(body: {
  username: string
  password: string
  password_confirm: string
  display_name?: string
  email?: string
  phone?: string
  role?: string
  department?: string
}): Promise<UserInfo> {
  const { data } = await client.post<UserInfo>('/admin/auth/users', body)
  return data
}
