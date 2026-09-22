import client from './client'
import type { PaginatedResponse } from './documents'

export interface UserItem {
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

export async function getUsers(params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<UserItem>> {
  const { data } = await client.get('/admin/users', { params })
  return data
}

export async function getUser(id: number): Promise<UserItem> {
  const { data } = await client.get(`/admin/users/${id}`)
  return data
}

export async function updateUser(id: number, body: {
  role?: string
  department?: string
  display_name?: string
  is_active?: boolean
}): Promise<UserItem> {
  const { data } = await client.put(`/admin/users/${id}`, body)
  return data
}

export async function deleteUser(id: number): Promise<void> {
  await client.delete(`/admin/users/${id}`)
}

export interface BulkDeleteResult {
  deleted: number
  failed: { id: number; reason: string }[]
}

export async function bulkDeleteUsers(ids: number[]): Promise<BulkDeleteResult> {
  const { data } = await client.post('/admin/users/bulk-delete', { ids })
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
}): Promise<UserItem> {
  const { data } = await client.post('/admin/auth/users', body)
  return data
}
