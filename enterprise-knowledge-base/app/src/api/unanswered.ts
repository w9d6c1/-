import client from './client'

export interface Unanswered {
  id: number
  thread_id: string
  question: string
  source: string
  status: string
  created_at: string
}

export async function fetchUnanswered(params?: { status?: string; source?: string; page?: number; per_page?: number }): Promise<Unanswered[]> {
  const { data } = await client.get('/admin/unanswered', { params })
  return data
}

export async function updateUnanswered(id: number, status: string): Promise<Unanswered> {
  const { data } = await client.patch(`/admin/unanswered/${id}`, { status })
  return data
}

export async function convertUnanswered(id: number): Promise<{ faq_id: number; question: string; generated_answer: string }> {
  const { data } = await client.post(`/admin/unanswered/${id}/convert`)
  return data
}
