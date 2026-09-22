import { useEffect, useState } from 'react'
import { Plus, Trash2, Edit3, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import {
  getCategoryTree, createCategory, updateCategory, deleteCategory,
  type Category,
} from '@/api/categories'

interface FlatRow extends Category { depth: number }

function flatten(nodes: Category[], depth = 0): FlatRow[] {
  const out: FlatRow[] = []
  for (const n of nodes) {
    out.push({ ...n, depth })
    if (n.children?.length) out.push(...flatten(n.children, depth + 1))
  }
  return out
}

export function Categories() {
  const [rows, setRows] = useState<FlatRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showEdit, setShowEdit] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [scope, setScope] = useState('public')
  const [parentId, setParentId] = useState<number | ''>('')
  const [sortOrder, setSortOrder] = useState(0)
  const [saving, setSaving] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  useEffect(() => {
    let active = true
    getCategoryTree()
      .then(tree => { if (active) setRows(flatten(tree)) })
      .catch(() => toast.error('加载分类失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reloadKey])

  const openAdd = () => {
    setEditId(null); setName(''); setScope('public'); setParentId(''); setSortOrder(0); setShowEdit(true)
  }
  const openEdit = (c: FlatRow) => {
    setEditId(c.id); setName(c.name); setScope(c.scope); setParentId(c.parent_id ?? ''); setSortOrder(c.sort_order); setShowEdit(true)
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('请输入分类名称'); return }
    setSaving(true)
    try {
      if (editId) {
        await updateCategory(editId, { name, scope, parent_id: parentId === '' ? null : Number(parentId), sort_order: sortOrder })
        toast.success('分类已更新')
      } else {
        await createCategory({ name, scope, parent_id: parentId === '' ? null : Number(parentId), sort_order: sortOrder })
        toast.success('分类已创建')
      }
      setShowEdit(false)
      reload()
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const toggleStatus = async (c: FlatRow) => {
    try {
      await updateCategory(c.id, { status: c.status === 'enabled' ? 'disabled' : 'enabled' })
      reload()
    } catch {
      toast.error('状态切换失败')
    }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteCategory(deleteId)
      toast.success('分类已删除')
      setDeleteId(null)
      reload()
    } catch {
      toast.error('删除失败')
    }
  }

  const parentOptions = rows.filter(r => r.id !== editId)

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">分类管理</h1>
          <p className="text-sm text-muted-foreground mt-1">维护知识库分类树</p>
        </div>
        <Button onClick={openAdd}><Plus className="mr-2 h-4 w-4" />新建分类</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无分类</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>范围</TableHead>
                  <TableHead>排序</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(r => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <span style={{ paddingLeft: r.depth * 20 }} className="text-sm font-medium">{r.name}</span>
                    </TableCell>
                    <TableCell><Badge variant="outline">{r.scope}</Badge></TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.sort_order}</TableCell>
                    <TableCell>
                      <button onClick={() => toggleStatus(r)}>
                        <Badge variant={r.status === 'enabled' ? 'default' : 'secondary'}>{r.status === 'enabled' ? '启用' : '禁用'}</Badge>
                      </button>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(r)}><Edit3 className="h-4 w-4" /></Button>
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

      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editId ? '编辑分类' : '新建分类'}</DialogTitle>
            <DialogDescription>分类用于组织知识库文档与 FAQ</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2"><Label>名称</Label><Input value={name} onChange={e => setName(e.target.value)} /></div>
            <div className="space-y-2">
              <Label>范围</Label>
              <select value={scope} onChange={e => setScope(e.target.value)} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                <option value="public">公开</option>
                <option value="internal">内部</option>
                <option value="customer">客户</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>上级分类</Label>
              <select value={parentId} onChange={e => setParentId(e.target.value ? Number(e.target.value) : '')} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                <option value="">（无）</option>
                {parentOptions.map(p => <option key={p.id} value={p.id}>{'　'.repeat(p.depth)}{p.name}</option>)}
              </select>
            </div>
            <div className="space-y-2"><Label>排序</Label><Input type="number" value={sortOrder} onChange={e => setSortOrder(Number(e.target.value))} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEdit(false)}>取消</Button>
            <Button onClick={handleSave} disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteId !== null} onOpenChange={open => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除分类可能影响其下文档与 FAQ 的归属，确定继续吗？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
