import client from './client'

export interface FAQ {
  id: number
  category_id: number
  question: string
  similar_questions: string[] | null
  answer: string
  tags: string[] | null
  scope: string
  status: string
  version: number
  review_status: string
  reviewer_id: number | null
  review_comment: string | null
  department: string | null
  effective_start: string | null
  effective_end: string | null
}

export interface FAQVersion {
  id: number
  version: number
  question: string
  answer: string
  similar_questions: string[] | null
  tags: string[] | null
  scope: string
  status: string
  created_at: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export async function fetchFAQs(page = 1, pageSize = 20): Promise<Paginated<FAQ>> {
  const { data } = await client.get('/admin/faqs', { params: { page, page_size: pageSize } })
  return data
}

export async function createFAQ(body: {
  category_id: number
  question: string
  answer: string
  scope?: string
  similar_questions?: string[]
  tags?: string[]
}): Promise<FAQ> {
  const { data } = await client.post('/admin/faqs', body)
  return data
}

export async function updateFAQ(id: number, body: Partial<FAQ>): Promise<FAQ> {
  const { data } = await client.put(`/admin/faqs/${id}`, body)
  return data
}

export async function deleteFAQ(id: number): Promise<void> {
  await client.delete(`/admin/faqs/${id}`)
}

export async function batchDeleteFAQs(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post('/admin/faqs/bulk-delete', { ids })
  return data
}

export async function submitForReview(id: number): Promise<FAQ> {
  const { data } = await client.post(`/admin/faqs/${id}/submit`)
  return data
}

export async function approveFAQ(id: number): Promise<FAQ> {
  const { data } = await client.post(`/admin/faqs/${id}/approve`)
  return data
}

export async function rejectFAQ(id: number, comment?: string): Promise<FAQ> {
  const { data } = await client.post(`/admin/faqs/${id}/reject`, { action: 'reject', comment: comment || null })
  return data
}

export async function getFAQVersions(id: number): Promise<FAQVersion[]> {
  const { data } = await client.get(`/admin/faqs/${id}/versions`)
  return data
}

export async function rollbackFAQ(id: number, versionId: number): Promise<FAQ> {
  const { data } = await client.post(`/admin/faqs/${id}/rollback/${versionId}`)
  return data
}
