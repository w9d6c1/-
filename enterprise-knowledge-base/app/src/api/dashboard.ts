import client from './client'

export interface TrendPoint {
  date: string
  count: number
}

export interface DashboardStats {
  today_chats: number
  faq_hit_rate: number
  feedback_good_rate: number
  pending_reviews: number
  pending_unanswered: number
  trend: TrendPoint[]
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await client.get('/admin/dashboard/stats')
  return data
}
