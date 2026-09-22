import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, HelpCircle, ThumbsUp, Clock, TrendingUp, ArrowRight } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getDashboardStats, type DashboardStats } from '@/api/dashboard'

export function Overview() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getDashboardStats()
      .then(d => { if (!cancelled) setStats(d) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-6xl mx-auto animate-pulse">
        <div className="h-8 w-40 bg-muted rounded" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-muted rounded-xl" />)}
        </div>
      </div>
    )
  }

  const maxCount = Math.max(...(stats?.trend.map(d => d.count) ?? [0]), 1)

  const cards = [
    { label: '今日对话', value: stats?.today_chats ?? 0, icon: MessageSquare, sub: '内部 + 客服合计' },
    { label: 'FAQ 命中率', value: `${((stats?.faq_hit_rate ?? 0) * 100).toFixed(0)}%`, icon: HelpCircle, sub: '今日问答命中 FAQ 比例' },
    { label: '反馈好评率', value: `${((stats?.feedback_good_rate ?? 0) * 100).toFixed(0)}%`, icon: ThumbsUp, sub: '近 30 天点赞比例' },
    { label: '待审文档', value: stats?.pending_reviews ?? 0, icon: Clock, sub: (stats?.pending_reviews ?? 0) > 0 ? '有待审核文档' : '无待审' },
  ]

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">控制台概览</h1>
        <p className="text-sm text-muted-foreground mt-1">企业知识库系统运行概览</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map(c => (
          <Card key={c.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{c.label}</CardTitle>
              <c.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{c.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{c.sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center gap-2">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">近 7 天对话趋势</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(stats?.trend ?? []).map(d => (
              <div key={d.date} className="flex items-center gap-2">
                <span className="w-12 text-xs text-muted-foreground text-right">{d.date}</span>
                <div className="flex-1 h-6 rounded bg-muted overflow-hidden flex items-center">
                  <div
                    className="h-full rounded bg-gradient-to-r from-primary to-primary/60 flex items-center justify-end pr-2"
                    style={{ width: `${maxCount > 0 ? Math.max((d.count / maxCount) * 100, 6) : 6}%` }}
                  >
                    <span className="text-xs text-primary-foreground font-medium">{d.count}</span>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">待处理事项</CardTitle>
            <CardDescription>需人工跟进</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center justify-center h-6 min-w-6 px-1.5 rounded bg-amber-100 text-amber-700 text-xs font-medium">
                {stats?.pending_reviews ?? 0}
              </span>
              <span className="text-sm flex-1">待审核文档</span>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => navigate('/console/review')}>
                去审核 <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </div>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center justify-center h-6 min-w-6 px-1.5 rounded bg-slate-100 text-slate-600 text-xs font-medium">
                {stats?.pending_unanswered ?? 0}
              </span>
              <span className="text-sm flex-1">未命中问题</span>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => navigate('/console/unanswered')}>
                去处理 <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
