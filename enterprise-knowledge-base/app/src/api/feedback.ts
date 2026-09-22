import client from './client'

export interface Feedback {
  id: number
  thread_id: string
  rating: 'like' | 'dislike'
  suggestion: string | null
  user_id: number | null
  created_at: string
}

export interface FeedbackStats {
  total: number
  likes: number
  dislikes: number
}

export async function fetchFeedbacks(params?: { rating?: string; page?: number; per_page?: number }): Promise<Feedback[]> {
  const { data } = await client.get('/admin/feedbacks', { params })
  return data
}

export async function fetchFeedbackStats(): Promise<FeedbackStats> {
  const { data } = await client.get('/admin/feedbacks/stats')
  return data
}
