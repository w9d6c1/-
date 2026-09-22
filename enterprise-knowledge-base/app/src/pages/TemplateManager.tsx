import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Edit3, Loader2, FileText, Layers } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
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
import {
  getTemplates, createTemplate, updateTemplate, deleteTemplate,
  type TemplateItem,
} from '@/api/articles'

export function TemplateManager() {
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [loading, setLoading] = useState(true)

  const [showEdit, setShowEdit] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editType, setEditType] = useState('structure')
  const [editInstruction, setEditInstruction] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getTemplates()
      setTemplates(data)
    } catch {
      toast.error('加载模板列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = () => {
    setEditId(null)
    setEditName('')
    setEditType('structure')
    setEditInstruction('')
    setShowEdit(true)
  }

  const handleEdit = (t: TemplateItem) => {
    setEditId(t.id)
    setEditName(t.name)
    setEditType(t.type)
    setEditInstruction(t.prompt_instruction)
    setShowEdit(true)
  }

  const handleSave = async () => {
    if (!editName.trim() || !editInstruction.trim()) {
      toast.error('模板名称和指令不能为空')
      return
    }
    setSaving(true)
    try {
      if (editId) {
        await updateTemplate(editId, { name: editName, prompt_instruction: editInstruction })
        toast.success('模板已更新')
      } else {
        await createTemplate({ name: editName, type: editType, prompt_instruction: editInstruction })
        toast.success('模板已创建')
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
      await deleteTemplate(deleteId)
      toast.success('模板已删除')
      setDeleteId(null)
      load()
    } catch {
      toast.error('删除失败')
    }
  }

  const structures = templates.filter(t => t.type === 'structure')
  const styles = templates.filter(t => t.type === 'style')

  if (loading) {
    return (
      <div className="p-6 space-y-6 max-w-5xl mx-auto animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-muted rounded-lg" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">模板管理</h1>
          <p className="text-sm text-muted-foreground mt-1">
            管理写作模板，系统预设 + 自定义模板
          </p>
        </div>
        <Button onClick={handleAdd}>
          <Plus className="mr-2 h-4 w-4" />
          新建模板
        </Button>
      </div>

      {/* 结构模板 */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">结构模板（控制文章骨架）</h2>
          <Badge variant="secondary">{structures.length}</Badge>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {structures.map(t => (
            <Card
              key={t.id}
              className="group hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => handleEdit(t)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    {t.name}
                    {t.is_preset ? (
                      <Badge variant="secondary" className="text-xs">系统</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">自定义</Badge>
                    )}
                  </CardTitle>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); handleEdit(t) }}>
                      <Edit3 className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); setDeleteId(t.id) }}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed line-clamp-4">
                  {t.prompt_instruction}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* 风格模板 */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">风格模板（控制文章口吻）</h2>
          <Badge variant="secondary">{styles.length}</Badge>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {styles.map(t => (
            <Card
              key={t.id}
              className="group hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => handleEdit(t)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    {t.name}
                    {t.is_preset ? (
                      <Badge variant="secondary" className="text-xs">系统</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">自定义</Badge>
                    )}
                  </CardTitle>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); handleEdit(t) }}>
                      <Edit3 className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); setDeleteId(t.id) }}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed line-clamp-4">
                  {t.prompt_instruction}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Edit Dialog */}
      <Dialog open={showEdit} onOpenChange={setShowEdit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editId ? '编辑模板' : '新建模板'}</DialogTitle>
            <DialogDescription>模板指令将直接拼接在 LLM 的写作 prompt 中</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>模板名称</Label>
              <Input value={editName} onChange={e => setEditName(e.target.value)} placeholder="如：问题解决型" />
            </div>
            {!editId && (
              <div className="space-y-2">
                <Label>类型</Label>
                <select value={editType} onChange={e => setEditType(e.target.value)}
                  className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                  <option value="structure">结构模板</option>
                  <option value="style">风格模板</option>
                </select>
              </div>
            )}
            <div className="space-y-2">
              <Label>模板指令</Label>
              <Textarea
                value={editInstruction}
                onChange={e => setEditInstruction(e.target.value)}
                placeholder="输入 AI 写作指令，如：&#10;1. 开头：描述用户痛点&#10;2. 分析：剖析问题原因&#10;3. 方案：给出具体步骤..."
                className="min-h-[150px]"
              />
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

      {/* Delete Confirm */}
      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>删除后不可恢复，确定要删除该模板吗？</AlertDialogDescription>
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
