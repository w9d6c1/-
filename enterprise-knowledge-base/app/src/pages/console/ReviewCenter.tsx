import { useEffect, useState } from 'react'
import { Loader2, RefreshCw, Eye, Check, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { getDocuments, getDocument, reviewDocument, type DocumentItem, type DocumentDetail } from '@/api/documents'
import { fetchFAQs, approveFAQ, rejectFAQ, type FAQ } from '@/api/faq'

function scopeLabel(scope: string) {
  if (scope === 'public') return '公共'
  if (scope === 'customer') return '客服'
  return '内部'
}

type PreviewKind = { type: 'doc'; data: DocumentDetail } | { type: 'faq'; data: FAQ } | null

export function ReviewCenter() {
  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [faqs, setFaqs] = useState<FAQ[]>([])
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [preview, setPreview] = useState<PreviewKind>(null)
  const [reject, setReject] = useState<{ type: 'doc' | 'faq'; id: number } | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [acting, setActing] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([
      getDocuments({ page: 1, page_size: 100 }),
      fetchFAQs(1, 500),
    ])
      .then(([d, f]) => { if (active) { setDocs(d.items); setFaqs(f.items) } })
      .catch(() => toast.error('加载审核数据失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reloadKey])

  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  const docPending = docs.filter(d => d.review_status === 'pending')
  const docReviewed = docs.filter(d => d.review_status !== 'pending' && d.review_status !== 'draft')
  const faqPending = faqs.filter(f => f.review_status === 'pending')
  const faqReviewed = faqs.filter(f => f.review_status !== 'pending' && f.review_status !== 'draft')

  const openDoc = async (id: number) => {
    try { setPreview({ type: 'doc', data: await getDocument(id) }) } catch { toast.error('加载文档失败') }
  }

  const approveDoc = async (id: number) => {
    setActing(true)
    try { await reviewDocument(id, 'approve'); toast.success('已通过'); reload() } catch { toast.error('操作失败') } finally { setActing(false) }
  }

  const confirmReject = async () => {
    if (!reject) return
    setActing(true)
    try {
      if (reject.type === 'doc') await reviewDocument(reject.id, 'reject', rejectReason || undefined)
      else await rejectFAQ(reject.id, rejectReason || undefined)
      toast.success('已驳回')
      setReject(null); setRejectReason(''); setPreview(null); reload()
    } catch { toast.error('操作失败') } finally { setActing(false) }
  }

  const approveFaq = async (id: number) => {
    setActing(true)
    try { await approveFAQ(id); toast.success('审核通过'); reload() } catch { toast.error('操作失败') } finally { setActing(false) }
  }

  if (loading) {
    return <div className="py-24 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
  }

  const docTable = (rows: DocumentItem[], reviewed: boolean) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-16">ID</TableHead>
          <TableHead>标题</TableHead>
          <TableHead className="w-20">范围</TableHead>
          <TableHead className="w-16">切片</TableHead>
          <TableHead className="w-44 text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(d => (
          <TableRow key={d.id}>
            <TableCell className="text-sm text-muted-foreground">{d.id}</TableCell>
            <TableCell className="text-sm max-w-md truncate">{d.title}</TableCell>
            <TableCell><Badge variant="outline">{scopeLabel(d.scope)}</Badge></TableCell>
            <TableCell className="text-sm text-muted-foreground">{d.chunk_count}</TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => openDoc(d.id)}><Eye className="mr-1 h-3 w-3" />查看</Button>
                {!reviewed && (
                  <>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-green-600" disabled={acting} onClick={() => approveDoc(d.id)}><Check className="mr-1 h-3 w-3" />通过</Button>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-destructive" disabled={acting} onClick={() => setReject({ type: 'doc', id: d.id })}><X className="mr-1 h-3 w-3" />驳回</Button>
                  </>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )

  const faqTable = (rows: FAQ[], reviewed: boolean) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-16">ID</TableHead>
          <TableHead>问题</TableHead>
          <TableHead className="w-20">范围</TableHead>
          <TableHead className="w-44 text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(f => (
          <TableRow key={f.id}>
            <TableCell className="text-sm text-muted-foreground">{f.id}</TableCell>
            <TableCell className="text-sm max-w-md truncate">{f.question}</TableCell>
            <TableCell><Badge variant="outline">{scopeLabel(f.scope)}</Badge></TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setPreview({ type: 'faq', data: f })}><Eye className="mr-1 h-3 w-3" />查看</Button>
                {!reviewed && (
                  <>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-green-600" disabled={acting} onClick={() => approveFaq(f.id)}><Check className="mr-1 h-3 w-3" />通过</Button>
                    <Button variant="ghost" size="sm" className="h-7 text-xs text-destructive" disabled={acting} onClick={() => setReject({ type: 'faq', id: f.id })}><X className="mr-1 h-3 w-3" />驳回</Button>
                  </>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">审核中心</h1>
          <p className="text-sm text-muted-foreground mt-1">文档与 FAQ 的审核</p>
        </div>
        <Button variant="outline" onClick={reload}><RefreshCw className="mr-2 h-4 w-4" />刷新</Button>
      </div>

      <Tabs defaultValue="docs">
        <TabsList>
          <TabsTrigger value="docs">待审核文档（{docPending.length}）</TabsTrigger>
          <TabsTrigger value="docsReviewed">已审核文档（{docReviewed.length}）</TabsTrigger>
          <TabsTrigger value="faqs">待审核 FAQ（{faqPending.length}）</TabsTrigger>
          <TabsTrigger value="faqsReviewed">已审核 FAQ（{faqReviewed.length}）</TabsTrigger>
        </TabsList>
        <TabsContent value="docs" className="mt-4"><Card><CardContent className="p-0">{docPending.length ? docTable(docPending, false) : <p className="py-12 text-center text-sm text-muted-foreground">无待审核文档</p>}</CardContent></Card></TabsContent>
        <TabsContent value="docsReviewed" className="mt-4"><Card><CardContent className="p-0">{docReviewed.length ? docTable(docReviewed, true) : <p className="py-12 text-center text-sm text-muted-foreground">暂无</p>}</CardContent></Card></TabsContent>
        <TabsContent value="faqs" className="mt-4"><Card><CardContent className="p-0">{faqPending.length ? faqTable(faqPending, false) : <p className="py-12 text-center text-sm text-muted-foreground">无待审核 FAQ</p>}</CardContent></Card></TabsContent>
        <TabsContent value="faqsReviewed" className="mt-4"><Card><CardContent className="p-0">{faqReviewed.length ? faqTable(faqReviewed, true) : <p className="py-12 text-center text-sm text-muted-foreground">暂无</p>}</CardContent></Card></TabsContent>
      </Tabs>

      <Dialog open={!!preview} onOpenChange={open => !open && setPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{preview?.type === 'doc' ? preview.data.title : preview?.type === 'faq' ? 'FAQ 详情' : ''}</DialogTitle>
            <DialogDescription>{preview?.type === 'doc' ? `${preview.data.word_count} 字` : ''}</DialogDescription>
          </DialogHeader>
          {preview?.type === 'faq' && (
            <div className="space-y-3 text-sm">
              <div><div className="font-medium mb-1">问题</div><div>{preview.data.question}</div></div>
              <div><div className="font-medium mb-1">答案</div><div className="whitespace-pre-wrap bg-muted/40 rounded p-3">{preview.data.answer}</div></div>
            </div>
          )}
          {preview?.type === 'doc' && (
            <div className="text-sm whitespace-pre-wrap bg-muted/40 rounded p-3 max-h-[50vh] overflow-y-auto">
              {preview.data.plain_text?.slice(0, 5000) || '（无文本内容）'}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreview(null)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reject} onOpenChange={open => { if (!open) { setReject(null); setRejectReason('') } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>驳回</DialogTitle>
            <DialogDescription>请输入驳回原因（选填）</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>驳回原因</Label>
            <Textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} className="min-h-[100px]" placeholder="驳回原因..." />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setReject(null); setRejectReason('') }}>取消</Button>
            <Button variant="destructive" onClick={confirmReject} disabled={acting}>
              {acting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}确认驳回
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
