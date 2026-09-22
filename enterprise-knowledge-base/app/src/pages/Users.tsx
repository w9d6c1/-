import { useState, useEffect, useCallback } from 'react'
import {
  Users as UsersIcon, Plus, Trash2, Shield, UserCheck, UserCog, UserIcon,
  Edit3, Loader2,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { Checkbox } from '@/components/ui/checkbox'
import { getUsers, deleteUser, updateUser, createUser, bulkDeleteUsers, type UserItem } from '@/api/users'
import { useAuth } from '@/stores/auth'

const roleConfig: Record<string, { label: string; icon: typeof Shield; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  superadmin: { label: '超级管理员', icon: Shield, variant: 'default' },
  dept_admin: { label: '部门管理员', icon: UserCog, variant: 'secondary' },
  operator: { label: '操作员', icon: UserCheck, variant: 'outline' },
  readonly: { label: '只读用户', icon: UserIcon, variant: 'secondary' },
}

export function Users() {
  const { user: currentUser } = useAuth()
  const isAdmin = currentUser?.role === 'superadmin'

  const [users, setUsers] = useState<UserItem[]>([])
  const [loading, setLoading] = useState(true)

  const [showEdit, setShowEdit] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editRole, setEditRole] = useState('readonly')
  const [editDept, setEditDept] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [showBulkDelete, setShowBulkDelete] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const selectableIds = users.filter(u => u.id !== currentUser?.id).map(u => u.id)
  const allSelected = selectableIds.length > 0 && selectableIds.every(id => selected.includes(id))
  const someSelected = selected.length > 0 && !allSelected
  const selectedSuperadmins = users.filter(u => selected.includes(u.id) && u.role === 'superadmin')
  const deletableCount = selected.length - selectedSuperadmins.length

  const toggleSelect = (id: number) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const toggleAll = () => {
    setSelected(allSelected ? [] : selectableIds)
  }

  const handleBulkDelete = async () => {
    setBulkDeleting(true)
    try {
      const res = await bulkDeleteUsers(selected)
      if (res.failed.length > 0) {
        toast.warning(`已禁用 ${res.deleted} 个用户，${res.failed.length} 个失败`)
      } else {
        toast.success(`已禁用 ${res.deleted} 个用户`)
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

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getUsers({ page_size: 100, page: 1 })
      setUsers(res.items)
    } catch {
      toast.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = () => {
    setEditId(null)
    setEditName('')
    setEditEmail('')
    setEditRole('readonly')
    setEditDept('')
    setEditPassword('')
    setShowEdit(true)
  }

  const handleEdit = (u: UserItem) => {
    setEditId(u.id)
    setEditName(u.display_name || '')
    setEditEmail(u.email || '')
    setEditRole(u.role)
    setEditDept(u.department || '')
    setEditPassword('')
    setShowEdit(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (editId) {
        await updateUser(editId, {
          display_name: editName,
          role: editRole,
          department: editDept,
        })
        toast.success('用户已更新')
      } else {
        await createUser({
          username: editName,
          password: editPassword || 'default123456',
          password_confirm: editPassword || 'default123456',
          display_name: editName,
          email: editEmail,
          role: editRole,
          department: editDept,
        })
        toast.success('用户已创建')
      }
      setShowEdit(false)
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '保存失败'
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteUser(deleteId)
      toast.success('用户已删除')
      setDeleteId(null)
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '删除失败'
      toast.error(msg)
    }
  }

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-5xl mx-auto animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-muted rounded-lg" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">用户管理</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理企业知识库系统的用户和角色权限
          </p>
        </div>
        {isAdmin && (
          <Button onClick={handleAdd}>
            <Plus className="mr-2 h-4 w-4" />
            添加用户
          </Button>
        )}
      </div>

      {isAdmin && selected.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-2">
          <span className="text-sm">已选 {selected.length} 个用户</span>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setShowBulkDelete(true)}
          >
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
          {users.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <UsersIcon className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-sm text-muted-foreground">暂无用户数据</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {isAdmin && (
                    <TableHead className="w-10">
                      <Checkbox
                        checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                        onCheckedChange={toggleAll}
                        aria-label="全选"
                      />
                    </TableHead>
                  )}
                  <TableHead>用户</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>部门</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map(u => {
                  const role = roleConfig[u.role] || { label: u.role, icon: UserIcon, variant: 'secondary' as const }
                  return (
                    <TableRow key={u.id}>
                      {isAdmin && (
                        <TableCell>
                          {u.id !== currentUser?.id && (
                            <Checkbox
                              checked={selected.includes(u.id)}
                              onCheckedChange={() => toggleSelect(u.id)}
                              aria-label={`选择 ${u.display_name || u.username}`}
                            />
                          )}
                        </TableCell>
                      )}
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                            {(u.display_name || u.username).charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="text-sm font-medium flex items-center gap-1.5">
                              {u.display_name || u.username}
                              {u.id === currentUser?.id && (
                                <Badge variant="outline" className="text-xs py-0">当前</Badge>
                              )}
                            </div>
                            <div className="text-xs text-muted-foreground">{u.email || u.phone || u.username}</div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={role.variant} className="gap-1">
                          <role.icon className="h-3 w-3" />
                          {role.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {u.department || '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={u.is_active ? 'default' : 'destructive'}>
                          {u.is_active ? '启用' : '禁用'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(u.created_at).toLocaleDateString('zh-CN')}
                      </TableCell>
                      <TableCell className="text-right">
                        {isAdmin && (
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleEdit(u)}>
                              <Edit3 className="h-4 w-4" />
                            </Button>
                            {u.id !== currentUser?.id && (
                              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDeleteId(u.id)}>
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            )}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editId ? '编辑用户' : '添加用户'}</DialogTitle>
            <DialogDescription>修改用户信息和角色权限</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>用户名 / 显示名称</Label>
              <Input value={editName} onChange={e => setEditName(e.target.value)} />
            </div>
            {!editId && (
              <>
                <div className="space-y-2">
                  <Label>邮箱</Label>
                  <Input value={editEmail} onChange={e => setEditEmail(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>密码</Label>
                  <Input type="password" value={editPassword} onChange={e => setEditPassword(e.target.value)} placeholder="留空则使用默认密码" />
                </div>
              </>
            )}
            <div className="space-y-2">
              <Label>角色</Label>
              <select value={editRole} onChange={e => setEditRole(e.target.value)}
                className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                <option value="readonly">只读用户</option>
                <option value="operator">操作员</option>
                <option value="dept_admin">部门管理员</option>
                <option value="superadmin">超级管理员</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>部门</Label>
              <Input value={editDept} onChange={e => setEditDept(e.target.value)} placeholder="部门名称" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEdit(false)}>取消</Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除后不可恢复，确定要删除该用户吗？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk Delete Dialog */}
      <AlertDialog open={showBulkDelete} onOpenChange={setShowBulkDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认批量删除</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>将禁用 {deletableCount} 个用户，禁用后无法登录系统。确定继续吗？</p>
                {selectedSuperadmins.length > 0 && (
                  <p className="text-amber-500">
                    选中包含 {selectedSuperadmins.length} 个超管账号（受保护，将自动跳过）：
                    {selectedSuperadmins.map(u => u.display_name || u.username).join('、')}
                  </p>
                )}
              </div>
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
