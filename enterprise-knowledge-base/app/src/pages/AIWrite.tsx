import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Loader2, ArrowRight, FileText, CheckCircle2, Copy } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { analyzeIntent, type AnalyzeResult } from '@/api/aiWrite'
import { getTemplates, startGeneration, createBatch, subscribeBatchProgress, getBatch, getBatchArticles, getArticle, type TemplateItem, type ArticleItem, type ArticleDetail, type GenerationEvent } from '@/api/articles'
import { PhotoMatcher } from '@/components/PhotoMatcher'
import { markdownToHtml } from '@/lib/markdown'

type Step = 'describe' | 'configure' | 'photos' | 'generating' | 'done'

export function AIWrite() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('describe')
  const [description, setDescription] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [topic, setTopic] = useState('')
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<number[]>([])
  const [wordCountMin, setWordCountMin] = useState(1200)
  const [wordCountMax, setWordCountMax] = useState(2000)
  const [photoCount, setPhotoCount] = useState(3)
  const [searchKeywords, setSearchKeywords] = useState<string[]>([])
  const [batchId, setBatchId] = useState<number | null>(null)
  const [generating, setGenerating] = useState(false)
  const [currentMessage, setCurrentMessage] = useState('')
  const [generatedArticle, setGeneratedArticle] = useState<ArticleItem | null>(null)
  const [articleContent, setArticleContent] = useState('')
  const [imagePlacement, setImagePlacement] = useState<{ object_name?: string; caption?: string }[]>([])
  const [error, setError] = useState('')

  // 订阅/轮询生命周期管理：切页或重新开始时中止，避免 SSE 连接泄漏
  const controllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [])

  const handleAnalyze = async () => {
    if (!description.trim()) { toast.error('请描述写作意图'); return }
    setAnalyzing(true)
    setError('')
    try {
      const [analysis, templateList] = await Promise.all([
        analyzeIntent(description),
        getTemplates(),
      ])
      setResult(analysis)
      setTemplates(templateList)
      setTopic(analysis.topic)
      setSelectedTemplateIds(analysis.suggested_template_ids.filter(id => templateList.find(t => t.id === id)))
      setWordCountMin(analysis.word_count_min)
      setWordCountMax(analysis.word_count_max)
      setPhotoCount(analysis.recommended_photo_count)
      setSearchKeywords(analysis.photo_search_keywords)
      setStep('configure')
    } catch (e) {
      toast.error('AI 分析失败，请重试')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleConfirmConfig = async () => {
    if (!topic.trim()) { toast.error('请输入文章主题'); return }
    try {
      const batch = await createBatch(topic, 1, [])
      setBatchId(batch.id)
      setStep('photos')
    } catch {
      toast.error('创建批次失败')
    }
  }

  const handlePhotosConfirmed = async (_photoIds: number[]) => {
    if (!batchId) return

    // 中止上一次订阅/轮询，防止旧连接泄漏
    controllerRef.current?.abort()
    controllerRef.current = null

    setStep('generating')
    setGenerating(true)
    setCurrentMessage('正在分析主题...')
    setError('')

    let articleReceived = false
    let pollingTimer: ReturnType<typeof setTimeout> | null = null

    const stop = () => {
      controllerRef.current?.abort()
      controllerRef.current = null
      if (pollingTimer !== null) {
        clearTimeout(pollingTimer)
        pollingTimer = null
      }
    }

    controllerRef.current = subscribeBatchProgress(
      batchId,
      async (event: GenerationEvent) => {
        switch (event.type) {
          case 'progress':
            if (mountedRef.current) setCurrentMessage(event.message)
            break
          case 'article_generated':
            if (!mountedRef.current) return
            if (event.data && Array.isArray(event.data)) {
              const articles = event.data as ArticleDetail[]
              if (articles.length > 0) {
                const latest = articles[articles.length - 1]
                setGeneratedArticle(latest)
                if (latest.content) {
                  setArticleContent(latest.content)
                }
                if (latest.image_placement && latest.image_placement.length > 0) {
                  setImagePlacement(latest.image_placement)
                }
                articleReceived = true
              }
            }
            break
          case 'completed':
            if (!mountedRef.current) return
            setGenerating(false)
            setStep('done')
            stop()
            if (!articleReceived && batchId) {
              try {
                const articlesRes = await getBatchArticles(batchId, { page: 1, page_size: 1 })
                if (articlesRes.items && articlesRes.items.length > 0) {
                  const detail = await getArticle(articlesRes.items[0].id) as unknown as ArticleDetail
                  setGeneratedArticle(detail)
                  setArticleContent(detail.content || '')
                  if (detail.image_placement && detail.image_placement.length > 0) {
                    setImagePlacement(detail.image_placement)
                  }
                }
              } catch {}
            }
            break
          case 'error':
            if (!mountedRef.current) return
            setError(event.message)
            setGenerating(false)
            stop()
            break
        }
      },
      () => {
        // 断流后 subscribeBatchProgress 会自动重连；轮询继续作为兜底同步进度
        if (mountedRef.current) {
          setCurrentMessage('进度连接异常，正在自动重连并同步进度...')
        }
      },
    )

    try {
      await startGeneration(batchId, selectedTemplateIds, true, wordCountMin, wordCountMax)
    } catch {
      if (mountedRef.current) {
        setError('启动生成失败')
        setGenerating(false)
      }
      stop()
      return
    }

    let attempts = 0
    const maxAttempts = 600 // 兜底轮询上限：600×2s = 20 分钟，覆盖超长生成

    const checkStatus = async () => {
      if (!mountedRef.current) return
      if (attempts >= maxAttempts) {
        if (mountedRef.current) {
          setError('生成超时，请刷新页面重试')
          setGenerating(false)
        }
        stop()
        return
      }
      attempts++

      try {
        const batch = await getBatch(batchId)
        if (batch.status === 'completed') {
          if (!mountedRef.current) return
          setGenerating(false)
          if (!articleReceived) {
            try {
              const articlesRes = await getBatchArticles(batchId, { page: 1, page_size: 1 })
              if (articlesRes.items && articlesRes.items.length > 0) {
                const detail = await getArticle(articlesRes.items[0].id) as unknown as ArticleDetail
                setGeneratedArticle(detail)
                setArticleContent(detail.content || '')
                if (detail.image_placement && detail.image_placement.length > 0) {
                  setImagePlacement(detail.image_placement)
                }
              }
            } catch {}
          }
          setStep('done')
          stop()
          return
        }
        if (batch.status === 'failed') {
          if (!mountedRef.current) return
          setError(batch.error_message || '生成失败')
          setGenerating(false)
          stop()
          return
        }
        pollingTimer = setTimeout(checkStatus, 2000)
      } catch {
        pollingTimer = setTimeout(checkStatus, 2000)
      }
    }

    pollingTimer = setTimeout(checkStatus, 2000)
  }

  const handleCopyContent = () => {
    if (articleContent) {
      navigator.clipboard.writeText(articleContent)
      toast.success('已复制到剪贴板')
    }
  }

  const templateTypes = { structure: '结构', style: '风格' }

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-8">
      <div className="flex items-center gap-3">
        <Sparkles className="w-6 h-6 text-primary" />
        <h1 className="text-2xl font-bold">AI 写作</h1>
      </div>

      {/* Step 1: Describe */}
      {step === 'describe' && (
        <Card>
          <CardHeader>
            <CardTitle>描述写作意图</CardTitle>
            <CardDescription>用自然语言描述你想要写的文章，AI 会分析并推荐最佳配置</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="例如：我想写一篇关于地下室电渗透防潮技术的科普文章，面向普通业主，用通俗易懂的语言解释原理和优势..."
              className="min-h-[120px]"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
            <Button onClick={handleAnalyze} disabled={analyzing || !description.trim()} className="w-full">
              {analyzing ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Sparkles className="w-4 h-4 mr-2" />}
              {analyzing ? 'AI 正在分析...' : 'AI 分析'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Configure */}
      {step === 'configure' && result && (
        <Card>
          <CardHeader>
            <CardTitle>AI 推荐配置</CardTitle>
            <CardDescription>AI 根据你的意图推荐了以下配置，你可以调整后确认</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <Label>文章主题</Label>
              <Input value={topic} onChange={e => setTopic(e.target.value)} />
            </div>

            <div className="space-y-2">
              <Label>写作模板</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {templates.map(t => {
                  const selected = selectedTemplateIds.includes(t.id)
                  return (
                    <div
                      key={t.id}
                      onClick={() => {
                        setSelectedTemplateIds(prev =>
                          prev.includes(t.id) ? prev.filter(id => id !== t.id) : [...prev, t.id]
                        )
                      }}
                      className={`border-2 rounded-lg p-3 cursor-pointer transition-all ${
                        selected ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{t.name}</span>
                        <Badge variant="outline" className="text-[10px]">
                          {templateTypes[t.type as keyof typeof templateTypes] || t.type}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{t.prompt_instruction}</p>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="space-y-2">
              <Label>字数范围：{wordCountMin} - {wordCountMax} 字</Label>
              <Slider
                value={[wordCountMin, wordCountMax]}
                min={500}
                max={5000}
                step={100}
                onValueChange={([min, max]) => { setWordCountMin(min); setWordCountMax(max) }}
              />
            </div>

            <div className="space-y-2">
              <Label>配图数量：{photoCount} 张</Label>
              <Slider
                value={[photoCount]}
                min={1}
                max={20}
                step={1}
                onValueChange={([v]) => setPhotoCount(v)}
              />
            </div>

            {searchKeywords.length > 0 && (
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">照片匹配关键词</Label>
                <div className="flex flex-wrap gap-1">
                  {searchKeywords.map((kw, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">{kw}</Badge>
                  ))}
                </div>
              </div>
            )}

            <Button onClick={handleConfirmConfig} className="w-full">
              <ArrowRight className="w-4 h-4 mr-2" />
              确认并匹配照片
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Photos */}
      {step === 'photos' && (
        <Card>
          <CardHeader>
            <CardTitle>选择配图</CardTitle>
            <CardDescription>智能匹配 {photoCount} 张照片，不满意的可以换或手动选择</CardDescription>
          </CardHeader>
          <CardContent>
            <PhotoMatcher
              topic={searchKeywords.join(' ') || topic}
              count={photoCount}
              batchId={batchId}
              onConfirm={handlePhotosConfirmed}
            />
          </CardContent>
        </Card>
      )}

      {/* Step 4: Generating */}
      {step === 'generating' && (
        <Card>
          <CardHeader>
            <CardTitle>{error ? '生成失败' : generating ? '正在生成文章...' : '生成完成'}</CardTitle>
            <CardDescription>{error || currentMessage}</CardDescription>
          </CardHeader>
          <CardContent>
            {error && (
              <div className="text-center py-4">
                <p className="text-destructive mb-4">{error}</p>
                <Button variant="outline" onClick={() => { setError(''); setStep('configure') }}>
                  返回调整
                </Button>
              </div>
            )}
            {generating && !error && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 5: Done */}
      {step === 'done' && generatedArticle && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-500" />
              <CardTitle>文章生成完成</CardTitle>
            </div>
            <CardDescription>{topic}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {articleContent ? (
              <div className="relative">
                <div
                  className="prose prose-sm max-w-none bg-muted/50 rounded-lg p-6"
                  dangerouslySetInnerHTML={{ __html: markdownToHtml(articleContent, imagePlacement) }}
                />
                <div className="flex gap-2 mt-4 justify-end">
                  <Button variant="outline" size="sm" onClick={handleCopyContent}>
                    <Copy className="w-3.5 h-3.5 mr-1" />
                    复制内容
                  </Button>
                  <Button size="sm" onClick={() => navigate(`/articles/${generatedArticle.id}`)}>
                    <FileText className="w-3.5 h-3.5 mr-1" />
                    查看文章详情
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center py-4 text-muted-foreground">
                <FileText className="w-4 h-4 mr-2" />
                文章已生成，查看详情查看完整内容
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => { controllerRef.current?.abort(); controllerRef.current = null; setStep('describe'); setBatchId(null); setGeneratedArticle(null); setArticleContent(''); setError('') }}>
                重新写作
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
