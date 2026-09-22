import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Flame, RefreshCw, Loader2, Sparkles, PenLine,
  ExternalLink, AlertCircle, TrendingUp,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import {
  getHotTopics, recommendHotTitles,
  type HotTopicsResponse, type HotRecommendResponse,
} from '@/api/articles'

const SOURCE_ORDER = ['baidu', 'weibo', 'zhihu', 'toutiao'] as const

function formatHotValue(v: number): string {
  if (!v) return ''
  if (v >= 100000000) return `${(v / 100000000).toFixed(1)}亿`
  if (v >= 10000) return `${Math.round(v / 10000)}万`
  return String(v)
}

function formatCachedAt(ts: number | null): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function HotTopics() {
  const navigate = useNavigate()
  const [data, setData] = useState<HotTopicsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('baidu')

  const [recommending, setRecommending] = useState(false)
  const [recommend, setRecommend] = useState<HotRecommendResponse | null>(null)

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    try {
      const res = await getHotTopics(refresh)
      setData(res)
      if (refresh) toast.success('热榜已刷新')
    } catch {
      toast.error('热榜加载失败，请稍后重试')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleRecommend = async () => {
    setRecommending(true)
    setRecommend(null)
    try {
      const res = await recommendHotTitles(8)
      setRecommend(res)
      if (res.message) toast.error(res.message)
      else if (res.recommendations.length === 0) toast.info('今日热点中没有与知识库匹配的选题')
      else toast.success(`已生成 ${res.recommendations.length} 个推荐选题`)
    } catch {
      toast.error('智能推荐失败，请稍后重试')
    } finally {
      setRecommending(false)
    }
  }

  const handleUseTopic = (topic: string) => {
    navigate('/batch-generate', { state: { topic } })
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">正在抓取今日热点…</span>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Flame className="h-6 w-6 text-orange-500" />
            今日热点
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            全网热榜实时聚合，结合知识库智能推荐今日选题
          </p>
        </div>
        <Button variant="outline" onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          刷新热榜
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start gap-1">
          {SOURCE_ORDER.map(s => {
            const src = data?.sources[s]
            return (
              <TabsTrigger key={s} value={s} className="gap-1.5">
                {src?.label ?? s}
                {src && !src.ok && <AlertCircle className="h-3 w-3 text-destructive" />}
              </TabsTrigger>
            )
          })}
        </TabsList>

        {SOURCE_ORDER.map(s => {
          const src = data?.sources[s]
          return (
            <TabsContent key={s} value={s} className="mt-4">
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{src?.label}</CardTitle>
                    {src?.cached_at && (
                      <span className="text-xs text-muted-foreground">
                        缓存于 {formatCachedAt(src.cached_at)}
                        {src.stale && '（刷新失败，显示旧数据）'}
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {!src?.ok ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
                      <AlertCircle className="h-4 w-4" />
                      该热榜源暂不可用，请稍后刷新重试
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {src.items.map(item => (
                        <div
                          key={`${s}-${item.rank}`}
                          className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-muted/50 transition-colors"
                        >
                          <span className={`w-6 text-center text-sm font-semibold shrink-0 ${
                            item.rank <= 3 ? 'text-orange-500' : 'text-muted-foreground'
                          }`}>
                            {item.rank}
                          </span>
                          <span className="text-sm flex-1 truncate">{item.title}</span>
                          {item.hot_value > 0 && (
                            <span className="text-xs text-muted-foreground shrink-0 flex items-center gap-0.5">
                              <TrendingUp className="h-3 w-3" />
                              {formatHotValue(item.hot_value)}
                            </span>
                          )}
                          {item.url && (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-muted-foreground hover:text-foreground shrink-0"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )
        })}
      </Tabs>

      <Card className="border-primary/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            智能选题推荐
          </CardTitle>
          <CardDescription>
            AI 分析今日热点与知识库内容的结合点，自动推荐适合今天创作的文章标题
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button onClick={handleRecommend} disabled={recommending} size="lg" className="w-full">
            {recommending
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 正在分析热点与知识库…（约 10-30 秒）</>
              : <><Sparkles className="mr-2 h-4 w-4" />生成今日选题推荐</>}
          </Button>

          {recommend && recommend.recommendations.length > 0 && (
            <div className="space-y-3">
              {recommend.recommendations.map((rec, i) => (
                <div key={i} className="rounded-xl border p-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge variant="secondary" className="shrink-0">
                        {data?.sources[rec.source]?.label ?? rec.source}
                      </Badge>
                      <span className="text-sm font-medium truncate">{rec.hot_title}</span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground/70">切入角度：</span>{rec.reason}
                  </p>
                  <div className="space-y-1.5">
                    {rec.titles.map((t, j) => (
                      <div key={j} className="flex items-center gap-2 text-sm bg-muted/50 rounded-lg px-3 py-2">
                        <PenLine className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="flex-1">{t}</span>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <p className="text-xs text-muted-foreground truncate flex-1">
                      建议主题：{rec.suggested_topic}
                    </p>
                    <Button size="sm" onClick={() => handleUseTopic(rec.suggested_topic)} className="shrink-0">
                      <PenLine className="mr-1 h-3.5 w-3.5" />
                      以此创作
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
