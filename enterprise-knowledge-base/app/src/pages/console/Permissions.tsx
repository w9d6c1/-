import { useEffect, useState } from 'react'
import { Plus, Trash2, Loader2, RefreshCw, Wand2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { toast } from 'sonner'
import {
  fetchPermissions, createPermission, updatePermission, deletePermission,
  createDefaults, reloadCache, type ScopePermission,
} from '@/api/permissions'

const ROLES = ['superadmin', 'dept_admin', 'operator', 'readonly']
const SCOPES = ['public', 'internal', 'customer']

export function Permissions() {
  const [rows, setRows] = useState<ScopePermission[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [role, setRole] = useState('operator')
  const [scope, setScope] = useState('public')
  const [saving, setSaving] = useState(false)

  const [reloadKey, setReloadKey] = useState(0)
  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  useEffect(() => {
    let active = true
    fetchPermissions()
      .then(r => { if (active) setRows(r) })
      .catch(() => toast.error('加载权限失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reloadKey])

  const handleAdd = async () => {
    setSaving(true)
    try {
      await createPermission({ role, scope, is_active: true })
      toast.success('已创建')
      setShowAdd(false); reload()
    } catch { toast.error('创建失败') } finally { setSaving(false) }
  }

  const toggle = async (p: ScopePermission) => {
    try { await updatePermission(p.id, { is_active: !p.is_active }); reload() } catch { toast.error('更新失败') }
  }

  const handleDelete = async (id: number) => {
    try { await deletePermission(id); reload() } catch { toast.error('删除失败') }
  }

  const handleDefaults = async () => {
    try { const r = await createDefaults(); toast.success(`已创建 ${r.created} 条默认权限`); reload() } catch { toast.error('操作失败') }
  }

  const handleReload = async () => {
    try { await reloadCache(); toast.success('缓存已刷新') } catch { toast.error('刷新失败') }
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">权限管理</h1>
          <p className="text-sm text-muted-foreground mt-1">角色可见的知识范围（scope）</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleDefaults}><Wand2 className="mr-2 h-4 w-4" />创建默认</Button>
          <Button variant="outline" onClick={handleReload}><RefreshCw className="mr-2 h-4 w-4" />刷新缓存</Button>
          <Button onClick={() => setShowAdd(true)}><Plus className="mr-2 h-4 w-4" />新增</Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无权限配置</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>角色</TableHead>
                  <TableHead>范围</TableHead>
                  <TableHead>启用</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(p => (
                  <TableRow key={p.id}>
                    <TableCell><Badge variant="outline">{p.role}</Badge></TableCell>
                    <TableCell><Badge variant="secondary">{p.scope}</Badge></TableCell>
                    <TableCell><Switch checked={p.is_active} onCheckedChange={() => toggle(p)} /></TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDelete(p.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增权限</DialogTitle>
            <DialogDescription>为角色分配可访问的知识范围</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>角色</Label>
              <select value={role} onChange={e => setRole(e.target.value)} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label>范围</Label>
              <select value={scope} onChange={e => setScope(e.target.value)} className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                {SCOPES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>取消</Button>
            <Button onClick={handleAdd} disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
