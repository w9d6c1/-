import { useEffect, useState } from 'react'
import { Loader2, RefreshCw, Trash2, Eye, Link2, GitMerge, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import {
  fetchSourceContents, fetchSourceContentDetail, updateSourceContentStatus, deleteSourceContent,
  mergeSourceContents, triggerSync, fetchPreviewUrl, fetchSyncStates, fetchSyncLogs,
  type SourceContent, type SourceContentDetail, type SyncState, type SyncLog,
} from '@/api/sourceContent'

const PAGE_SIZE = 20
const SOURCE_TYPES = ['', 'wechat', 'toutiao', 'zhihu', 'bilibili', 'official_website', 'internal']

export function SourceContents() {
  const [rows, setRows] = useState<SourceContent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [filters, setFilters] = useState<{ source_type: string; status: string; search: string }>({ source_type: '', status: '', search: '' })
  const [draft, setDraft] = useState({ search: '' })

  const [detail, setDetail] = useState<SourceContentDetail | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [mergePrimary, setMergePrimary] = useState('')
  const [mergeDup, setMergeDup] = useState('')

  const [states, setStates] = useState<SyncState[]>([])
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    let active = true
    fetchSourceContents({ ...filters, page, page_size: PAGE_SIZE })
      .then(res => { if (active) { setRows(res.items); setTotal(res.total) } })
      .catch(() => toast.error('加载失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [filters, page, reloadKey])

  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  const loadSync = async () => {
    try {
      const [s, l] = await Promise.all([fetchSyncStates(), fetchSyncLogs({ page: 1, page_size: 20 })])
      setStates(s); setLogs(l.items)
    } catch { /* ignore */ }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await triggerSync()
      toast.success(`同步完成：抓取 ${res.total_fetched}，入库 ${res.total_ingested}${res.all_ok ? '' : '（部分平台失败）'}`)
      reload(); loadSync()
    } catch {
      toast.error('同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const openDetail = async (id: number) => {
    try { setDetail(await fetchSourceContentDetail(id)) } catch { toast.error('加载详情失败') }
  }

  const toggleStatus = async (r: SourceContent) => {
    try { await updateSourceContentStatus(r.id, r.status === 'online' ? 'offline' : 'online'); reload() } catch { toast.error('操作失败') }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try { await deleteSourceContent(deleteId); toast.success('已删除'); setDeleteId(null); reload() } catch { toast.error('删除失败') }
  }

  const handlePreview = async (id: number) => {
    try { const url = await fetchPreviewUrl(id); window.open(url, '_blank', 'noopener') } catch { toast.error('无可用预览链接') }
  }

  const handleMerge = async () => {
    const p = Number(mergePrimary); const d = Number(mergeDup)
    if (!p || !d || p === d) { toast.error('请填写两个不同的文档 ID'); return }
    try {
      await mergeSourceContents(p, d)
      toast.success('合并成功')
      setMergeOpen(false); setMergePrimary(''); setMergeDup(''); reload()
    } catch { toast.error('合并失败') }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">多源内容</h1>
          <p className="text-sm text-muted-foreground mt-1">公众号 / 头条 / 知乎 / B站 / 官网采集内容管理</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setMergeOpen(true)}><GitMerge className="mr-2 h-4 w-4" />合并</Button>
          <Button onClick={handleSync} disabled={syncing}>
            {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            立即同步
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">来源</label>
          <select value={filters.source_type} onChange={e => { setLoading(true); setPage(1); setFilters(f => ({ ...f, source_type: e.target.value })) }} className="h-9 rounded-md border bg-background px-3 text-sm">
            {SOURCE_TYPES.map(t => <option key={t} value={t}>{t || '全部'}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">状态</label>
          <select value={filters.status} onChange={e => { setLoading(true); setPage(1); setFilters(f => ({ ...f, status: e.target.value })) }} className="h-9 rounded-md border bg-background px-3 text-sm">
            <option value="">全部</option>
            <option value="online">上线</option>
            <option value="offline">下线</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">搜索</label>
          <Input value={draft.search} onChange={e => setDraft({ search: e.target.value })} onKeyDown={e => { if (e.key === 'Enter') { setLoading(true); setPage(1); setFilters(f => ({ ...f, search: draft.search })) } }} className="w-48" placeholder="标题关键字" />
        </div>
        <Badge variant="secondary">{total} 条</Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无内容</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>标题</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>切片</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(r => (
                  <TableRow key={r.id}>
                    <TableCell className="max-w-sm">
                      <div className="text-sm font-medium truncate">{r.title}</div>
                      <div className="text-xs text-muted-foreground truncate">{r.source_name || r.source_type}{r.publish_time ? ` · ${r.publish_time.slice(0, 10)}` : ''}</div>
                    </TableCell>
                    <TableCell><Badge variant="outline">{r.source_type}</Badge></TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.chunk_count}</TableCell>
                    <TableCell>
                      <button onClick={() => toggleStatus(r)}>
                        <Badge variant={r.status === 'online' ? 'default' : 'secondary'}>{r.status === 'online' ? '上线' : '下线'}</Badge>
                      </button>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="详情" onClick={() => openDetail(r.id)}><Eye className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="预览原文" onClick={() => handlePreview(r.id)}><Link2 className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDeleteId(r.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {total > PAGE_SIZE && (
        <div className="flex justify-center items-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => { setLoading(true); setPage(p => p - 1) }}>上一页</Button>
          <span className="text-sm text-muted-foreground">第 {page} / {totalPages} 页</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => { setLoading(true); setPage(p => p + 1) }}>下一页</Button>
        </div>
      )}

      <Tabs defaultValue="states">
        <TabsList>
          <TabsTrigger value="states">同步状态</TabsTrigger>
          <TabsTrigger value="logs">同步日志</TabsTrigger>
        </TabsList>
        <TabsContent value="states" className="mt-4">
          <Button variant="outline" size="sm" onClick={loadSync} className="mb-3"><RefreshCw className="mr-1 h-3 w-3" />加载</Button>
          {states.length === 0 ? <p className="text-sm text-muted-foreground">点击「加载」查看各平台同步状态</p> : (
            <Table>
              <TableHeader><TableRow><TableHead>平台</TableHead><TableHead>最近同步</TableHead><TableHead>状态</TableHead><TableHead>错误</TableHead></TableRow></TableHeader>
              <TableBody>
                {states.map(s => (
                  <TableRow key={s.platform}>
                    <TableCell className="text-sm">{s.platform}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{s.last_sync_at || '—'}</TableCell>
                    <TableCell><Badge variant={s.last_status === 'ok' ? 'default' : 'secondary'}>{s.last_status}</Badge></TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-xs truncate">{s.last_error || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>
        <TabsContent value="logs" className="mt-4">
          <Button variant="outline" size="sm" onClick={loadSync} className="mb-3"><Download className="mr-1 h-3 w-3" />加载</Button>
          {logs.length === 0 ? <p className="text-sm text-muted-foreground">点击「加载」查看同步日志</p> : (
            <Table>
              <TableHeader><TableRow><TableHead>平台</TableHead><TableHead>开始</TableHead><TableHead>抓取</TableHead><TableHead>入库</TableHead><TableHead>状态</TableHead></TableRow></TableHeader>
              <TableBody>
                {logs.map(l => (
                  <TableRow key={l.id}>
                    <TableCell className="text-sm">{l.platform}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{l.started_at}</TableCell>
                    <TableCell className="text-sm">{l.fetched_count}</TableCell>
                    <TableCell className="text-sm">{l.ingested_count}</TableCell>
                    <TableCell><Badge variant={l.status === 'ok' ? 'default' : 'secondary'}>{l.status}</Badge></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={!!detail} onOpenChange={open => !open && setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{detail?.title}</DialogTitle>
            <DialogDescription>{detail?.source_name || detail?.source_type} · {detail?.word_count} 字 · {detail?.chunk_count} 切片</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm font-medium">来源链接</div>
            {(detail?.source_links || []).length === 0 ? <p className="text-sm text-muted-foreground">无</p> : detail?.source_links.map(l => (
              <div key={l.id} className="text-sm flex items-center gap-2">
                <Badge variant="outline">{l.platform}</Badge>
                {l.original_url
                  ? <a href={l.original_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate">{l.original_url}</a>
                  : <span className="text-muted-foreground">—</span>}
                {l.is_primary && <Badge variant="secondary">主</Badge>}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>合并重复内容</DialogTitle>
            <DialogDescription>将重复文档合并到主文档，重复文档将被删除</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2"><Label>主文档 ID</Label><Input value={mergePrimary} onChange={e => setMergePrimary(e.target.value)} /></div>
            <div className="space-y-2"><Label>重复文档 ID</Label><Input value={mergeDup} onChange={e => setMergeDup(e.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMergeOpen(false)}>取消</Button>
            <Button onClick={handleMerge}>合并</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteId !== null} onOpenChange={open => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>确认删除</AlertDialogTitle><AlertDialogDescription>删除后将从数据库与检索引擎移除，确定继续吗？</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
