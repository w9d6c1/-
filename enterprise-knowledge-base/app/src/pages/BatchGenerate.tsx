import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Sparkles, Upload, X, Loader2, CheckCircle2,
  FileText, ChevronRight, AlertCircle,
  Copy, Globe, Search, PenLine, Library, Wand2, Users, Ruler, Handshake,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import {
  createBatch, startGeneration, subscribeBatchProgress,
  imitateArticle, analyzeStyle, fetchUrlContent,
  generateTopics, getTemplatesByAccountType, getAccountTypeLabel,
  getBatch, getBatchArticles,
  ACCOUNT_TYPES,
  type GenerationEvent, type ArticleItem, type StyleAnalysis, type TemplateItem,
  type TopicRecommendItem, type AccountTypeInfo,
} from '@/api/articles'
import { PhotoMatcher } from '@/components/PhotoMatcher'

const ACCOUNT_ICONS: Record<string, typeof Users> = {
  user: Users,
  designer: Ruler,
  dealer: Handshake,
}

export function BatchGenerate() {
  const navigate = useNavigate()
  const location = useLocation()
  const [tab, setTab] = useState<'batch' | 'imitate'>('batch')

  // ===== 批量生成状态（新工作流: 选题 → 账号类型 → 权重配图 → 生成） =====
  const [step, setStep] = useState<'topic' | 'account' | 'photos' | 'generating' | 'done'>('topic')
  const [topic, setTopic] = useState('')
  const [count, setCount] = useState(5)
  const [batchId, setBatchId] = useState<number | null>(null)
  const [, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentMessage, setCurrentMessage] = useState('')
  const [generatedArticles, setGeneratedArticles] = useState<ArticleItem[]>([])
  const [error, setError] = useState('')

  // 生成进度回调中需要最新值（避免闭包过期）
  const countRef = useRef(count)
  const stepRef = useRef(step)
  useEffect(() => { countRef.current = count }, [count])
  useEffect(() => { stepRef.current = step }, [step])

  // ① 公司方向 + 智能选题
  const [companyDirection, setCompanyDirection] = useState('')
  const [generatedTopics, setGeneratedTopics] = useState<TopicRecommendItem[]>([])
  const [topicsLoading, setTopicsLoading] = useState(false)

  // ② 账号类型 + 固定模板
  const [accountType, setAccountType] = useState<string>('')
  const [accountTemplates, setAccountTemplates] = useState<TemplateItem[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(false)

  // 目标字数范围（批量生成）
  const [wordMin, setWordMin] = useState(1200)
  const [wordMax, setWordMax] = useState(3000)

  useEffect(() => {
    const state = location.state as { topic?: string } | null
    if (state?.topic) {
      setTopic(state.topic)
      setTab('batch')
      setStep('topic')
      window.history.replaceState({}, '')
      toast.success('已从今日热点带入创作主题')
    }
  }, [location.state])

  // ① 生成选题：热点 + 知识库 + 公司方向
  const handleGenerateTopics = async () => {
    setTopicsLoading(true)
    setGeneratedTopics([])
    try {
      const res = await generateTopics(companyDirection.trim())
      if (res.recommendations.length === 0) {
        toast.info(res.message || '暂未生成合适选题，可修改公司方向后重试，或直接手动输入主题')
      } else {
        toast.success(`已生成 ${res.recommendations.length} 个推荐选题`)
      }
      setGeneratedTopics(res.recommendations)
    } catch {
      toast.error('选题生成失败，请稍后重试')
    } finally {
      setTopicsLoading(false)
    }
  }

  const handleUseTopic = (t: string) => {
    setTopic(t)
    toast.success('已选用该主题')
  }

  // ② 选择账号类型 → 加载该类型固定模板
  const handleSelectAccount = async (key: string) => {
    setAccountType(key)
    setTemplatesLoading(true)
    try {
      const list = await getTemplatesByAccountType(key)
      setAccountTemplates(list.filter(t => t.account_type === key))
    } catch {
      toast.error('加载模板失败')
      setAccountTemplates([])
    } finally {
      setTemplatesLoading(false)
    }
  }

  const handleCreateBatch = async () => {
    if (!topic.trim()) { toast.error('请先输入或选择文章主题'); return }
    if (!accountType) { toast.error('请选择账号类型'); return }
    try {
      const batch = await createBatch(topic.trim(), count, [], accountType)
      setBatchId(batch.id)
      setStep('photos')
      toast.success(`批次已创建（${getAccountTypeLabel(accountType)}）`)
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '创建批次失败')
    }
  }

  // ③ 权重配图确认后启动生成
  const handleStartGeneration = async () => {
    if (!batchId) return
    setError('')
    setGeneratedArticles([])
    setProgress(0)
    setGenerating(true)
    setStep('generating')

    try {
      // 账号类型的固定模板由后端按 account_type 自动注入；照片来自照片库
      await startGeneration(batchId, undefined, true, wordMin, wordMax)
    } catch {
      toast.error('启动生成失败')
      setGenerating(false)
      setStep('photos')
    }
  }

  // 生成进度订阅：SSE 实时进度 + 轮询兜底
  // 无论 SSE 因超时/断网/代理空闲等原因断开，轮询都会保证页面最终进入完成或失败态，
  // 避免卡在「正在生成文章」进度条。
  useEffect(() => {
    if (step !== 'generating' || !batchId) return

    const controller = subscribeBatchProgress(
      batchId,
      (event: GenerationEvent) => {
        switch (event.type) {
          case 'progress':
            setCurrentMessage(event.message)
            break
          case 'article_generated':
            if (event.data && Array.isArray(event.data)) {
              const articles = event.data as unknown as ArticleItem[]
              if (articles.length > 0) {
                setGeneratedArticles(articles)
                setProgress(Math.min(Math.ceil((articles.length / countRef.current) * 100), 99))
              }
            }
            break
          case 'completed':
            if (stepRef.current === 'generating') {
              setProgress(100)
              setStep('done')
              setGenerating(false)
              toast.success('所有文章生成完成！')
            }
            break
          case 'error':
            if (stepRef.current === 'generating') {
              setError(event.message)
              toast.error(event.message)
              setGenerating(false)
            }
            break
        }
      },
      () => {
        if (stepRef.current === 'generating') {
          setCurrentMessage('进度流已断开，正在通过轮询同步进度...')
        }
      },
    )

    // 轮询看门狗：SSE 不可用时兜底，保证最终收尾
    const pollTimer = window.setInterval(async () => {
      if (stepRef.current !== 'generating') return
      try {
        const batch = await getBatch(batchId)
        if (batch.status === 'completed') {
          if (stepRef.current !== 'generating') return
          try {
            const res = await getBatchArticles(batchId, { page: 1, page_size: 100 })
            if (res.items.length > 0) setGeneratedArticles(res.items)
          } catch {
            // 列表拉取失败不阻塞收尾
          }
          setProgress(100)
          setStep('done')
          setGenerating(false)
          toast.success('所有文章生成完成！')
        } else if (batch.status === 'failed') {
          if (stepRef.current !== 'generating') return
          const msg = batch.error_message || '生成失败'
          setError(msg)
          toast.error(msg)
          setGenerating(false)
        }
      } catch {
        // 网络抖动：忽略，下轮重试
      }
    }, 3000)

    return () => {
      controller.abort()
      window.clearInterval(pollTimer)
    }
  }, [step, batchId])

  const resetBatch = () => {
    setStep('topic')
    setTopic('')
    setCompanyDirection('')
    setGeneratedTopics([])
    setAccountType('')
    setAccountTemplates([])
    setGeneratedArticles([])
    setProgress(0)
    setError('')
    setBatchId(null)
  }

  // ===== 模仿创作状态 =====
  const [imitateUrl, setImitateUrl] = useState('')
  const [imitateText, setImitateText] = useState('')
  const [imitateTopic, setImitateTopic] = useState('')
  const [imitating, setImitating] = useState(false)
  const [imitateStyle, setImitateStyle] = useState<StyleAnalysis | null>(null)
  const [imitateResult, setImitateResult] = useState<{ batch_id: number; article: { id: number; title: string; word_count: number } } | null>(null)
  const [urlLoading, setUrlLoading] = useState(false)
  const [imitateBatchId, setImitateBatchId] = useState<number | null>(null)
  const [imitatePhotoIds, setImitatePhotoIds] = useState<number[]>([])

  // 目标字数范围（模仿创作）
  const [imitateWordMin, setImitateWordMin] = useState(1200)
  const [imitateWordMax, setImitateWordMax] = useState(3000)

  const handleFetchUrl = async () => {
    if (!imitateUrl.trim()) { toast.error('请输入网页链接'); return }
    setUrlLoading(true)
    try {
      const { content } = await fetchUrlContent(imitateUrl.trim())
      setImitateText(content)
      toast.success(`网页已抓取，共 ${content.length} 字，可点击"分析文章风格"进行风格分析`)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '网页抓取失败'
      toast.error(msg)
    } finally {
      setUrlLoading(false)
    }
  }

  const handleAnalyzeStyle = async () => {
    const text = imitateText.trim()
    if (!text || text.length < 100) { toast.error('请粘贴至少 100 字的参考文章'); return }
    setImitating(true)
    try {
      const style = await analyzeStyle(text)
      setImitateStyle(style)
      toast.success('风格分析完成')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '分析失败'
      toast.error(msg)
    }
    setImitating(false)
  }

  const handleImitateCreateBatch = async () => {
    if (!imitateTopic.trim()) { toast.error('请输入创作主题'); return }
    if (imitateText.trim().length < 100) { toast.error('请先粘贴至少 100 字的参考文章或抓取网页内容'); return }
    try {
      const batch = await createBatch(imitateTopic.trim(), 1, [])
      setImitateBatchId(batch.id)
      toast.success('批次已创建，请选择配图')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '创建批次失败'
      toast.error(msg)
    }
  }

  const handleImitate = async () => {
    if (!imitateTopic.trim()) { toast.error('请输入创作主题'); return }
    if (!imitateText.trim() || imitateText.trim().length < 100) { toast.error('请粘贴至少 100 字的参考文章'); return }
    setImitating(true)
    setImitateResult(null)
    try {
      const result = await imitateArticle({
        topic: imitateTopic.trim(),
        source_text: imitateText.trim(),
        photo_ids: imitatePhotoIds.length > 0 ? imitatePhotoIds : undefined,
        batch_id: imitateBatchId ?? undefined,
        style_analysis: imitateStyle ?? undefined,
        word_count_min: imitateWordMin,
        word_count_max: imitateWordMax,
      })
      setImitateResult({
        batch_id: result.batch_id,
        article: result.article,
      })
      toast.success('模仿文章生成完成！')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '模仿创作失败，请检查网络连接或稍后重试'
      toast.error(msg)
    } finally {
      setImitating(false)
    }
  }

  // ===== 渲染 =====

  const steps = ['选题', '账号类型', '权重配图', '生成']
  const stepIndex = step === 'topic' ? 0 : step === 'account' ? 1 : step === 'photos' ? 2 : step === 'generating' || step === 'done' ? 3 : 0

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">文章创作</h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI 驱动的文章创作，批量生成或模仿创作
          </p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'batch' | 'imitate')}>
        <TabsList className="w-full justify-start gap-1">
          <TabsTrigger value="batch" className="gap-1.5">
            <Sparkles className="h-4 w-4" />
            批量生成
          </TabsTrigger>
          <TabsTrigger value="imitate" className="gap-1.5">
            <Copy className="h-4 w-4" />
            模仿创作
          </TabsTrigger>
        </TabsList>

        <TabsContent value="batch" className="space-y-6 mt-4">

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {steps.map((s, i) => {
          const done = i < stepIndex || step === 'done'
          const active = i === stepIndex
          return (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className={`h-px w-8 ${done ? 'bg-primary' : 'bg-muted'}`} />}
              <div className={`flex items-center gap-1.5 text-xs font-medium ${
                done ? 'text-primary' : active ? 'text-foreground' : 'text-muted-foreground'
              }`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${
                  done ? 'bg-primary text-primary-foreground' :
                  active ? 'border-2 border-primary text-primary' :
                  'border-2 border-muted-foreground/30 text-muted-foreground'
                }`}>
                  {done ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
                </div>
                {s}
              </div>
            </div>
          )
        })}
      </div>

      {/* Step: 选题（公司方向 + 热点 + 知识库） */}
      {step === 'topic' && (
        <Card>
          <CardHeader>
            <CardTitle>第 1 步：生成选题</CardTitle>
            <CardDescription>输入公司创作方向，AI 将结合今日热点与知识库智能推荐选题；也可直接手动输入主题</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>公司创作方向（可选，自由填写）</Label>
              <Textarea
                placeholder="例如：产品优势、技术原理、工程案例、招商加盟、客户见证、施工工艺……想围绕公司哪些方面创作，就写哪些"
                value={companyDirection}
                onChange={e => setCompanyDirection(e.target.value)}
                className="min-h-[80px]"
              />
              <p className="text-xs text-muted-foreground">留空则按热点 + 知识库常规推荐</p>
            </div>

            <Button
              onClick={handleGenerateTopics}
              disabled={topicsLoading}
              className="w-full"
              size="lg"
            >
              {topicsLoading
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 正在分析热点与知识库…（约 10-30 秒）</>
                : <><Wand2 className="mr-2 h-4 w-4" />AI 生成选题</>}
            </Button>

            {generatedTopics.length > 0 && (
              <div className="space-y-3 border-t pt-4">
                <p className="text-sm font-medium">推荐选题（点击选用）：</p>
                {generatedTopics.map((rec, i) => (
                  <div key={i} className="rounded-xl border p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Badge variant="secondary" className="shrink-0">{rec.source}</Badge>
                        <span className="text-sm font-medium truncate">{rec.hot_title}</span>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground/70">切入角度：</span>{rec.reason}
                    </p>
                    <p className="text-sm">{rec.suggested_topic}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {rec.titles.map((t, j) => (
                        <Badge key={j} variant="outline" className="text-xs font-normal">{t}</Badge>
                      ))}
                    </div>
                    <Button
                      size="sm"
                      variant={topic === rec.suggested_topic ? 'default' : 'outline'}
                      onClick={() => handleUseTopic(rec.suggested_topic)}
                      className="mt-1"
                    >
                      <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                      {topic === rec.suggested_topic ? '已选用' : '选用此主题'}
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2 border-t pt-4">
              <Label>文章主题</Label>
              <Input
                placeholder="例如：电渗透防潮技术在别墅地下室的应用"
                value={topic}
                onChange={e => setTopic(e.target.value)}
                maxLength={500}
              />
              <p className="text-xs text-muted-foreground">{topic.length}/500</p>
            </div>

            <div className="space-y-2">
              <Label>生成数量：{count} 篇（每篇自动生成一个针对所选人群的角度）</Label>
              <Slider value={[count]} onValueChange={([v]) => setCount(v)} min={1} max={10} step={1} />
            </div>

            <div className="space-y-2">
              <Label>目标字数（每篇）：{wordMin} - {wordMax} 字</Label>
              <div className="flex items-center gap-3">
                <Input
                  type="number"
                  min={100}
                  max={20000}
                  step={100}
                  value={wordMin}
                  onChange={e => setWordMin(Math.max(100, Math.min(Number(e.target.value) || 100, wordMax)))}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">至</span>
                <Input
                  type="number"
                  min={100}
                  max={20000}
                  step={100}
                  value={wordMax}
                  onChange={e => setWordMax(Math.max(Number(e.target.value) || 100, wordMin))}
                  className="w-32"
                />
                <span className="text-xs text-muted-foreground">字</span>
              </div>
            </div>

            <Button onClick={() => { if (!topic.trim()) { toast.error('请先输入或选择主题'); return } setStep('account') }} className="w-full" size="lg" disabled={!topic.trim()}>
              <Sparkles className="mr-2 h-4 w-4" />
              选择账号类型，下一步
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step: 账号类型（目标受众） + 固定模板 */}
      {step === 'account' && (
        <Card>
          <CardHeader>
            <CardTitle>第 2 步：选择账号类型（目标受众）</CardTitle>
            <CardDescription>选择后自动套用该人群的固定写作模板，角度也将按该人群自动生成</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {ACCOUNT_TYPES.map((at: AccountTypeInfo) => {
                const Icon = ACCOUNT_ICONS[at.icon] || Users
                const selected = accountType === at.key
                return (
                  <button
                    key={at.key}
                    onClick={() => handleSelectAccount(at.key)}
                    className={`rounded-xl border-2 p-4 text-left transition-colors ${
                      selected
                        ? 'border-primary bg-primary/5'
                        : 'border-muted hover:border-primary/30'
                    }`}
                  >
                    <Icon className={`h-6 w-6 mb-2 ${selected ? 'text-primary' : 'text-muted-foreground'}`} />
                    <div className={`font-medium ${selected ? 'text-primary' : ''}`}>{at.label}</div>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{at.description}</p>
                  </button>
                )
              })}
            </div>

            {templatesLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载该人群的写作模板...
              </div>
            )}

            {accountType && !templatesLoading && (
              <div className="space-y-2 border-t pt-4">
                <p className="text-sm font-medium">
                  {getAccountTypeLabel(accountType)}固定模板（自动套用）
                </p>
                <div className="flex flex-wrap gap-2">
                  {accountTemplates.map(t => (
                    <div key={t.id} className="px-3 py-2 rounded-lg border bg-muted/30 text-sm">
                      <div className="font-medium">{t.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {t.type === 'structure' ? '结构模板' : '风格模板'}
                      </div>
                    </div>
                  ))}
                  {accountTemplates.length === 0 && (
                    <span className="text-sm text-muted-foreground">该人群暂无预设模板</span>
                  )}
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" size="lg" onClick={() => setStep('topic')}>
                返回上一步
              </Button>
              <Button className="flex-1" size="lg" onClick={handleCreateBatch} disabled={!accountType}>
                <Sparkles className="mr-2 h-4 w-4" />
                创建批次，权重配图
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step: 权重配图 */}
      {step === 'photos' && (
        <Card>
          <CardHeader>
            <CardTitle>第 3 步：权重配图</CardTitle>
            <CardDescription>
              结合「{topic}」与所选模板，按权重（LLM 相关度 + 标签命中 + 新鲜度 + 防复用）自动匹配照片
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <PhotoMatcher
              topic={topic}
              count={5}
              batchId={batchId}
              templateInstruction={accountTemplates.map(t => t.prompt_instruction).join('\n') || undefined}
              onConfirm={async (photoIds) => {
                toast.success(`已关联 ${photoIds.length} 张照片`)
                setStep('generating')
                setProgress(0)
                setGeneratedArticles([])
                setError('')
                await handleStartGeneration()
              }}
            />
            <div className="flex justify-between items-center">
              <Button variant="ghost" onClick={resetBatch}>
                <X className="mr-1 h-4 w-4" />
                重新开始
              </Button>
              <p className="text-xs text-muted-foreground">权重系数可在后端 settings.photo_match_weights 配置</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step: Generating */}
      {step === 'generating' && (
        <Card>
          <CardHeader>
            <CardTitle>正在生成文章...</CardTitle>
            <CardDescription>AI 正在按「{getAccountTypeLabel(accountType)}」人群与固定模板撰写文章，请稍候</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={progress} className="h-2" />
            <p className="text-sm text-muted-foreground text-center">{currentMessage || '准备中...'}</p>

            {generatedArticles.length > 0 && (
              <div className="space-y-2 mt-4">
                <p className="text-sm font-medium">已生成 {generatedArticles.length} 篇：</p>
                {generatedArticles.map(a => (
                  <div key={a.id} className="flex items-center gap-2 text-sm p-2 rounded bg-muted/50">
                    <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    <span className="truncate">{a.title}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{a.word_count} 字</span>
                  </div>
                ))}
              </div>
            )}

            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 p-3 mt-2">
                <p className="text-sm text-red-700 flex items-center gap-1.5">
                  <AlertCircle className="h-4 w-4 shrink-0" />{error}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              生成完成！
            </CardTitle>
            <CardDescription>共生成 {generatedArticles.length} 篇文章（{getAccountTypeLabel(accountType)} 视角）</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {generatedArticles.map(a => (
                <div key={a.id} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="text-sm truncate">{a.title}</span>
                    <Badge variant="outline" className="text-xs shrink-0">{a.word_count} 字</Badge>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => navigate(`/articles/${a.id}`)}
                  >
                    查看 <ChevronRight className="h-3 w-3 ml-1" />
                  </Button>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => batchId && navigate(`/batch/${batchId}/publish`)}>
                <Upload className="mr-2 h-4 w-4" />
                发布到平台
              </Button>
              <Button variant="outline" className="flex-1" onClick={resetBatch}>
                <Sparkles className="mr-2 h-4 w-4" />
                再生成一批
              </Button>
            </div>
           </CardContent>
        </Card>
      )}

        </TabsContent>

        {/* ===== 模仿创作 Tab ===== */}
        <TabsContent value="imitate" className="space-y-6 mt-4">

          <Card>
            <CardHeader>
              <CardTitle>第 1 步：导入参考文章</CardTitle>
              <CardDescription>粘贴一篇你认为写得好的文章，AI 将分析其风格并模仿创作</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <div className="flex-1 space-y-2">
                  <Label>网页链接（可选）</Label>
                  <div className="flex gap-2">
                    <Input
                      placeholder="https://..."
                      value={imitateUrl}
                      onChange={e => setImitateUrl(e.target.value)}
                    />
                    <Button variant="outline" onClick={handleFetchUrl} disabled={urlLoading}>
                      {urlLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label>或直接粘贴参考文章正文</Label>
                <Textarea
                  placeholder="将参考文章的完整内容粘贴到这里（至少 100 字）..."
                  value={imitateText}
                  onChange={e => setImitateText(e.target.value)}
                  className="min-h-[200px]"
                />
                <p className="text-xs text-muted-foreground">{imitateText.length} 字</p>
              </div>
              <Button variant="outline" onClick={handleAnalyzeStyle} disabled={imitating || imitateText.trim().length < 100}>
                {imitating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                分析文章风格
              </Button>
            </CardContent>
          </Card>

          {imitateStyle && (
            <Card className="border-primary/30 bg-primary/5">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Search className="h-4 w-4 text-primary" />
                  风格分析结果
                </CardTitle>
                <CardDescription>{imitateStyle.style_description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">语气</span>
                    <Badge variant="outline" className="text-xs">{imitateStyle.tone}</Badge>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">开头方式</span>
                    <Badge variant="outline" className="text-xs">{imitateStyle.opening_style}</Badge>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">段落结构</span>
                    <Badge variant="outline" className="text-xs">{imitateStyle.structure}</Badge>
                  </div>
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">论证手法</span>
                    <Badge variant="outline" className="text-xs">{imitateStyle.argument_pattern}</Badge>
                  </div>
                  <div className="col-span-2 space-y-1">
                    <span className="text-xs text-muted-foreground">结尾方式</span>
                    <Badge variant="outline" className="text-xs">{imitateStyle.closing_style}</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>第 2 步：输入创作主题</CardTitle>
              <CardDescription>告诉 AI 你想写什么主题，它将模仿参考文章的风格来创作</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>创作主题</Label>
                <Input
                  placeholder="例如：电渗透防潮技术在沿海别墅的应用"
                  value={imitateTopic}
                  onChange={e => setImitateTopic(e.target.value)}
                  maxLength={500}
                />
                <p className="text-xs text-muted-foreground">{imitateTopic.length}/500</p>
              </div>

              <div className="space-y-2">
                <Label>目标字数：{imitateWordMin} - {imitateWordMax} 字</Label>
                <div className="flex items-center gap-3">
                  <Input
                    type="number"
                    min={100}
                    max={20000}
                    step={100}
                    value={imitateWordMin}
                    onChange={e => setImitateWordMin(Math.max(100, Math.min(Number(e.target.value) || 100, imitateWordMax)))}
                    className="w-32"
                  />
                  <span className="text-sm text-muted-foreground">至</span>
                  <Input
                    type="number"
                    min={100}
                    max={20000}
                    step={100}
                    value={imitateWordMax}
                    onChange={e => setImitateWordMax(Math.max(Number(e.target.value) || 100, imitateWordMin))}
                    className="w-32"
                  />
                  <span className="text-xs text-muted-foreground">字</span>
                </div>
              </div>

              {!imitateBatchId ? (
                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleImitateCreateBatch}
                  disabled={!imitateTopic.trim()}
                >
                  <PenLine className="mr-2 h-4 w-4" />
                  创建批次并选择配图
                </Button>
              ) : (
                <div className="space-y-4 pt-2 border-t">
                  <div className="flex items-center gap-2">
                    <Library className="h-4 w-4 text-primary" />
                    <span className="text-sm font-medium">选择配图（可选）</span>
                  </div>
                  <PhotoMatcher
                    topic={imitateTopic}
                    count={50}
                    batchId={imitateBatchId}
                    onConfirm={(photoIds) => {
                      setImitatePhotoIds(photoIds)
                      toast.success(`已选择 ${photoIds.length} 张照片`)
                    }}
                  />
                  <div className="flex justify-end">
                    <Button variant="outline" size="sm" onClick={() => toast.success('已跳过配图选择')}>
                      跳过配图
                    </Button>
                  </div>
                </div>
              )}

              <Button
                className="w-full"
                size="lg"
                onClick={handleImitate}
                disabled={imitating || !imitateTopic.trim() || imitateText.trim().length < 100}
              >
                {imitating ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 正在分析风格并创作中…</>
                ) : (
                  <><Copy className="mr-2 h-4 w-4" />开始模仿创作</>
                )}
              </Button>
            </CardContent>
          </Card>

          {imitateResult && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  创作完成！
                </CardTitle>
                <CardDescription>已按照参考文章风格生成新文章</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 rounded-lg bg-muted/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">{imitateResult.article.title}</span>
                    </div>
                    <Badge variant="outline">{imitateResult.article.word_count} 字</Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button className="flex-1" onClick={() => navigate(`/articles/${imitateResult.article.id}`)}>
                    <FileText className="mr-2 h-4 w-4" />
                    查看文章并编辑
                  </Button>
                  <Button variant="outline" className="flex-1" onClick={() => navigate(`/batch/${imitateResult.batch_id}/publish`)}>
                    <Upload className="mr-2 h-4 w-4" />
                    发布到平台
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => { setImitateResult(null); setImitateTopic(''); setImitateText(''); setImitateStyle(null); setImitateBatchId(null); setImitatePhotoIds([]); setImitateUrl(''); setImitating(false); setUrlLoading(false) }}>
                    <X className="mr-1 h-4 w-4" />
                    重新创作
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
