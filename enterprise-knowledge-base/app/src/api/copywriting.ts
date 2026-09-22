import client from './client'
import type { PaginatedResponse } from './documents'

export interface HotTopicItem {
  rank: number
  title: string
  hot_value: number
  url: string
  source?: string
  cover?: string
  id?: number
}

export interface HotTopicSource {
  label: string
  items: HotTopicItem[]
}

export interface CopyHotTopicsResponse {
  sources: Record<string, HotTopicSource>
  updated_at: number
}

export interface TitleRecommendItem {
  title: string
  hot_word: string
  hot_url: string
  cover: string
  reason: string
}

export interface TitlesRecommendResponse {
  recommendations: TitleRecommendItem[]
  hot_count: number
}

export interface MaterialEntry {
  ok: boolean
  filename: string
  type: string
  description: string
  object_name: string | null
}

export interface ScriptItem {
  id: number
  user_id: number
  title: string
  hot_word: string | null
  hot_url: string | null
  voiceover: string
  storyboard: string | null
  material_notes: string | null
  requirement: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ManualHotCreate {
  title: string
  url?: string
  source?: string
  sort_order?: number
}

// ========== 热点 ==========

export async function getCopyHotTopics(refresh = false): Promise<CopyHotTopicsResponse> {
  const { data } = await client.get('/admin/copywriting/hot-topics', { params: { refresh } })
  return data
}

export async function createManualHot(payload: ManualHotCreate): Promise<{ id: number }> {
  const { data } = await client.post('/admin/copywriting/hot-topics/manual', payload)
  return data
}

export async function deleteManualHot(id: number): Promise<void> {
  await client.delete(`/admin/copywriting/hot-topics/manual/${id}`)
}

export async function clearManualHot(): Promise<{ ok: boolean; deleted: number }> {
  const { data } = await client.delete('/admin/copywriting/hot-topics/manual')
  return data
}

// ========== 文案标题推荐 ==========

export async function recommendCopyTitles(count = 10, includeManual = true): Promise<TitlesRecommendResponse> {
  const { data } = await client.post('/admin/copywriting/titles/recommend', {
    count,
    include_manual: includeManual,
  }, { timeout: 120000 })
  return data
}

// ========== 素材 ==========

export async function uploadMaterials(files: File[]): Promise<{ entries: MaterialEntry[]; count: number }> {
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  const { data } = await client.post('/admin/copywriting/materials/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

export async function importLink(url: string): Promise<{ url: string; content: string; content_length: number }> {
  const { data } = await client.post('/admin/copywriting/materials/import-link', { url }, { timeout: 60000 })
  return data
}

// ========== 脚本 ==========

export async function generateScript(params: {
  title: string
  hot_word?: string
  hot_url?: string
  requirement?: string
  material_entries?: MaterialEntry[]
  material_notes?: string
}): Promise<ScriptItem> {
  const { data } = await client.post('/admin/copywriting/scripts/generate', params, { timeout: 120000 })
  return data
}

export async function getScripts(params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<ScriptItem>> {
  const { data } = await client.get('/admin/copywriting/scripts', { params })
  return data
}

export async function getScript(id: number): Promise<ScriptItem> {
  const { data } = await client.get(`/admin/copywriting/scripts/${id}`)
  return data
}

export async function updateScript(id: number, body: Partial<Pick<ScriptItem, 'title' | 'hot_word' | 'hot_url' | 'voiceover' | 'storyboard' | 'requirement' | 'status'>>): Promise<ScriptItem> {
  const { data } = await client.put(`/admin/copywriting/scripts/${id}`, body)
  return data
}

export async function deleteScript(id: number): Promise<void> {
  await client.delete(`/admin/copywriting/scripts/${id}`)
}

export async function exportScript(id: number, format: 'md' | 'txt' | 'html' | 'docx' | 'pdf'): Promise<Blob> {
  const { data } = await client.get(`/admin/copywriting/scripts/${id}/export`, {
    params: { format },
    responseType: 'blob',
  })
  return data
}
