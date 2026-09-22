import client from './client'

export interface ScopePermission {
  id: number
  role: string
  scope: string
  is_active: boolean
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export async function fetchPermissions(): Promise<ScopePermission[]> {
  const { data } = await client.get<Paginated<ScopePermission> | ScopePermission[]>('/admin/scope-permissions')
  return Array.isArray(data) ? data : (data.items ?? [])
}

export async function createPermission(body: { role: string; scope: string; is_active?: boolean }): Promise<ScopePermission> {
  const { data } = await client.post('/admin/scope-permissions', body)
  return data
}

export async function updatePermission(id: number, body: { is_active: boolean }): Promise<ScopePermission> {
  const { data } = await client.put(`/admin/scope-permissions/${id}`, body)
  return data
}

export async function deletePermission(id: number): Promise<void> {
  await client.delete(`/admin/scope-permissions/${id}`)
}

export async function createDefaults(): Promise<{ created: number }> {
  const { data } = await client.post('/admin/scope-permissions/defaults')
  return data
}

export async function reloadCache(): Promise<{ status: string }> {
  const { data } = await client.post('/admin/scope-permissions/reload')
  return data
}
