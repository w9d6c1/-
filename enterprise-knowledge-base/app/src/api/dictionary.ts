import client from './client'

export interface Synonym {
  id: number
  word: string
  synonyms: string[]
  scope: string
}

export interface SensitiveWord {
  id: number
  word: string
  word_type: string
  answer: string | null
  scope: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface BatchImportResult {
  imported: number
  skipped: number
  errors: string[]
}

// ── 同义词 ──
export async function fetchSynonyms(page = 1, pageSize = 50): Promise<Paginated<Synonym>> {
  const { data } = await client.get('/admin/synonyms', { params: { page, page_size: pageSize } })
  return data
}

export async function createSynonym(word: string, synonyms: string[], scope = 'public'): Promise<Synonym> {
  const { data } = await client.post('/admin/synonyms', { word, synonyms, scope })
  return data
}

export async function updateSynonym(id: number, body: Partial<Synonym>): Promise<Synonym> {
  const { data } = await client.put(`/admin/synonyms/${id}`, body)
  return data
}

export async function deleteSynonym(id: number): Promise<void> {
  await client.delete(`/admin/synonyms/${id}`)
}

export async function batchDeleteSynonyms(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post('/admin/synonyms/bulk-delete', { ids })
  return data
}

export async function importSynonymsCsv(file: File): Promise<BatchImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await client.post('/admin/synonyms/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  return data
}

// ── 敏感词 ──
export async function fetchSensitiveWords(page = 1, pageSize = 50): Promise<Paginated<SensitiveWord>> {
  const { data } = await client.get('/admin/sensitive-words', { params: { page, page_size: pageSize } })
  return data
}

export async function createSensitiveWord(word: string, answer?: string): Promise<SensitiveWord> {
  const { data } = await client.post('/admin/sensitive-words', { word, word_type: 'sensitive', answer: answer || null })
  return data
}

export async function deleteSensitiveWord(id: number): Promise<void> {
  await client.delete(`/admin/sensitive-words/${id}`)
}

export async function batchDeleteSensitiveWords(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post('/admin/sensitive-words/bulk-delete', { ids })
  return data
}

export async function importSensitiveWordsCsv(file: File): Promise<BatchImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await client.post('/admin/sensitive-words/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  return data
}

// ── 禁答词 ──
export async function fetchForbidWords(page = 1, pageSize = 50): Promise<Paginated<SensitiveWord>> {
  const { data } = await client.get('/admin/forbid-words', { params: { page, page_size: pageSize } })
  return data
}

export async function createForbidWord(word: string, answer?: string, scope = 'all'): Promise<SensitiveWord> {
  const { data } = await client.post('/admin/forbid-words', { word, answer: answer || null, scope })
  return data
}

export async function deleteForbidWord(id: number): Promise<void> {
  await client.delete(`/admin/forbid-words/${id}`)
}

export async function batchDeleteForbidWords(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post('/admin/forbid-words/bulk-delete', { ids })
  return data
}

export async function importForbidWordsCsv(file: File): Promise<BatchImportResult> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await client.post('/admin/forbid-words/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  return data
}
