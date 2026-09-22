import client from './client'
import type { PaginatedResponse } from './documents'

export interface PhotoItem {
  id: number
  object_name: string
  filename: string
  tags: string[]
  description: string | null
  file_size: number
  content_type: string
  user_id: number
  created_at: string
  updated_at: string
}

export interface PhotoUploadResult {
  photo_id: number
  object_name: string
  tags: string[]
  description: string | null
  tagged?: boolean
  warning?: string
}

export interface PhotoMatchItem {
  photo_id: number
  object_name: string
  filename: string
  tags: string[]
  description: string | null
  confidence: number
  reason: string
}

export interface PhotoMatchResponse {
  matches: PhotoMatchItem[]
}

export async function uploadPhoto(file: File): Promise<PhotoUploadResult> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await client.post('/admin/articles/photos/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function getPhotos(params?: {
  page?: number
  page_size?: number
  tag?: string
}): Promise<PaginatedResponse<PhotoItem>> {
  const { data } = await client.get('/admin/articles/photos', { params })
  return data
}

export async function getPhoto(id: number): Promise<PhotoItem> {
  const { data } = await client.get(`/admin/articles/photos/${id}`)
  return data
}

export async function updatePhoto(id: number, tags: string[]): Promise<PhotoItem> {
  const { data } = await client.put(`/admin/articles/photos/${id}`, { tags })
  return data
}

export async function deletePhoto(id: number): Promise<void> {
  await client.delete(`/admin/articles/photos/${id}`)
}

export async function suggestTags(id: number): Promise<{ photo_id: number; tags: string[] }> {
  const { data } = await client.post(`/admin/articles/photos/${id}/suggest-tags`)
  return data
}

export async function matchPhotos(
  topic: string,
  count: number = 5,
  excludeDays: number = 30,
): Promise<PhotoMatchResponse> {
  const { data } = await client.post('/admin/articles/photos/match', {
    topic,
    count,
    exclude_days: excludeDays,
  })
  return data
}

export interface WeightedPhotoMatchItem {
  photo_id: number
  object_name: string
  filename: string
  tags: string[]
  description: string | null
  confidence: number
  reason: string
  weights: { tag_keyword: number; semantic: number; freshness: number; anti_reuse: number }
}

export interface WeightedPhotoMatchResponse {
  matches: WeightedPhotoMatchItem[]
}

export async function matchPhotosWeighted(
  topic: string,
  templateInstruction: string = '',
  count: number = 5,
  excludeDays: number = 30,
): Promise<WeightedPhotoMatchResponse> {
  const { data } = await client.post('/admin/articles/photos/match-weighted', {
    topic,
    template_instruction: templateInstruction || undefined,
    count,
    exclude_days: excludeDays,
  })
  return data
}

export async function selectPhotos(
  batchId: number,
  photoIds: number[],
): Promise<{ ok: boolean; count: number; photo_ids: number[] }> {
  const { data } = await client.post(
    `/admin/articles/batches/${batchId}/select-photos`,
    { photo_ids: photoIds },
  )
  return data
}

export function getPhotoUrl(objectName: string): string {
  return `${import.meta.env.VITE_API_BASE_URL || '/api'}/admin/articles/photos/${encodeURIComponent(objectName)}`
}

export async function fetchPhotoBlob(objectName: string): Promise<string> {
  const url = getPhotoUrl(objectName)
  const token = localStorage.getItem('token')
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`Photo fetch failed: ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
