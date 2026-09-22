import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Trash2, Sparkles, CalendarClock,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { getBatches, deleteBatch, getAccountTypeLabel, type BatchItem } from '@/api/articles'

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  draft: { label: '草稿', variant: 'secondary' },
  generating: { label: '生成中', variant: 'outline' },
  completed: { label: '已完成', variant: 'default' },
  failed: { label: '失败', variant: 'destructive' },
}

export function Schedule() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<BatchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await getBatches({ page_size: 100, page: 1 })
      setTasks(res.items)
    } catch {
      toast.error('加载任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteBatch(deleteId)
      toast.success('任务已删除')
      setDeleteId(null)
      load()
    } catch {
      toast.error('删除失败')
    }
  }

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-40 bg-muted rounded-xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">定时任务</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理所有文章生成批次，创建新批次进行批量生成
          </p>
        </div>
        <Button onClick={() => navigate('/batch-generate')}>
          <Plus className="mr-2 h-4 w-4" />
          创建新批次
        </Button>
      </div>

      {tasks.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <CalendarClock className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-sm text-muted-foreground mb-4">暂无批次任务</p>
            <Button onClick={() => navigate('/batch-generate')}>
              <Sparkles className="mr-2 h-4 w-4" />
              创建第一个批次
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tasks.map(task => {
            const status = statusConfig[task.status] || statusConfig.draft
            const progressPct = task.article_count > 0 ? Math.round((task.generated_count / task.article_count) * 100) : 0
            return (
              <Card
                key={task.id}
                className="group hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => navigate(`/batch/${task.id}/publish`)}
              >
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{task.topic}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {task.generated_count}/{task.article_count} 篇
                      </div>
                    </div>
                    <Button
                      variant="ghost" size="icon"
                      className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                      onClick={(e) => { e.stopPropagation(); setDeleteId(task.id) }}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>

                  <Progress value={progressPct} className="h-1.5" />

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Badge variant={status.variant}>{status.label}</Badge>
                      {task.account_type && (
                        <Badge variant="secondary" className="text-xs">
                          {getAccountTypeLabel(task.account_type)}
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {new Date(task.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>此操作将永久删除该批次，无法恢复。确定继续吗？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
