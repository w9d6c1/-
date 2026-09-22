import client from './client'

export interface Category {
  id: number
  parent_id: number | null
  name: string
  sort_order: number
  scope: string
  status: string
  department: string | null
  children?: Category[]
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CategoryPayload {
  name: string
  scope: string
  parent_id?: number | null
  sort_order?: number
  department?: string | null
}

export interface CategoryUpdatePayload {
  name?: string
  scope?: string
  parent_id?: number | null
  sort_order?: number
  status?: string
}

export async function getCategoryTree(): Promise<Category[]> {
  const { data } = await client.get('/admin/categories/tree')
  return data
}

export async function getCategoriesFlat(): Promise<Category[]> {
  const { data } = await client.get<Paginated<Category>>('/admin/categories', { params: { page_size: 500 } })
  return data.items ?? []
}

export async function createCategory(body: CategoryPayload): Promise<Category> {
  const { data } = await client.post('/admin/categories', body)
  return data
}

export async function updateCategory(id: number, body: CategoryUpdatePayload): Promise<Category> {
  const { data } = await client.put(`/admin/categories/${id}`, body)
  return data
}

export async function deleteCategory(id: number): Promise<void> {
  await client.delete(`/admin/categories/${id}`)
}

export async function batchDeleteCategories(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post('/admin/categories/bulk-delete', { ids })
  return data
}
