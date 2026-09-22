import { useCallback, useEffect, useRef, useState } from 'react'
import { Plus, Send, ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  chatStreamCustomer, chatStreamInternal, fetchThreadMessages, listThreads,
  submitFeedback, submitUnanswered,
  type Citation, type ImageInfo,
} from '@/api/agent'
import { MessageContent } from './MessageContent'

export type AgentType = 'internal' | 'customer'

interface Message {
  id: string
  role: 'user' | 'ai'
  content: string
  confidence?: number
  needsHuman?: boolean
  faqHit?: boolean
  isStreaming?: boolean
  citations?: Citation[]
  images?: ImageInfo[]
  timestamp: number
}

interface ThreadRef {
  id: string
  title: string
}

const CUSTOMER_THREADS_KEY = 'kb_customer_threads'

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function readCustomerThreads(): ThreadRef[] {
  try {
    return JSON.parse(localStorage.getItem(CUSTOMER_THREADS_KEY) || '[]')
  } catch {
    return []
  }
}

function confidenceVariant(v?: number): 'default' | 'secondary' | 'destructive' {
  if (v === undefined) return 'secondary'
  if (v >= 0.8) return 'default'
  if (v >= 0.5) return 'secondary'
  return 'destructive'
}

export function ChatPanel({ mode, title, subtitle }: { mode: AgentType; title: string; subtitle: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [threadId, setThreadId] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [threads, setThreads] = useState<ThreadRef[]>([])
  const [rated, setRated] = useState<Record<string, 'like' | 'dislike'>>({})
  const [input, setInput] = useState('')

  const messagesMapRef = useRef<Record<string, Message[]>>({})
  const threadIdRef = useRef('')
  const lastQuestionRef = useRef('')
  const bodyRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    threadIdRef.current = threadId
  }, [threadId])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // 加载线程历史
  useEffect(() => {
    let cancelled = false
    async function load() {
      if (mode === 'internal') {
        try {
          const rows = await listThreads()
          if (!cancelled) setThreads(rows.map(r => ({ id: r.thread_id, title: r.title })))
        } catch {
          /* best-effort */
        }
      } else {
        if (!cancelled) setThreads(readCustomerThreads())
      }
    }
    load()
    return () => { cancelled = true }
  }, [mode])

  const saveCurrentThread = useCallback(() => {
    const id = threadIdRef.current
    if (id && messages.length > 0) {
      messagesMapRef.current[id] = [...messages]
    }
  }, [messages])

  const newThread = useCallback(() => {
    saveCurrentThread()
    setMessages([])
    setThreadId('')
    threadIdRef.current = ''
  }, [saveCurrentThread])

  const switchThread = useCallback(async (id: string) => {
    if (id === threadIdRef.current) return
    saveCurrentThread()
    setThreadId(id)
    threadIdRef.current = id

    const cached = messagesMapRef.current[id]
    if (cached && cached.length > 0) {
      setMessages([...cached])
      return
    }

    setMessages([])
    messagesMapRef.current[id] = []
    try {
      const rows = await fetchThreadMessages(id, mode)
      const hydrated: Message[] = []
      for (const m of rows) {
        hydrated.push({ id: genId(), role: 'user', content: m.question, timestamp: new Date(m.created_at).getTime() })
        if (m.answer) {
          hydrated.push({
            id: genId(), role: 'ai', content: m.answer,
            confidence: m.confidence ?? undefined,
            faqHit: m.faq_hit,
            citations: (m.citations ?? undefined) as Citation[] | undefined,
            images: (m.images ?? undefined) as ImageInfo[] | undefined,
            timestamp: new Date(m.created_at).getTime() + 1,
          })
        }
      }
      messagesMapRef.current[id] = hydrated
      if (threadIdRef.current === id) setMessages([...hydrated])
    } catch {
      messagesMapRef.current[id] = []
    }
  }, [mode, saveCurrentThread])

  const updateMessage = useCallback((id: string, patch: Partial<Message>) => {
    setMessages(prev => prev.map(m => (m.id === id ? { ...m, ...patch } : m)))
  }, [])

  const sendMessage = useCallback(async (raw: string) => {
    const content = raw.trim()
    if (!content || isStreaming) return

    const isNew = !threadIdRef.current
    if (isNew) {
      saveCurrentThread()
      const newId = genId()
      threadIdRef.current = newId
      setThreadId(newId)
    }
    const activeThreadId = threadIdRef.current

    setInput('')
    lastQuestionRef.current = content
    const aiId = genId()
    setMessages(prev => [
      ...prev,
      { id: genId(), role: 'user', content, timestamp: Date.now() },
      { id: aiId, role: 'ai', content: '', isStreaming: true, timestamp: Date.now() },
    ])
    setIsStreaming(true)

    const streamFn = mode === 'customer' ? chatStreamCustomer : chatStreamInternal
    let answerText = ''

    try {
      for await (const event of streamFn(content, activeThreadId)) {
        if (event.type === 'token') {
          answerText += event.content
          updateMessage(aiId, { content: answerText })
        } else if (event.type === 'done') {
          answerText = event.answer || answerText
          updateMessage(aiId, {
            content: answerText,
            confidence: event.confidence,
            needsHuman: event.needs_human,
            faqHit: event.faq_hit,
            citations: event.citations || [],
            images: event.images || [],
            isStreaming: false,
          })
          if (isNew) {
            const title = content.slice(0, 20)
            setThreads(prev => [{ id: activeThreadId, title }, ...prev.filter(t => t.id !== activeThreadId)])
            if (mode === 'customer') {
              const list = readCustomerThreads()
              if (!list.some(t => t.id === activeThreadId)) {
                list.unshift({ id: activeThreadId, title })
                try { localStorage.setItem(CUSTOMER_THREADS_KEY, JSON.stringify(list.slice(0, 50))) } catch { /* quota */ }
              }
            }
          }
          if (event.confidence !== undefined && event.confidence < 0.5 && lastQuestionRef.current) {
            submitUnanswered(activeThreadId, lastQuestionRef.current, mode, mode !== 'customer').catch(() => {})
          }
        } else if (event.type === 'error') {
          updateMessage(aiId, { content: event.message || '抱歉，系统暂时出现问题，请稍后重试。', isStreaming: false })
        }
      }
    } catch (e) {
      if ((e as Error)?.message === 'Unauthorized') return
      updateMessage(aiId, { content: '抱歉，系统暂时出现问题，请稍后重试。', isStreaming: false })
    }

    setIsStreaming(false)
  }, [isStreaming, mode, saveCurrentThread, updateMessage])

  const rateMessage = useCallback(async (msgId: string, rating: 'like' | 'dislike') => {
    if (rated[msgId]) return
    setRated(prev => ({ ...prev, [msgId]: rating }))
    try {
      await submitFeedback(threadIdRef.current, rating, undefined, mode !== 'customer')
    } catch {
      /* best-effort */
    }
  }, [rated, mode])

  return (
    <div className="flex h-full">
      {mode === 'internal' && (
        <aside className="w-64 shrink-0 border-r bg-card flex flex-col">
          <div className="p-3 border-b">
            <Button className="w-full" onClick={newThread}>
              <Plus className="mr-2 h-4 w-4" />新对话
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {threads.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">暂无对话记录</p>
            )}
            {threads.map(t => (
              <button
                key={t.id}
                onClick={() => switchThread(t.id)}
                className={cn(
                  'w-full text-left px-3 py-2 rounded-md text-sm truncate transition-colors',
                  t.id === threadId ? 'bg-primary/10 text-primary' : 'hover:bg-muted text-muted-foreground',
                )}
              >
                {t.title || '未命名对话'}
              </button>
            ))}
          </div>
        </aside>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 shrink-0 border-b bg-card flex items-center justify-between px-5">
          <div className="flex items-baseline gap-3">
            <span className="font-semibold">{title}</span>
            <span className="text-sm text-muted-foreground">{subtitle}</span>
          </div>
          {mode === 'customer' && (
            <Button variant="outline" size="sm" onClick={newThread}>
              <Plus className="mr-1 h-4 w-4" />新对话
            </Button>
          )}
        </header>

        <div ref={bodyRef} className="flex-1 overflow-y-auto bg-muted/30 px-6 py-5">
          {messages.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              {mode === 'internal' ? '开始提问，获取知识库智能回答' : '您好，有什么可以帮助您的？'}
            </div>
          )}
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div
                  className={cn(
                    'max-w-[80%] rounded-xl px-4 py-3 text-sm',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground rounded-br-sm'
                      : 'bg-card border rounded-bl-sm',
                  )}
                >
                  <MessageContent
                    content={msg.content}
                    citations={msg.citations}
                    images={msg.images}
                    isStreaming={msg.isStreaming}
                  />
                  {msg.role === 'ai' && !msg.isStreaming && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {msg.confidence !== undefined && (
                        <Badge variant={confidenceVariant(msg.confidence)} className="text-xs">
                          置信度: {(msg.confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                      {msg.faqHit && <Badge variant="outline" className="text-xs text-green-600">FAQ命中</Badge>}
                      {msg.needsHuman && <Badge variant="outline" className="text-xs text-amber-600">建议转人工</Badge>}
                      <span className="ml-auto flex items-center gap-1">
                        <Button
                          variant="ghost" size="sm" className={cn('h-7 px-2 text-xs', rated[msg.id] === 'like' && 'text-primary')}
                          onClick={() => rateMessage(msg.id, 'like')}
                        >
                          <ThumbsUp className="mr-1 h-3 w-3" />有帮助
                        </Button>
                        <Button
                          variant="ghost" size="sm" className={cn('h-7 px-2 text-xs', rated[msg.id] === 'dislike' && 'text-destructive')}
                          onClick={() => rateMessage(msg.id, 'dislike')}
                        >
                          <ThumbsDown className="mr-1 h-3 w-3" />没帮助
                        </Button>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isStreaming && messages[messages.length - 1]?.content === '' && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground pl-1">
                <Loader2 className="h-3 w-3 animate-spin" />AI 正在思考...
              </div>
            )}
          </div>
        </div>

        <footer className="shrink-0 border-t bg-card px-6 py-3">
          <div className="max-w-3xl mx-auto flex items-end gap-2">
            <Textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendMessage(input)
                }
              }}
              placeholder="请输入您的问题..."
              className="min-h-[44px] max-h-40 resize-none"
              rows={1}
            />
            <Button onClick={() => sendMessage(input)} disabled={isStreaming || !input.trim()}>
              <Send className="mr-1 h-4 w-4" />发送
            </Button>
          </div>
        </footer>
      </div>
    </div>
  )
}
