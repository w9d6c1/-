import client from './client'

export interface SourceContent {
  id: number
  title: string
  scope: string
  status: string
  source_type: string
  source_name: string | null
  original_url: string | null
  publish_time: string | null
  word_count: number
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface SourceLink {
  id: number
  doc_id: number
  platform: string
  external_id: string
  original_url: string | null
  source_name: string | null
  publish_time: string | null
  is_primary: boolean
  created_at: string
}

export interface SourceContentDetail extends SourceContent {
  source_links: SourceLink[]
}

export interface SyncState {
  platform: string
  last_cursor: string | null
  last_sync_at: string | null
  last_status: string
  last_error: string | null
}

export interface SyncLog {
  id: number
  platform: string
  started_at: string
  finished_at: string | null
  fetched_count: number
  ingested_count: number
  duplicated_count: number
  status: string
  error: string | null
}

export interface SyncTriggerResult {
  total_fetched: number
  total_ingested: number
  failed_platforms: string[]
  all_ok: boolean
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SourceContentListParams {
  page?: number
  page_size?: number
  source_type?: string
  status?: string
  search?: string
}

export async function fetchSourceContents(params?: SourceContentListParams): Promise<Paginated<SourceContent>> {
  const { data } = await client.get('/admin/source-contents', { params })
  return data
}

export async function fetchSourceContentDetail(id: number): Promise<SourceContentDetail> {
  const { data } = await client.get(`/admin/source-contents/${id}`)
  return data
}

export async function updateSourceContentStatus(id: number, status: 'online' | 'offline'): Promise<SourceContent> {
  const { data } = await client.put(`/admin/source-contents/${id}/status`, { status })
  return data
}

export async function deleteSourceContent(id: number): Promise<void> {
  await client.delete(`/admin/source-contents/${id}`)
}

export async function mergeSourceContents(primaryDocId: number, duplicateDocId: number): Promise<SourceContent> {
  const { data } = await client.post('/admin/source-contents/merge', {
    primary_doc_id: primaryDocId,
    duplicate_doc_id: duplicateDocId,
  })
  return data
}

export async function triggerSync(platforms?: string[]): Promise<SyncTriggerResult> {
  const { data } = await client.post('/admin/source-contents/sync', { platforms: platforms || null })
  return data
}

export async function fetchPreviewUrl(id: number): Promise<string> {
  const { data } = await client.get(`/admin/source-contents/${id}/preview-url`)
  return data.url
}

export async function fetchSyncStates(): Promise<SyncState[]> {
  const { data } = await client.get('/admin/source-contents/sync-states')
  return data
}

export async function fetchSyncLogs(params?: { platform?: string; page?: number; page_size?: number }): Promise<Paginated<SyncLog>> {
  const { data } = await client.get('/admin/source-contents/sync-logs', { params })
  return data
}
