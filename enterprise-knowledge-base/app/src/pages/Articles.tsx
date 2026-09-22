import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileText, Search, Plus, Trash2, Loader2,
  CheckCircle2, Clock, Sparkles, AlertCircle, ChevronRight,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { Checkbox } from '@/components/ui/checkbox'
import { getBatches, deleteBatch, bulkDeleteBatches, getAccountTypeLabel, type BatchItem } from '@/api/articles'

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: typeof CheckCircle2 }> = {
  draft: { label: '草稿', variant: 'secondary', icon: Clock },
  generating: { label: '生成中', variant: 'outline', icon: Sparkles },
  completed: { label: '已完成', variant: 'default', icon: CheckCircle2 },
  failed: { label: '失败', variant: 'destructive', icon: AlertCircle },
}

export function Articles() {
  const navigate = useNavigate()
  const [batches, setBatches] = useState<BatchItem[]>([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<number[]>([])
  const [showBulkDelete, setShowBulkDelete] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const toggleSelect = (id: number) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const handleBulkDelete = async () => {
    setBulkDeleting(true)
    try {
      const res = await bulkDeleteBatches(selected)
      if (res.failed.length > 0) {
        toast.warning(`已删除 ${res.deleted} 个批次，${res.failed.length} 个失败`)
      } else {
        toast.success(`已删除 ${res.deleted} 个批次`)
      }
      setSelected([])
      setShowBulkDelete(false)
      load()
    } catch {
      toast.error('批量删除失败')
    } finally {
      setBulkDeleting(false)
    }
  }

  const load = async () => {
    setLoading(true)
    try {
      const res = await getBatches({ page_size: 100, page: 1 })
      setBatches(res.items)
    } catch {
      toast.error('加载批次列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    let result = batches
    if (statusFilter !== 'all') {
      result = result.filter(b => b.status === statusFilter)
    }
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(b => b.topic.toLowerCase().includes(q))
    }
    return result
  }, [batches, search, statusFilter])

  const filteredIds = filtered.map(b => b.id)
  const allSelected = filteredIds.length > 0 && filteredIds.every(id => selected.includes(id))
  const someSelected = selected.length > 0 && !allSelected

  const toggleAll = () => {
    setSelected(allSelected ? [] : filteredIds)
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteBatch(deleteId)
      toast.success(`批次已删除`)
      load()
    } catch {
      toast.error('删除失败')
    }
    setDeleteId(null)
  }

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-muted rounded-lg" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">文章管理</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理所有批量生成的文章批次，点击进入查看文章
          </p>
        </div>
        <Button onClick={() => navigate('/batch-generate')}>
          <Plus className="mr-2 h-4 w-4" />
          创建新批次
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索批次主题..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="h-10 rounded-md border bg-background px-3 py-2 text-sm"
        >
          <option value="all">全部状态</option>
          <option value="draft">草稿</option>
          <option value="generating">生成中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
          <Checkbox
            checked={allSelected ? true : someSelected ? 'indeterminate' : false}
            onCheckedChange={toggleAll}
            aria-label="全选"
          />
          全选
        </label>
        <Badge variant="secondary" className="ml-auto">
          {filtered.length} 个批次
        </Badge>
      </div>

      {selected.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-2">
          <span className="text-sm">已选 {selected.length} 个批次</span>
          <Button variant="destructive" size="sm" onClick={() => setShowBulkDelete(true)}>
            <Trash2 className="mr-1 h-4 w-4" />
            批量删除
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelected([])}>
            取消选择
          </Button>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-sm text-muted-foreground mb-4">
                {batches.length === 0 ? '暂无批次，去创建第一个吧' : '未找到匹配的批次'}
              </p>
              {batches.length === 0 && (
                <Button onClick={() => navigate('/batch-generate')}>
                  <Plus className="mr-2 h-4 w-4" />
                  创建批次
                </Button>
              )}
            </div>
          ) : (
            <div className="divide-y">
              {filtered.map(batch => {
                const status = statusConfig[batch.status] || statusConfig.draft
                return (
                  <div
                    key={batch.id}
                    className="flex items-center justify-between p-4 hover:bg-muted/50 cursor-pointer transition-colors"
                    onClick={() => navigate(`/batch/${batch.id}/publish`)}
                  >
                    <div
                      className="flex items-center shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Checkbox
                        checked={selected.includes(batch.id)}
                        onCheckedChange={() => toggleSelect(batch.id)}
                        aria-label={`选择批次 ${batch.topic}`}
                      />
                    </div>
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <status.icon className={`h-5 w-5 shrink-0 ${
                        batch.status === 'completed' ? 'text-green-500' :
                        batch.status === 'generating' ? 'text-blue-500 animate-pulse' :
                        batch.status === 'failed' ? 'text-red-500' :
                        'text-muted-foreground'
                      }`} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium truncate">{batch.topic}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {batch.generated_count}/{batch.article_count} 篇 ·
                          创建于 {new Date(batch.created_at).toLocaleDateString('zh-CN')}
                          {batch.account_type && ` · ${getAccountTypeLabel(batch.account_type)}`}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={status.variant}>{status.label}</Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/batch/${batch.id}/publish`)
                        }}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteId(batch.id)
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              此操作将永久删除该批次及其所有文章，无法恢复。确定继续吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showBulkDelete} onOpenChange={setShowBulkDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认批量删除</AlertDialogTitle>
            <AlertDialogDescription>
              将永久删除 {selected.length} 个批次及其所有文章，无法恢复。确定继续吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {bulkDeleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
