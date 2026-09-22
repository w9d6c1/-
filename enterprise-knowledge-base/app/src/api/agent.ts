const BASE = '/api/agent'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

function publicHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
}

function handleAuthError() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  window.location.hash = '#/login'
}

export interface ImageInfo {
  id: number
  doc_index: number
  seq: number
  url: string
  object_name?: string
  width?: number | null
  height?: number | null
}

export interface Citation {
  index: number
  title: string
  platform: string
  url: string
  source_name: string
  is_internal: boolean
  images?: { id: number; url: string; width?: number | null; height?: number | null }[]
}

export interface StreamToken {
  type: 'token'
  content: string
}

export interface StreamDone {
  type: 'done'
  answer: string
  confidence: number
  needs_human: boolean
  faq_hit: boolean
  citations?: Citation[]
  images?: ImageInfo[]
}

export interface StreamError {
  type: 'error'
  message: string
}

export type StreamEvent = StreamToken | StreamDone | StreamError

async function* chatStream(
  url: string,
  headers: Record<string, string>,
  msg: string,
  threadId?: string,
): AsyncGenerator<StreamEvent> {
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message: msg, thread_id: threadId }),
  })

  if (resp.status === 401) {
    handleAuthError()
    throw new Error('Unauthorized')
  }

  const reader = resp.body?.getReader()
  if (!reader) return

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
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          yield JSON.parse(data) as StreamEvent
        } catch {
          // skip malformed SSE lines
        }
      }
    }
  }
}

export function chatStreamInternal(msg: string, threadId?: string): AsyncGenerator<StreamEvent> {
  return chatStream(`${BASE}/internal/chat/stream`, authHeaders(), msg, threadId)
}

export function chatStreamCustomer(msg: string, threadId?: string): AsyncGenerator<StreamEvent> {
  return chatStream(`${BASE}/customer/chat/stream`, publicHeaders(), msg, threadId)
}

export interface ThreadSummary {
  thread_id: string
  title: string
  turns: number
  last_active: string
}

export interface ThreadMessage {
  question: string
  answer: string
  confidence?: number | null
  faq_hit: boolean
  citations?: Citation[] | null
  images?: ImageInfo[] | null
  created_at: string
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const resp = await fetch(`${BASE}/threads?limit=50`, { headers: authHeaders() })
  if (resp.status === 401) {
    handleAuthError()
    throw new Error('Unauthorized')
  }
  return resp.json()
}

export async function fetchThreadMessages(threadId: string, source: string): Promise<ThreadMessage[]> {
  const headers = source === 'internal' ? authHeaders() : publicHeaders()
  const resp = await fetch(
    `${BASE}/threads/${encodeURIComponent(threadId)}/messages?source=${source}`,
    { headers },
  )
  if (!resp.ok) return []
  return resp.json()
}

export async function submitFeedback(
  threadId: string,
  rating: 'like' | 'dislike',
  suggestion?: string,
  useAuth = true,
): Promise<void> {
  await fetch('/api/admin/feedbacks', {
    method: 'POST',
    headers: useAuth ? authHeaders() : publicHeaders(),
    body: JSON.stringify({ thread_id: threadId, rating, suggestion: suggestion || null }),
  })
}

export async function submitUnanswered(
  threadId: string,
  question: string,
  source: string,
  useAuth = true,
): Promise<void> {
  await fetch('/api/admin/unanswered', {
    method: 'POST',
    headers: useAuth ? authHeaders() : publicHeaders(),
    body: JSON.stringify({ thread_id: threadId, question, source }),
  })
}
