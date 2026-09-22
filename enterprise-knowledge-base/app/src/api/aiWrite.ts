import client from './client'

export interface AnalyzeResult {
  topic: string
  suggested_template_ids: number[]
  word_count_min: number
  word_count_max: number
  recommended_photo_count: number
  photo_search_keywords: string[]
}

export async function analyzeIntent(description: string): Promise<AnalyzeResult> {
  const { data } = await client.post('/admin/articles/ai-write/analyze', { description })
  return data
}
