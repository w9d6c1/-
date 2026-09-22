import client from './client'

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface DocumentItem {
  id: number
  category_id: number
  title: string
  file_type: string | null
  file_size: number | null
  word_count: number
  scope: string
  status: string
  chunk_strategy: string
  chunk_count: number
  review_status: string
  review_comment: string | null
  department: string | null
  created_at: string
  updated_at: string
}

export interface DocumentDetail extends DocumentItem {
  plain_text: string | null
}

export interface ChunkItem {
  id: number
  doc_id: number
  chunk_index: number
  content: string
  page_number: number | null
  heading_path: string | null
  vector_id: string | null
  bm25_id: string | null
  last_sync_at: string | null
}

export interface CategoryItem {
  id: number
  parent_id: number | null
  name: string
  sort_order: number
  scope: string
  status: string
  department: string | null
  created_at: string
  children?: CategoryItem[]
}

export interface ParseResult {
  plain_text: string
  word_count: number
}

export async function getDocuments(params?: {
  page?: number
  page_size?: number
  category_id?: number
  scope?: string
  status?: string
}): Promise<PaginatedResponse<DocumentItem>> {
  const { data } = await client.get('/admin/documents', { params })
  return data
}

export async function getDocument(id: number): Promise<DocumentDetail> {
  const { data } = await client.get(`/admin/documents/${id}`)
  return data
}

export async function getDocumentChunks(id: number): Promise<ChunkItem[]> {
  const { data } = await client.get(`/admin/documents/${id}/chunks`)
  return data
}

export async function uploadDocument(file: File, fields: {
  title: string
  category_id: number
  scope?: string
  chunk_strategy?: string
  department?: string
}): Promise<DocumentItem> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('title', fields.title)
  fd.append('category_id', String(fields.category_id))
  if (fields.scope) fd.append('scope', fields.scope)
  if (fields.chunk_strategy) fd.append('chunk_strategy', fields.chunk_strategy)
  if (fields.department) fd.append('department', fields.department)
  const { data } = await client.post('/admin/documents/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function createDocumentByContent(body: {
  title: string
  content: string
  file_type: string
  category_id: number
  scope?: string
  chunk_strategy?: string
  department?: string
}): Promise<DocumentItem> {
  const { content, file_type, ...meta } = body
  const { data: doc } = await client.post('/admin/documents', meta)
  if (content) {
    const { data: updated } = await client.post(`/admin/documents/${doc.id}/content`, { content, file_type })
    return updated
  }
  return doc
}

export async function parseContent(content: string, file_type: string): Promise<ParseResult> {
  const { data } = await client.post('/admin/documents/parse', { content, file_type })
  return data
}

export async function chunkDocument(id: number): Promise<{ chunk_count: number }> {
  const { data } = await client.post(`/admin/documents/${id}/chunk`)
  return data
}

export async function resyncDocument(id: number): Promise<{ synced: number }> {
  const { data } = await client.post(`/admin/documents/${id}/resync`)
  return data
}

export async function deleteDocument(id: number): Promise<void> {
  await client.delete(`/admin/documents/${id}`)
}

export async function updateDocumentContent(id: number, content: string, file_type: string): Promise<DocumentItem> {
  const { data } = await client.post(`/admin/documents/${id}/content`, { content, file_type })
  return data
}

export async function reviewDocument(id: number, action: 'approve' | 'reject', comment?: string): Promise<DocumentItem> {
  const { data } = await client.post(`/admin/documents/${id}/review`, { action, comment })
  return data
}

export async function getCategories(): Promise<CategoryItem[]> {
  const { data } = await client.get('/admin/categories/tree')
  return data
}

export async function getDepartments(): Promise<string[]> {
  const { data } = await client.get('/admin/documents/departments')
  return data
}
