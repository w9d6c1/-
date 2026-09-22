import { useEffect, useState } from 'react'
import { Plus, Trash2, Edit3, Loader2, Search, History, Check, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import {
  fetchFAQs, createFAQ, updateFAQ, deleteFAQ, batchDeleteFAQs,
  submitForReview, approveFAQ, rejectFAQ, getFAQVersions, rollbackFAQ,
  type FAQ, type FAQVersion,
} from '@/api/faq'
import { getCategoriesFlat, type Category } from '@/api/categories'

const PAGE_SIZE = 20

export function Faqs() {
  const [items, setItems] = useState<FAQ[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categories, setCategories] = useState<Category[]>([])
  const [selected, setSelected] = useState<number[]>([])

  const [showEdit, setShowEdit] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [scope, setScope] = useState('public')
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [saving, setSaving] = useState(false)

  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [showBulk, setShowBulk] = useState(false)

  const [versionsOf, setVersionsOf] = useState<FAQ | null>(null)
  const [versions, setVersions] = useState<FAQVersion[]>([])

  const [reloadKey, setReloadKey] = useState(0)
  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  useEffect(() => {
    let active = true
    fetchFAQs(page, PAGE_SIZE)
      .then(res => { if (active) { setItems(res.items); setTotal(res.total) } })
      .catch(() => toast.error('加载 FAQ 失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [page, reloadKey])

  useEffect(() => {
    let active = true
    getCategoriesFlat().then(c => { if (active) setCategories(c) }).catch(() => {})
    return () => { active = false }
  }, [])

  const openAdd = () => {
    setEditId(null); setQuestion(''); setAnswer(''); setScope('public'); setCategoryId(categories[0]?.id ?? ''); setShowEdit(true)
  }
  const openEdit = (f: FAQ) => {
    setEditId(f.id); setQuestion(f.question); setAnswer(f.answer); setScope(f.scope); setCategoryId(f.category_id); setShowEdit(true)
  }

  const handleSave = async () => {
    if (!question.trim() || !answer.trim()) { toast.error('问题与答案不能为空'); return }
    setSaving(true)
    try {
      if (editId) {
        await updateFAQ(editId, { question, answer, scope, category_id: Number(categoryId) || 0 })
        toast.success('FAQ 已更新')
      } else {
        await createFAQ({ category_id: Number(categoryId) || 0, question, answer, scope })
        toast.success('FAQ 已创建')
      }
      setShowEdit(false)
      reload()
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try { await deleteFAQ(deleteId); toast.success('已删除'); setDeleteId(null); reload() } catch { toast.error('删除失败') }
  }

  const handleBulkDelete = async () => {
    try {
      const res = await batchDeleteFAQs(selected)
      toast.success(`已删除 ${res.deleted} 条`)
      setSelected([]); setShowBulk(false); reload()
    } catch { toast.error('批量删除失败') }
  }

  const review = async (f: FAQ, action: 'submit' | 'approve' | 'reject') => {
    try {
      if (action === 'submit') await submitForReview(f.id)
      else if (action === 'approve') await approveFAQ(f.id)
      else await rejectFAQ(f.id)
      toast.success('操作成功')
      reload()
    } catch { toast.error('操作失败') }
  }

  const openVersions = async (f: FAQ) => {
    setVersionsOf(f)
    try { setVersions(await getFAQVersions(f.id)) } catch { toast.error('加载版本失败') }
  }

  const handleRollback = async (v: FAQVersion) => {
    if (!versionsOf) return
    try { await rollbackFAQ(versionsOf.id, v.id); toast.success('已回滚'); setVersionsOf(null); reload() } catch { toast.error('回滚失败') }
  }

  const filtered = items.filter(f => !search || f.question.toLowerCase().includes(search.toLowerCase()))
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const allSelected = filtered.length > 0 && filtered.every(f => selected.includes(f.id))

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">FAQ 管理</h1>
          <p className="text-sm text-muted-foreground mt-1">维护常见问题与标准答案</p>
        </div>
        <Button onClick={openAdd}><Plus className="mr-2 h-4 w-4" />新建 FAQ</Button>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="搜索问题..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Badge variant="secondary">{total} 条</Badge>
        {selected.length > 0 && (
          <>
            <span className="text-sm text-muted-foreground">已选 {selected.length}</span>
            <Button variant="destructive" size="sm" onClick={() => setShowBulk(true)}><Trash2 className="mr-1 h-4 w-4" />批量删除</Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected([])}>取消选择</Button>
          </>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无 FAQ</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox checked={allSelected} onCheckedChange={() => setSelected(allSelected ? [] : filtered.map(f => f.id))} />
                  </TableHead>
                  <TableHead>问题</TableHead>
                  <TableHead>范围</TableHead>
                  <TableHead>审核</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(f => (
                  <TableRow key={f.id}>
                    <TableCell>
                      <Checkbox checked={selected.includes(f.id)} onCheckedChange={() => setSelected(p => p.includes(f.id) ? p.filter(x => x !== f.id) : [...p, f.id])} />
                    </TableCell>
                    <TableCell className="max-w-md">
                      <div className="text-sm font-medium truncate">{f.question}</div>
                      <div className="text-xs text-muted-foreground truncate">{f.answer}</div>
                    </TableCell>
                    <TableCell><Badge variant="outline">{f.scope}</Badge></TableCell>
                    <TableCell>
                      <Badge variant={f.review_status === 'approved' ? 'default' : f.review_status === 'rejected' ? 'destructive' : 'secondary'}>
                        {f.review_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-0.5">
                        {f.review_status === 'pending' && (
                          <Button variant="ghost" size="icon" className="h-8 w-8" title="提交审核" onClick={() => review(f, 'submit')}><Check className="h-4 w-4" /></Button>
                        )}
                        {f.review_status !== 'approved' && (
                          <Button variant="ghost" size="icon" className="h-8 w-8" title="通过" onClick={() => review(f, 'approve')}><Check className="h-4 w-4 text-green-600" /></Button>
                        )}
                        {f.review_status === 'pending' && (
                          <Button variant="ghost" size="icon" className="h-8 w-8" title="驳回" onClick={() => review(f, 'reject')}><X className="h-4 w-4 text-destructive" /></Button>
                        )}
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="版本" onClick={() => openVersions(f)}><History className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(f)}><Edit3 className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDeleteId(f.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
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
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
          <span className="text-sm text-muted-foreground">第 {page} / {totalPages} 页</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</Button>
        </div>
      )}

      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{editId ? '编辑 FAQ' : '新建 FAQ'}</DialogTitle>
            <DialogDescription>FAQ 命中后会直接返回标准答案</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2"><Label>问题</Label><Input value={question} onChange={e => setQuestion(e.target.value)} /></div>
            <div className="space-y-2"><Label>答案</Label><Textarea value={answer} onChange={e => setAnswer(e.target.value)} className="min-h-[140px]" /></div>
            <div className="flex gap-4">
              <div className="flex-1 space-y-2">
                <Label>范围</Label>
                <select value={scope} onChange={e => setScope(e.target.value)} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                  <option value="public">公开</option>
                  <option value="internal">内部</option>
                  <option value="customer">客户</option>
                </select>
              </div>
              <div className="flex-1 space-y-2">
                <Label>分类</Label>
                <select value={categoryId} onChange={e => setCategoryId(e.target.value ? Number(e.target.value) : '')} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                  <option value="">无分类</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEdit(false)}>取消</Button>
            <Button onClick={handleSave} disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!versionsOf} onOpenChange={open => !open && setVersionsOf(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>版本历史</DialogTitle></DialogHeader>
          {versions.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">暂无历史版本</p>
          ) : versions.map(v => (
            <div key={v.id} className="flex items-center justify-between border-b py-2 last:border-0">
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">v{v.version} · {v.question}</div>
                <div className="text-xs text-muted-foreground truncate">{v.answer}</div>
              </div>
              <Button variant="outline" size="sm" onClick={() => handleRollback(v)}>回滚</Button>
            </div>
          ))}
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteId !== null} onOpenChange={open => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>确认删除</AlertDialogTitle><AlertDialogDescription>删除后不可恢复，确定继续吗？</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showBulk} onOpenChange={setShowBulk}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>确认批量删除</AlertDialogTitle><AlertDialogDescription>将删除 {selected.length} 条 FAQ，确定继续吗？</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
