import { useState, useEffect } from 'react'
import {
  TrendingUp, CheckCircle2, Clock, AlertCircle,
  Loader2,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { getPublishingStats, type PublishingStats, type PublishingRecord } from '@/api/articles'

const PLATFORM_LABELS: Record<string, string> = {
  toutiao: '头条号',
  baijia: '百家号',
  zhihu: '知乎',
  wangyi: '网易号',
  csdn: 'CSDN',
  jianshu: '简书',
  weibo: '微博',
  xiaohongshu: '小红书',
  yidianhao: '一点号',
  douyin_tuwen: '抖音图文',
}

const STATUS_VARIANTS: Record<string, 'default' | 'destructive' | 'secondary' | 'outline'> = {
  published: 'default',
  failed: 'destructive',
  pending: 'secondary',
}

const STATUS_LABELS: Record<string, string> = {
  published: '已发布',
  failed: '失败',
  pending: '待发布',
}

export function PublishDashboard() {
  const [stats, setStats] = useState<PublishingStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getPublishingStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">加载统计数据失败</p>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-xl font-semibold">发布仪表板</h1>
        <p className="text-sm text-muted-foreground">查看所有平台账号的发布数据</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">今日发布</p>
                <p className="text-2xl font-bold">{stats.today_published}</p>
              </div>
              <div className="p-2 rounded-full bg-primary/10">
                <TrendingUp className="h-5 w-5 text-primary" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">累计成功</p>
                <p className="text-2xl font-bold">{stats.total_published}</p>
              </div>
              <div className="p-2 rounded-full bg-green-100 dark:bg-green-900/20">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">失败 / 待处理</p>
                <p className="text-2xl font-bold">
                  <span className="text-red-500">{stats.total_failed}</span>
                  <span className="text-muted-foreground mx-1">/</span>
                  <span className="text-muted-foreground">{stats.total_pending}</span>
                </p>
              </div>
              <div className="p-2 rounded-full bg-orange-100 dark:bg-orange-900/20">
                <AlertCircle className="h-5 w-5 text-orange-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {stats.by_platform.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">各平台发布量</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {stats.by_platform.map((item) => (
                <div key={item.platform} className="flex items-center justify-between text-sm">
                  <span>{PLATFORM_LABELS[item.platform] || item.platform}</span>
                  <Badge variant="secondary">{item.count} 篇</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近发布记录</CardTitle>
        </CardHeader>
        <CardContent>
          {stats.recent_records.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">暂无发布记录</p>
          ) : (
            <div className="space-y-2">
              {stats.recent_records.slice(0, 15).map((r: PublishingRecord) => (
                <div key={r.id} className="flex items-center justify-between p-2 rounded-lg border text-sm">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <Badge variant={STATUS_VARIANTS[r.status] || 'outline'} className="shrink-0">
                      {STATUS_LABELS[r.status] || r.status}
                    </Badge>
                    <span className="text-muted-foreground shrink-0">
                      {PLATFORM_LABELS[r.platform] || r.platform}
                    </span>
                    <span className="truncate">
                      {r.platform_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.error_message && (
                      <span className="text-xs text-destructive truncate max-w-[150px]" title={r.error_message}>
                        {r.error_message}
                      </span>
                    )}
                    {r.published_at && (
                      <span className="text-xs text-muted-foreground">
                        {new Date(r.published_at).toLocaleString('zh-CN')}
                      </span>
                    )}
                    {r.scheduled_at && r.status === 'pending' && (
                      <Badge variant="outline" className="text-xs">
                        <Clock className="h-3 w-3 mr-1" />
                        定时 {new Date(r.scheduled_at).toLocaleString('zh-CN')}
                      </Badge>
                    )}
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
