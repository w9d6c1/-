import client from './client'
import type { PaginatedResponse } from './documents'

export interface ArticleItem {
  id: number
  batch_id: number
  title: string
  word_count: number
  angle: string
  account_type: string | null
  status: string
  review_status: string
  created_at: string
  updated_at: string
}

export interface ImagePlacement {
  object_name?: string
  caption?: string
}

export interface ArticleDetail extends ArticleItem {
  content: string
  image_placement: ImagePlacement[]
  user_id: number
}

export interface BatchItem {
  id: number
  topic: string
  account_type: string | null
  photo_count: number
  article_count: number
  generated_count: number
  status: string
  user_id: number
  created_at: string
  updated_at: string
}

export interface BatchDetail extends BatchItem {
  photo_object_names: string[] | null
  photo_descriptions: string | null
  error_message: string | null
}

export interface PlatformInfo {
  platform: string
  name: string
  method: string
  available: boolean
}

export interface PlatformAccountItem {
  id: number
  platform_id: string
  account_name: string
  account_group: string | null
  credentials_type: string
  status: string
  last_verified_at: string | null
  error_message: string | null
  user_id: number
  created_at: string
  updated_at: string
}

export interface PlatformAccountDetail extends PlatformAccountItem {
  credentials: string
}

export interface AccountVerifyResult {
  success: boolean
  message: string
  account_id: number
}

export interface PublishingStats {
  total_published: number
  total_failed: number
  total_pending: number
  today_published: number
  today_failed: number
  by_platform: { platform: string; count: number }[]
  recent_records: PublishingRecord[]
}

export interface PublishingRecord {
  id: number
  article_id: number
  platform: string
  platform_name: string | null
  account_id: number | null
  status: string
  published_url: string | null
  remote_article_id: string | null
  error_message: string | null
  retry_count: number
  published_at: string | null
  scheduled_at: string | null
  created_at: string
}

export interface GenAngle {
  key: string
  label: string
}

export const DEFAULT_ANGLES: GenAngle[] = [
  { key: 'technical_detail', label: '技术原理解析' },
  { key: 'case_study', label: '案例实践分享' },
  { key: 'benefit_analysis', label: '优势效益分析' },
  { key: 'comparison', label: '方案对比分析' },
  { key: 'maintenance_guide', label: '选购施工指南' },
]

// ========== 目标账号类型（文章视角人群） ==========

export interface AccountTypeInfo {
  key: string
  label: string
  description: string
  icon: 'user' | 'designer' | 'dealer'
}

export const ACCOUNT_TYPES: AccountTypeInfo[] = [
  {
    key: 'user',
    label: '用户',
    description: '面向业主/普通用户，选购指南、常见问题、案例分享',
    icon: 'user',
  },
  {
    key: 'designer',
    label: '设计师',
    description: '面向建筑/设计专业人士，技术原理、方案对比、规范解读',
    icon: 'designer',
  },
  {
    key: 'dealer',
    label: '经销商',
    description: '面向经销商/渠道经营者，招商政策、市场机遇、利润分析',
    icon: 'dealer',
  },
]

export function getAccountTypeLabel(key: string | null): string {
  return ACCOUNT_TYPES.find(a => a.key === key)?.label ?? '通用'
}

// ========== Batches ==========

export async function createBatch(topic: string, article_count: number, angle_keys?: string[], account_type?: string): Promise<BatchItem> {
  const { data } = await client.post('/admin/articles/batches', { topic, article_count, angle_keys, account_type })
  return data
}

export async function getBatches(params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<BatchItem>> {
  const { data } = await client.get('/admin/articles/batches', { params })
  return data
}

export async function getBatch(id: number): Promise<BatchDetail> {
  const { data } = await client.get(`/admin/articles/batches/${id}`)
  return data
}

export async function deleteBatch(id: number): Promise<void> {
  await client.delete(`/admin/articles/batches/${id}`)
}

export async function uploadBatchPhotos(id: number, files: File[]): Promise<{ ok: boolean; photo_count: number; object_names: string[] }> {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  const { data } = await client.post(`/admin/articles/batches/${id}/upload-photos`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function startGeneration(id: number, template_ids?: number[], usePhotoLibrary?: boolean, minWords?: number, maxWords?: number): Promise<{ ok: boolean; batch_id: number; status: string }> {
  let url = `/admin/articles/batches/${id}/generate`
  const params: string[] = []
  if (template_ids && template_ids.length > 0) {
    params.push(...template_ids.map(tid => `template_ids=${tid}`))
  }
  if (usePhotoLibrary) {
    params.push(`use_photo_library=true`)
  }
  if (minWords !== undefined) {
    params.push(`min_words=${minWords}`)
  }
  if (maxWords !== undefined) {
    params.push(`max_words=${maxWords}`)
  }
  if (params.length > 0) {
    url += '?' + params.join('&')
  }
  const { data } = await client.post(url)
  return data
}

export async function getBatchArticles(id: number, params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedResponse<ArticleItem>> {
  const { data } = await client.get(`/admin/articles/batches/${id}/articles`, { params })
  return data
}

export async function exportBatch(id: number): Promise<Blob> {
  const { data } = await client.get(`/admin/articles/batches/${id}/export`, { responseType: 'blob' })
  return data
}

export async function publishBatch(id: number, platform_ids: string[], article_ids?: number[], account_id?: number, scheduled_at?: string): Promise<{ ok: boolean; record_count: number; records: PublishingRecord[] }> {
  const { data } = await client.post(`/admin/articles/batches/${id}/publish`, {
    platform_ids,
    article_ids,
    account_id: account_id || null,
    scheduled_at: scheduled_at || null,
  })
  return data
}

// ========== Articles ==========

export async function getArticle(id: number): Promise<ArticleDetail> {
  const { data } = await client.get(`/admin/articles/articles/${id}`)
  return data
}

export async function updateArticle(id: number, body: { title?: string; content?: string }): Promise<ArticleDetail> {
  const { data } = await client.put(`/admin/articles/articles/${id}`, body)
  return data
}

export async function deleteArticle(id: number): Promise<void> {
  await client.delete(`/admin/articles/articles/${id}`)
}

export async function bulkDeleteBatches(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const { data } = await client.post(`/admin/articles/batches/bulk-delete`, { ids })
  return data
}

export async function regenerateArticle(id: number): Promise<ArticleDetail> {
  const { data } = await client.post(`/admin/articles/articles/${id}/regenerate`)
  return data
}

export async function publishArticle(id: number, platform_ids: string[], account_id?: number, scheduled_at?: string): Promise<{ ok: boolean; records: PublishingRecord[] }> {
  const { data } = await client.post(`/admin/articles/articles/${id}/publish`, {
    platform_ids,
    account_id: account_id || null,
    scheduled_at: scheduled_at || null,
  })
  return data
}

export async function getPublishingStatus(id: number): Promise<PublishingRecord[]> {
  const { data } = await client.get(`/admin/articles/articles/${id}/publishing-status`)
  return data
}

export async function getBatchPublishingStatus(id: number): Promise<PublishingRecord[]> {
  const { data } = await client.get(`/admin/articles/batches/${id}/publishing-status`)
  return data
}

export async function exportArticle(id: number, format: 'md' | 'html' | 'docx'): Promise<Blob> {
  const { data } = await client.get(`/admin/articles/articles/${id}/export`, {
    params: { format },
    responseType: 'blob',
  })
  return data
}

// ========== Platforms ==========

export async function getPlatforms(): Promise<PlatformInfo[]> {
  const { data } = await client.get('/admin/articles/platforms')
  return data
}

export interface BridgeStatus {
  ok: boolean
  service?: string
  mode?: string
  extension_connected?: Record<string, boolean>
  queue_lengths?: Record<string, number>
  running?: Record<string, boolean>
  error?: string
}

export async function getBridgeStatus(): Promise<BridgeStatus> {
  const { data } = await client.get('/admin/articles/bridge/status')
  return data
}

// ========== Platform Accounts ==========

export async function getAccounts(platform_id?: string): Promise<PlatformAccountItem[]> {
  const { data } = await client.get('/admin/articles/accounts', { params: platform_id ? { platform_id } : {} })
  return data
}

export async function getAccount(id: number): Promise<PlatformAccountDetail> {
  const { data } = await client.get(`/admin/articles/accounts/${id}`)
  return data
}

export async function createAccount(params: {
  platform_id: string
  account_name: string
  account_group: string
  ws_token: string
  credentials?: string
  credentials_type?: string
}): Promise<PlatformAccountItem> {
  const { data } = await client.post('/admin/articles/accounts', params)
  return data
}

export async function updateAccount(id: number, params: {
  account_name?: string
  account_group?: string
  ws_token?: string
  credentials?: string
  credentials_type?: string
}): Promise<PlatformAccountItem> {
  const { data } = await client.put(`/admin/articles/accounts/${id}`, params)
  return data
}

export async function deleteAccount(id: number): Promise<void> {
  await client.delete(`/admin/articles/accounts/${id}`)
}

export async function verifyAccount(id: number): Promise<AccountVerifyResult> {
  const { data } = await client.post(`/admin/articles/accounts/${id}/verify`)
  return data
}

export async function getPublishingStats(): Promise<PublishingStats> {
  const { data } = await client.get('/admin/articles/publishing-stats')
  return data
}

// ========== URL Fetch ==========

export async function fetchUrlContent(url: string): Promise<{ content: string }> {
  const { data } = await client.post('/admin/articles/fetch-url', { url })
  return data
}

// ========== Imitate ==========

export interface StyleAnalysis {
  tone: string
  opening_style: string
  structure: string
  argument_pattern: string
  closing_style: string
  style_description: string
}

export interface ImitateResult {
  batch_id: number
  article: ArticleDetail
}

export async function imitateArticle(params: {
  topic: string
  source_text?: string
  source_url?: string
  photo_ids?: number[]
  batch_id?: number
  style_analysis?: StyleAnalysis
  word_count_min?: number
  word_count_max?: number
}): Promise<ImitateResult> {
  const { data } = await client.post('/admin/articles/imitate', params)
  return data
}

export async function analyzeStyle(source_text: string): Promise<StyleAnalysis> {
  const { data } = await client.post('/admin/articles/analyze-style', { source_text })
  return data
}

// ========== Templates ==========

export interface TemplateItem {
  id: number
  user_id: number
  name: string
  type: string
  account_type: string | null
  prompt_instruction: string
  is_preset: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export async function getTemplates(): Promise<TemplateItem[]> {
  const { data } = await client.get('/admin/articles/templates')
  return data
}

export async function getTemplatesByAccountType(accountType: string): Promise<TemplateItem[]> {
  const { data } = await client.get('/admin/articles/templates', { params: { account_type: accountType } })
  return data
}

export async function createTemplate(params: {
  name: string
  type: string
  prompt_instruction: string
}): Promise<TemplateItem> {
  const { data } = await client.post('/admin/articles/templates', params)
  return data
}

export async function updateTemplate(id: number, params: {
  name?: string
  prompt_instruction?: string
}): Promise<TemplateItem> {
  const { data } = await client.put(`/admin/articles/templates/${id}`, params)
  return data
}

export async function deleteTemplate(id: number): Promise<void> {
  await client.delete(`/admin/articles/templates/${id}`)
}

// ========== Hot Topics — 今日热点与智能选题 ==========

export interface HotTopicItem {
  rank: number
  title: string
  hot_value: number
  url: string
}

export interface HotTopicSource {
  label: string
  ok: boolean
  items: HotTopicItem[]
  cached_at: number | null
  stale?: boolean
}

export interface HotTopicsResponse {
  sources: Record<string, HotTopicSource>
  updated_at: number
}

export interface HotTitleRecommendation {
  hot_title: string
  source: string
  reason: string
  suggested_topic: string
  titles: string[]
}

export interface HotRecommendResponse {
  recommendations: HotTitleRecommendation[]
  hot_count: number
  message: string
}

export async function getHotTopics(refresh = false): Promise<HotTopicsResponse> {
  const { data } = await client.get('/admin/articles/hot-topics', { params: { refresh } })
  return data
}

export async function recommendHotTitles(max_topics = 8): Promise<HotRecommendResponse> {
  const { data } = await client.post('/admin/articles/hot-topics/recommend', null, {
    params: { max_topics },
    timeout: 120000,
  })
  return data
}

// ========== Topic Generate — 智能选题（热点 + 知识库 + 公司方向） ==========

export interface TopicRecommendItem {
  hot_title: string
  source: string
  reason: string
  suggested_topic: string
  titles: string[]
}

export interface TopicGenerateResponse {
  recommendations: TopicRecommendItem[]
  hot_count: number
  message: string
}

export async function generateTopics(companyDirection: string, maxTopics = 8): Promise<TopicGenerateResponse> {
  const { data } = await client.post('/admin/articles/topics/generate', {
    company_direction: companyDirection,
    max_topics: maxTopics,
  }, { timeout: 120000 })
  return data
}

// ========== Photo Proxy ==========

export function getPhotoUrl(objectName: string): string {
  return `${import.meta.env.VITE_API_BASE_URL || '/api'}/admin/articles/photos/${encodeURIComponent(objectName)}`
}

// ========== SSE Stream ==========

export interface GenerationEvent {
  type: 'progress' | 'article_generated' | 'error' | 'completed'
  batch_id: number
  message: string
  data?: unknown
}

export function subscribeBatchProgress(
  batchId: number,
  onEvent: (event: GenerationEvent) => void,
  onError?: (error: Event) => void,
): AbortController {
  const controller = new AbortController()
  const token = localStorage.getItem('token')
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
  const MAX_RETRIES = 8

  let finished = false
  let attempt = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const clearReconnectTimer = () => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const scheduleReconnect = (err: Error) => {
    if (finished || controller.signal.aborted) return
    if (attempt < MAX_RETRIES) {
      attempt += 1
      const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000)
      timer = setTimeout(() => { void connect() }, delay)
    } else if (onError) {
      onError(err as unknown as Event)
    }
  }

  const connect = async () => {
    if (finished || controller.signal.aborted) return

    try {
      const res = await fetch(`${baseUrl}/admin/articles/batches/${batchId}/stream`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`Stream error: ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) throw new Error('Stream body not readable')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: GenerationEvent = JSON.parse(line.slice(6))
              onEvent(event)
              // 成功收到事件说明连接可用：重置重连计数，后续偶发断流可持续重连
              attempt = 0
              if (event.type === 'completed' || event.type === 'error') {
                finished = true
                clearReconnectTimer()
                return
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }

      // 流在到达终态前结束（代理空闲超时/网络波动等）→ 自动重连
      if (!finished) scheduleReconnect(new Error('SSE 连接中断，正在重连'))
    } catch (err) {
      const e = err as Error
      if (e.name === 'AbortError') return
      if (!finished) scheduleReconnect(e)
    }
  }

  void connect()

  controller.signal.addEventListener('abort', () => {
    finished = true
    clearReconnectTimer()
  })

  return controller
}
