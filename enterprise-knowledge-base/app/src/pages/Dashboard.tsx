import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileText, BookOpen, Sparkles,
  Clock, TrendingUp, AlertTriangle, MessageSquare,
} from 'lucide-react'
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { getDashboardStats } from '@/api/dashboard'
import { getDocuments } from '@/api/documents'
import { getBatches } from '@/api/articles'
import type { DashboardStats } from '@/api/dashboard'

export function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [docCount, setDocCount] = useState(0)
  const [batchCount, setBatchCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const dStats = await getDashboardStats()
        setStats(dStats)
      } catch {
        // ignore
      }
      try {
        const docs = await getDocuments({ page_size: 1, page: 1 })
        setDocCount(docs.total)
      } catch {
        // ignore
      }
      try {
        const batches = await getBatches({ page_size: 1, page: 1 })
        setBatchCount(batches.total)
      } catch {
        // ignore
      }
      setLoading(false)
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-48 bg-muted rounded" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 bg-muted rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  const statCards = [
    {
      label: '今日咨询',
      value: stats?.today_chats ?? 0,
      icon: MessageSquare,
      sub: `FAQ 命中率 ${((stats?.faq_hit_rate ?? 0) * 100).toFixed(0)}%`,
    },
    {
      label: '知识库文档',
      value: docCount,
      icon: BookOpen,
      sub: '已向量化存储',
    },
    {
      label: '文章批次',
      value: batchCount,
      icon: Sparkles,
      sub: 'AI 批量生成',
    },
    {
      label: '待处理',
      value: (stats?.pending_reviews ?? 0) + (stats?.pending_unanswered ?? 0),
      icon: Clock,
      sub: `${stats?.pending_reviews ?? 0} 审核 · ${stats?.pending_unanswered ?? 0} 未答`,
    },
  ]

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">仪表盘</h1>
          <p className="text-sm text-muted-foreground mt-1">企业知识库系统概览</p>
        </div>
        <Button onClick={() => navigate('/batch-generate')}>
          <Sparkles className="mr-2 h-4 w-4" />
          批量生成文章
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map(card => (
          <Card key={card.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.label}
              </CardTitle>
              <card.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{card.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{card.sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">快捷操作</CardTitle>
            <CardDescription>常用功能入口</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button variant="outline" className="w-full justify-start" onClick={() => navigate('/batch-generate')}>
              <Sparkles className="mr-2 h-4 w-4" />
              批量生成营销文章
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={() => navigate('/knowledge-base')}>
              <BookOpen className="mr-2 h-4 w-4" />
              管理知识库文档
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={() => navigate('/articles')}>
              <FileText className="mr-2 h-4 w-4" />
              查看文章批次
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">系统状态</CardTitle>
            <CardDescription>核心服务监控</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">用户满意度</span>
              <span className="font-medium text-green-600">
                {((stats?.feedback_good_rate ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
            {stats && stats.trend.length > 0 && (
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  近 7 日咨询趋势数据已加载
                </span>
              </div>
            )}
            {(stats?.pending_reviews ?? 0) > 0 && (
              <div className="flex items-center gap-2 text-sm text-orange-600">
                <AlertTriangle className="h-4 w-4" />
                有 {stats?.pending_reviews} 条文档待审核
              </div>
            )}
            {(stats?.pending_unanswered ?? 0) > 0 && (
              <div className="flex items-center gap-2 text-sm text-orange-600">
                <AlertTriangle className="h-4 w-4" />
                有 {stats?.pending_unanswered} 条未回答问题
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
