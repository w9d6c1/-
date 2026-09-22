import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Download, Share2, CheckCircle2, XCircle,
  Clock, Loader2, FileText, AlertCircle,
  Calendar,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import {
  getBatch, getBatchArticles, publishBatch, publishArticle,
  getBatchPublishingStatus, exportBatch, getPlatforms, getAccounts,
  getBridgeStatus,
  type BatchDetail, type ArticleItem, type PlatformInfo,
  type PublishingRecord, type PlatformAccountItem, type BridgeStatus,
} from '@/api/articles'

const POLL_INTERVAL_MS = 5000

function statusBadge(record: PublishingRecord | undefined) {
  if (!record) return null
  if (record.status === 'published') {
    return <Badge className="bg-green-600/15 text-green-600 border-green-600/30"><CheckCircle2 className="h-3 w-3 mr-1" />已发布</Badge>
  }
  if (record.status === 'failed') {
    return (
      <Badge variant="destructive" title={record.error_message || '未知错误'}>
        <XCircle className="h-3 w-3 mr-1" />失败
      </Badge>
    )
  }
  if (record.status === 'publishing') {
    return <Badge className="bg-blue-600/15 text-blue-600 border-blue-600/30"><Loader2 className="h-3 w-3 mr-1 animate-spin" />发布中</Badge>
  }
  return <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" />排队中</Badge>
}

const PLATFORM_LABELS: Record<string, string> = {
  toutiao: '头条号', baijia: '百家号', zhihu: '知乎',
  wangyi: '网易号', csdn: 'CSDN', jianshu: '简书',
  weibo: '微博', xiaohongshu: '小红书', yidianhao: '一点号',
  douyin_tuwen: '抖音图文',
}

export function PublishManager() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [articles, setArticles] = useState<ArticleItem[]>([])
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [accounts, setAccounts] = useState<PlatformAccountItem[]>([])
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [publishRecords, setPublishRecords] = useState<Map<number, PublishingRecord[]>>(new Map())
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState(false)
  const [useSchedule, setUseSchedule] = useState(false)
  const [scheduledTime, setScheduledTime] = useState('')
  const [bridgeOk, setBridgeOk] = useState<boolean | null>(null)
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus | null>(null)
  const [polling, setPolling] = useState(false)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const batchId = Number(id)

  const fetchStatuses = useCallback(async () => {
    try {
      const records = await getBatchPublishingStatus(batchId)
      const map = new Map<number, PublishingRecord[]>()
      for (const r of records) {
        const list = map.get(r.article_id) || []
        list.push(r)
        map.set(r.article_id, list)
      }
      setPublishRecords(map)
      const hasActive = records.some(r => r.status === 'pending' || r.status === 'publishing')
      return hasActive
    } catch {
      return false
    }
  }, [batchId])

  const startPolling = useCallback(async () => {
    setPolling(true)
    const tick = async () => {
      const hasActive = await fetchStatuses()
      if (hasActive) {
        pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS)
      } else {
        setPolling(false)
      }
    }
    await tick()
  }, [fetchStatuses])

  useEffect(() => {
    fetchStatuses().then(hasActive => { if (hasActive) startPolling() })
    return () => { if (pollTimer.current) clearTimeout(pollTimer.current) }
  }, [fetchStatuses, startPolling])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [b, arts, plats, accs] = await Promise.all([
        getBatch(batchId),
        getBatchArticles(batchId),
        getPlatforms(),
        getAccounts(),
      ])
      setBatch(b)
      setArticles(arts.items)
      setPlatforms(plats)
      setAccounts(accs)
    } catch {
      toast.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [batchId])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    getBridgeStatus()
      .then(d => { setBridgeOk(d.ok === true); setBridgeStatus(d) })
      .catch(() => { setBridgeOk(false); setBridgeStatus(null) })
  }, [])

  const handlePublishBatch = async () => {
    if (selectedPlatforms.length === 0) { toast.error('请选择发布平台'); return }
    if (!selectedAccountId) { toast.error('请选择发布账号'); return }
    // 发布前检查扩展连接状态
    if (bridgeStatus?.extension_connected) {
      const selectedAccount = accounts.find(a => a.id === selectedAccountId)
      const group = selectedAccount?.account_group
      if (group && !bridgeStatus.extension_connected[group]) {
        toast.error(`账号组 ${group} 的 Chrome 扩展未连接，请先在浏览器中启用扩展的 CLI/MCP 连接`)
        return
      }
    }
    setPublishing(true)
    try {
      const scheduledAt = useSchedule && scheduledTime ? new Date(scheduledTime).toISOString() : undefined
      const result = await publishBatch(batchId, selectedPlatforms, undefined, selectedAccountId, scheduledAt)
      if (useSchedule && scheduledTime) {
        toast.success(`已排期 ${result.record_count} 个发布任务`)
      } else if (result.record_count === 0) {
        toast.info('所选文章均已有排队中的发布任务，未重复提交')
      } else {
        toast.success(`已提交 ${result.record_count} 个发布任务，后台异步执行中`)
      }
      loadData()
      startPolling()
    } catch {
      toast.error('发布失败')
    } finally {
      setPublishing(false)
    }
  }

  const handlePublishArticle = async (articleId: number) => {
    if (selectedPlatforms.length === 0) { toast.error('请选择发布平台'); return }
    if (!selectedAccountId) { toast.error('请选择发布账号'); return }
    // 发布前检查扩展连接状态
    if (bridgeStatus?.extension_connected) {
      const selectedAccount = accounts.find(a => a.id === selectedAccountId)
      const group = selectedAccount?.account_group
      if (group && !bridgeStatus.extension_connected[group]) {
        toast.error(`账号组 ${group} 的 Chrome 扩展未连接，请先在浏览器中启用扩展的 CLI/MCP 连接`)
        return
      }
    }
    try {
      const scheduledAt = useSchedule && scheduledTime ? new Date(scheduledTime).toISOString() : undefined
      const result = await publishArticle(articleId, selectedPlatforms, selectedAccountId, scheduledAt)
      if (useSchedule && scheduledTime) {
        toast.success('已排期')
      } else if (result.records.length === 0) {
        toast.info('该文章已有排队中的发布任务，未重复提交')
      } else {
        toast.success('已加入发布队列，后台异步执行中')
      }
      startPolling()
    } catch {
      toast.error('发布失败')
    }
  }

  const handleExportBatch = async () => {
    try {
      const blob = await exportBatch(batchId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${batch?.topic || 'batch'}-文章.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('批量导出成功')
    } catch {
      toast.error('导出失败')
    }
  }

  const togglePlatform = (id: string) => {
    setSelectedPlatforms(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id])
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!batch) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-full">
        <p className="text-sm text-muted-foreground mb-4">批次不存在</p>
        <Button onClick={() => navigate('/articles')}>返回文章列表</Button>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/articles')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回
          </Button>
          <div>
            <h1 className="text-xl font-semibold">{batch.topic}</h1>
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              {batch.generated_count}/{batch.article_count} 篇 · {batch.status}
              {polling && (
                <span className="flex items-center gap-1 text-xs text-primary">
                  <Loader2 className="h-3 w-3 animate-spin" />发布进行中
                </span>
              )}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={handleExportBatch}>
          <Download className="mr-2 h-4 w-4" />
          批量导出 ZIP
        </Button>
      </div>

      {/* Platform Selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">发布平台</CardTitle>
          <CardDescription>选择目标平台和账号进行发布</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            {platforms.map(p => (
              <button
                key={p.platform}
                onClick={() => togglePlatform(p.platform)}
                className={`px-4 py-2 rounded-lg border text-sm transition-colors ${
                  selectedPlatforms.includes(p.platform)
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-muted hover:border-muted-foreground/30'
                }`}
              >
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {p.method === 'direct_api' ? 'API直发' :
                   p.method === 'wechatsync' ? 'CLI同步' : '手动导出'}
                </div>
              </button>
            ))}
          </div>

          {/* Account Selector */}
          <div>
            <Label className="text-sm mb-2 block">选择发布账号</Label>
            {accounts.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                暂无可用的平台账号，请先在
                <a href="#/accounts" className="text-primary underline mx-1">平台账号</a>
                中添加
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {accounts.filter(a => selectedPlatforms.length === 0 || selectedPlatforms.some(p =>
                  a.platform_id === p
                )).map(a => (
                  <button
                    key={a.id}
                    onClick={() => setSelectedAccountId(a.id)}
                    className={`px-3 py-1.5 rounded-md text-xs border transition-colors ${
                      selectedAccountId === a.id
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-muted hover:border-muted-foreground/30'
                    }`}
                  >
                    {a.account_group && (
                      <Badge variant="outline" className="text-[10px] mr-1 px-1 py-0">{a.account_group}</Badge>
                    )}
                    <span className="font-medium">{a.account_name}</span>
                    <span className="text-muted-foreground ml-1">
                      ({PLATFORM_LABELS[a.platform_id] || a.platform_id})
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Schedule Toggle */}
          <div className="flex items-center gap-4 pt-2 border-t">
            <div className="flex items-center gap-2">
              <Switch checked={useSchedule} onCheckedChange={setUseSchedule} />
              <Label className="text-sm cursor-pointer" onClick={() => setUseSchedule(!useSchedule)}>
                <Calendar className="h-4 w-4 inline mr-1" />
                定时发布
              </Label>
            </div>
            {useSchedule && (
              <Input
                type="datetime-local"
                value={scheduledTime}
                onChange={e => setScheduledTime(e.target.value)}
                className="w-56 h-8 text-xs"
              />
            )}
          </div>

          {bridgeOk === false && selectedPlatforms.length > 0 && (
            <p className="text-xs text-destructive flex items-center gap-1 mt-1">
              <AlertCircle className="h-3 w-3" />
              桥接器未启动（http://127.0.0.1:3010），多平台发布将不可用。请先运行 publisher-bridge。
            </p>
          )}
          {bridgeStatus?.extension_connected && (
            <div className="flex flex-wrap gap-2 text-[10px]">
              {Object.entries(bridgeStatus.extension_connected).map(([group, connected]) => (
                <span key={group} className={`px-2 py-0.5 rounded border ${
                  connected ? 'border-green-300 bg-green-50 text-green-700' : 'border-red-200 bg-red-50 text-red-600'
                }`}>
                  {group}: {connected ? '已连接' : '未连接'}
                </span>
              ))}
            </div>
          )}

          <Button
            className="mt-2"
            onClick={handlePublishBatch}
            disabled={selectedPlatforms.length === 0 || !selectedAccountId || publishing}
          >
            {publishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Share2 className="mr-2 h-4 w-4" />}
            {useSchedule && scheduledTime ? '排期发布' : '一键发布全批次'}
            {useSchedule && scheduledTime ? '' : ` 到 ${selectedPlatforms.length} 个平台`}
          </Button>
        </CardContent>
      </Card>

      {/* Platform Progress */}
      {polling && (() => {
        const allRecords: PublishingRecord[] = []
        for (const list of publishRecords.values()) {
          allRecords.push(...list)
        }
        const grouped = new Map<string, { done: number; publishing: number; failed: number; pending: number; errors: string[] }>()
        for (const r of allRecords) {
          const g = grouped.get(r.platform) || { done: 0, publishing: 0, failed: 0, pending: 0, errors: [] }
          if (r.status === 'published') g.done++
          else if (r.status === 'publishing') g.publishing++
          else if (r.status === 'failed') { g.failed++; if (r.error_message && !g.errors.includes(r.error_message)) g.errors.push(r.error_message) }
          else g.pending++
          grouped.set(r.platform, g)
        }
        const total = allRecords.length
        const totalDone = [...grouped.values()].reduce((s, g) => s + g.done, 0)

        return (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">发布进度</CardTitle>
              <CardDescription>整体: {totalDone}/{total} 已完成</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {[...grouped.entries()].map(([platform, g]) => {
                const count = g.done + g.failed + g.publishing + g.pending
                const pct = count > 0 ? Math.round((g.done / count) * 100) : 0
                const key = `${platform}-${g.done}-${g.publishing}-${g.pending}-${g.failed}`
                return (
                  <div key={key} className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{PLATFORM_LABELS[platform] || platform}</span>
                        {g.publishing > 0 && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />}
                        {g.done === count && g.done > 0 && <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />}
                        {g.failed === count && g.failed > 0 && <XCircle className="h-3.5 w-3.5 text-destructive" />}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {g.done}/{count} 已完成
                        {g.failed > 0 && g.failed < count && ` · ${g.failed} 失败`}
                      </span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2.5 overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${pct}%`,
                          background: g.failed === count ? 'hsl(var(--destructive))'
                            : pct === 100 ? 'hsl(142, 76%, 36%)'
                            : 'hsl(var(--primary))'
                        }}
                      />
                    </div>
                    {g.failed > 0 && g.errors.length > 0 && (
                      <div className="space-y-0.5">
                        {g.errors.map((err, i) => (
                          <p key={i} className="text-xs text-destructive truncate" title={err}>{err}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </CardContent>
          </Card>
        )
      })()}

      {/* Articles */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">文章列表 ({articles.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {articles.map(article => {
            const records = publishRecords.get(article.id) || []
            const latestByPlatform = new Map<string, PublishingRecord>()
            for (const r of records) {
              if (!latestByPlatform.has(r.platform)) latestByPlatform.set(r.platform, r)
            }
            const platformRecords = [...latestByPlatform.values()]
            return (
              <div key={article.id} className="p-3 rounded-lg border hover:bg-muted/30 transition-colors space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <button
                        className="block w-full text-sm font-medium truncate hover:text-primary text-left"
                        onClick={() => navigate(`/articles/${article.id}`)}
                      >
                        {article.title}
                      </button>
                      <div className="text-xs text-muted-foreground mt-0.5 truncate">
                        {article.word_count} 字 · {article.angle}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => handlePublishArticle(article.id)}
                      disabled={selectedPlatforms.length === 0}
                    >
                      <Share2 className="h-3 w-3 mr-1" />
                      发布
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => navigate(`/articles/${article.id}`)}
                    >
                      查看
                    </Button>
                  </div>
                </div>
                {platformRecords.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pl-7">
                    {platformRecords.map(r => (
                      <span key={r.id} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        {PLATFORM_LABELS[r.platform] || r.platform}
                        {statusBadge(r)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>
    </div>
  )
}
