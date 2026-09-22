import { useEffect, useState } from 'react'
import { Loader2, RefreshCw, ThumbsUp, ThumbsDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from 'sonner'
import { fetchFeedbacks, fetchFeedbackStats, type Feedback, type FeedbackStats } from '@/api/feedback'

export function Feedbacks() {
  const [rows, setRows] = useState<Feedback[]>([])
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [rating, setRating] = useState('')
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    fetchFeedbacks({ rating: rating || undefined, per_page: 100 })
      .then(r => { if (active) setRows(r) })
      .catch(() => toast.error('加载反馈失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [rating, reloadKey])

  useEffect(() => {
    let active = true
    fetchFeedbackStats().then(s => { if (active) setStats(s) }).catch(() => {})
    return () => { active = false }
  }, [reloadKey])

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">用户反馈</h1>
          <p className="text-sm text-muted-foreground mt-1">问答点赞 / 点踩记录</p>
        </div>
        <Button variant="outline" onClick={() => { setLoading(true); setReloadKey(k => k + 1) }}>
          <RefreshCw className="mr-2 h-4 w-4" />刷新
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card><CardContent className="pt-6"><div className="text-2xl font-bold">{stats?.total ?? 0}</div><p className="text-xs text-muted-foreground mt-1">总反馈</p></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="text-2xl font-bold text-green-600">{stats?.likes ?? 0}</div><p className="text-xs text-muted-foreground mt-1">有帮助</p></CardContent></Card>
        <Card><CardContent className="pt-6"><div className="text-2xl font-bold text-destructive">{stats?.dislikes ?? 0}</div><p className="text-xs text-muted-foreground mt-1">没帮助</p></CardContent></Card>
      </div>

      <div className="flex gap-2">
        {[{ v: '', l: '全部' }, { v: 'like', l: '有帮助' }, { v: 'dislike', l: '没帮助' }].map(o => (
          <Button key={o.v} size="sm" variant={rating === o.v ? 'default' : 'outline'} onClick={() => { setLoading(true); setRating(o.v) }}>
            {o.l}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无反馈</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">评价</TableHead>
                  <TableHead>建议</TableHead>
                  <TableHead>会话</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(r => (
                  <TableRow key={r.id}>
                    <TableCell>
                      {r.rating === 'like'
                        ? <Badge className="gap-1"><ThumbsUp className="h-3 w-3" />有帮助</Badge>
                        : <Badge variant="destructive" className="gap-1"><ThumbsDown className="h-3 w-3" />没帮助</Badge>}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.suggestion || '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground font-mono">{r.thread_id?.slice(0, 12) || '—'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">{new Date(r.created_at).toLocaleString('zh-CN')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
