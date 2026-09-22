import { useState, useEffect, useCallback, useRef } from 'react'
import {
  BookOpen, Plus, Trash2, Search, FileText, Upload,
  X, RefreshCw, Layers, Loader2, Sparkles, ChevronRight,
  AlertCircle, CheckCircle2,
} from 'lucide-react'
import {
  Card, CardHeader, CardTitle, CardContent,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
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
  getDocuments, getDocument, getDocumentChunks, uploadDocument,
  deleteDocument, resyncDocument, getCategories, getDepartments,
  createDocumentByContent,
  type DocumentItem, type DocumentDetail, type ChunkItem, type CategoryItem,
} from '@/api/documents'
import { useAuth } from '@/stores/auth'

export function KnowledgeBase() {
  const { user } = useAuth()
  const canManage = user?.role === 'superadmin' || user?.role === 'dept_admin' || user?.role === 'operator'

  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [viewDoc, setViewDoc] = useState<DocumentDetail | null>(null)
  const [viewChunks, setViewChunks] = useState<ChunkItem[]>([])
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [categories, setCategories] = useState<CategoryItem[]>([])
  const [, setDepartments] = useState<string[]>([])

  const [pasteTitle, setPasteTitle] = useState('')
  const [pasteContent, setPasteContent] = useState('')
  const [pasteScope, setPasteScope] = useState('public')
  const [pasteCategoryId, setPasteCategoryId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDocs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getDocuments({ page, page_size: 20 })
      setDocs(res.items)
      setTotal(res.total)
    } catch {
      toast.error('加载文档列表失败')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { loadDocs() }, [loadDocs])

  useEffect(() => {
    getCategories().then(setCategories).catch(() => {})
    getDepartments().then(setDepartments).catch(() => {})
  }, [])

  const handleViewDoc = useCallback(async (doc: DocumentItem) => {
    try {
      const [detail, chunks] = await Promise.all([
        getDocument(doc.id),
        getDocumentChunks(doc.id),
      ])
      setViewDoc(detail)
      setViewChunks(chunks)
    } catch {
      toast.error('加载文档详情失败')
    }
  }, [])

  const handlePasteAdd = async () => {
    if (!pasteTitle.trim() || !pasteContent.trim()) {
      toast.error('标题和内容不能为空')
      return
    }
    setSaving(true)
    try {
      await createDocumentByContent({
        title: pasteTitle,
        content: pasteContent,
        file_type: 'txt',
        category_id: pasteCategoryId || 0,
        scope: pasteScope,
      })
      toast.success(`已添加「${pasteTitle}」`)
      setShowAdd(false)
      setPasteTitle('')
      setPasteContent('')
      setPasteScope('public')
      setPasteCategoryId(null)
      loadDocs()
    } catch {
      toast.error('添加文档失败')
    } finally {
      setSaving(false)
    }
  }

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    setUploadError('')
    try {
      await uploadDocument(file, {
        title: file.name.replace(/\.[^.]+$/, ''),
        category_id: pasteCategoryId || 0,
        scope: pasteScope,
      })
      toast.success(`已上传「${file.name}」`)
      setShowAdd(false)
      loadDocs()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '上传失败'
      setUploadError(msg)
      toast.error(msg)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleResync = async (id: number) => {
    try {
      const result = await resyncDocument(id)
      toast.success(`已同步 ${result.synced} 个分块到检索引擎`)
    } catch {
      toast.error('同步失败')
    }
  }

  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await deleteDocument(deleteId)
      toast.success('文档已删除')
      setDeleteId(null)
      if (viewDoc?.id === deleteId) setViewDoc(null)
      loadDocs()
    } catch {
      toast.error('删除失败')
    }
  }

  const vectoredCount = docs.filter(d => d.chunk_count > 0).length

  if (loading && docs.length === 0) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <div key={i} className="h-40 bg-muted rounded-xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">知识库管理</h1>
          <p className="text-sm text-muted-foreground mt-1">
            支持 PDF/Word/MD/TXT 上传，自动分块 → 向量化 → 混合检索
          </p>
        </div>
        {canManage && (
          <Button onClick={() => { setShowAdd(true); setUploadError('') }}>
            <Plus className="mr-2 h-4 w-4" />
            添加文档
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="搜索文档标题..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Badge variant={vectoredCount === total ? 'default' : 'secondary'} className="gap-1.5">
          <Sparkles className="h-3 w-3" />
          {vectoredCount}/{total} 已向量化
        </Badge>
        <Badge variant="secondary">{total} 篇</Badge>
      </div>

      {docs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <BookOpen className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-sm text-muted-foreground mb-4">
              {search ? '未找到匹配的文档' : '知识库为空，开始添加文档吧'}
            </p>
            {!search && canManage && (
              <Button onClick={() => { setShowAdd(true); setUploadError('') }}>
                <Upload className="mr-2 h-4 w-4" />上传文件
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.filter(d => !search || d.title.toLowerCase().includes(search.toLowerCase())).map(doc => (
              <Card
                key={doc.id}
                className="group hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => handleViewDoc(doc)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <CardTitle className="text-sm font-medium truncate">{doc.title}</CardTitle>
                    </div>
                    {canManage && (
                      <Button
                        variant="ghost" size="icon"
                        className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                        onClick={(e) => { e.stopPropagation(); setDeleteId(doc.id) }}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><FileText className="h-3 w-3" />{doc.word_count} 字</span>
                    <span className="flex items-center gap-1"><Layers className="h-3 w-3" />{doc.chunk_count} 块</span>
                    <span className="flex items-center gap-1">
                      {doc.chunk_count > 0 ? (
                        <><CheckCircle2 className="h-3 w-3 text-green-500" />已向量化</>
                      ) : (
                        <><AlertCircle className="h-3 w-3 text-orange-500" />待处理</>
                      )}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline" className="text-xs">{doc.scope}</Badge>
                    {doc.file_type && <Badge variant="outline" className="text-xs">{doc.file_type}</Badge>}
                    <Badge variant={doc.status === 'online' ? 'default' : 'secondary'} className="text-xs">
                      {doc.status}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">
                      {new Date(doc.created_at).toLocaleDateString('zh-CN')}
                    </span>
                    <Button variant="ghost" size="sm" className="h-6 text-xs gap-1 opacity-0 group-hover:opacity-100">
                      查看详情 <ChevronRight className="h-3 w-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {total > 20 && (
            <div className="flex justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                上一页
              </Button>
              <span className="flex items-center text-sm text-muted-foreground">
                第 {page} / {Math.ceil(total / 20)} 页
              </span>
              <Button variant="outline" size="sm" disabled={page >= Math.ceil(total / 20)} onClick={() => setPage(p => p + 1)}>
                下一页
              </Button>
            </div>
          )}
        </>
      )}

      {/* Add Dialog */}
      <Dialog open={showAdd} onOpenChange={(open) => { setShowAdd(open); if (!open) setUploadError('') }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>添加知识库文档</DialogTitle>
            <DialogDescription>上传文件或粘贴文本，后端自动解析、分块、向量化</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label className="mb-2 block">上传文件</Label>
              <label className="block cursor-pointer">
                <div className="rounded-lg border-2 border-dashed p-6 text-center hover:border-primary/50 hover:bg-accent/30 transition-colors">
                  {uploading ? (
                    <>
                      <Loader2 className="h-8 w-8 mx-auto mb-2 animate-spin text-primary" />
                      <p className="text-sm">正在上传和解析...</p>
                    </>
                  ) : (
                    <>
                      <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                      <p className="text-sm font-medium">点击选择文件</p>
                      <p className="text-xs text-muted-foreground mt-1">支持 PDF / DOCX / MD / TXT</p>
                    </>
                  )}
                </div>
                <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.md,.txt" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f) }}
                  disabled={uploading} />
              </label>
              {uploadError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 mt-2">
                  <p className="text-sm text-red-700 flex items-center gap-1.5">
                    <AlertCircle className="h-4 w-4 shrink-0" />{uploadError}
                  </p>
                </div>
              )}
            </div>

            <div className="flex gap-4">
              <div className="flex-1 space-y-2">
                <Label>范围</Label>
                <select value={pasteScope} onChange={e => setPasteScope(e.target.value)}
                  className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                  <option value="public">公开</option>
                  <option value="internal">内部</option>
                  <option value="customer">客户</option>
                </select>
              </div>
              <div className="flex-1 space-y-2">
                <Label>分类</Label>
                <select value={pasteCategoryId || ''} onChange={e => setPasteCategoryId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm">
                  <option value="">无分类</option>
                  {categories.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <Label>直接粘贴文本</Label>
              <Input placeholder="文档标题" value={pasteTitle} onChange={e => setPasteTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Textarea
                placeholder="粘贴文档内容..."
                value={pasteContent}
                onChange={e => setPasteContent(e.target.value)}
                className="min-h-[150px]"
              />
              {pasteContent && <p className="text-xs text-muted-foreground">{pasteContent.length} 字</p>}
            </div>
            <Button className="w-full" onClick={handlePasteAdd} disabled={saving}>
              {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />保存中...</> : <><Plus className="mr-2 h-4 w-4" />添加文档</>}
            </Button>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}><X className="mr-2 h-4 w-4" />关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail View Dialog */}
      <Dialog open={!!viewDoc} onOpenChange={(open) => !open && setViewDoc(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          {viewDoc && (
            <>
              <DialogHeader>
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <DialogTitle className="text-lg">{viewDoc.title}</DialogTitle>
                </div>
                <DialogDescription>
                  {viewDoc.word_count} 字 · {viewDoc.chunk_count} 个分块 ·
                  {viewDoc.chunk_count > 0 ? ' 已向量化' : ' 待分块'}
                  {viewDoc.department && ` · ${viewDoc.department}`}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">{viewDoc.scope}</Badge>
                  <Badge variant="outline">{viewDoc.file_type || 'text'}</Badge>
                  <Badge variant={viewDoc.status === 'online' ? 'default' : 'secondary'}>{viewDoc.status}</Badge>
                  <Badge variant={viewDoc.review_status === 'approved' ? 'default' : viewDoc.review_status === 'rejected' ? 'destructive' : 'outline'}>
                    {viewDoc.review_status}
                  </Badge>
                </div>

                <Card>
                  <CardHeader className="py-3 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm">分块列表</CardTitle>
                    {canManage && (
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleResync(viewDoc.id)}>
                        <RefreshCw className="h-3 w-3 mr-1" />重新同步
                      </Button>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-1 max-h-[300px] overflow-y-auto">
                    {viewChunks.length === 0 ? (
                      <p className="text-xs text-muted-foreground py-4 text-center">暂无分块数据</p>
                    ) : (
                      viewChunks.map((chunk, i) => (
                        <div key={chunk.id} className="flex items-start gap-2 rounded p-2 hover:bg-accent/50 text-xs">
                          <Badge variant="outline" className="shrink-0 h-5 w-5 flex items-center justify-center p-0 text-xs">{i + 1}</Badge>
                          <span className="flex-1 min-w-0 leading-relaxed">
                            {chunk.content.slice(0, 150)}{chunk.content.length > 150 ? '...' : ''}
                          </span>
                          {chunk.vector_id ? (
                            <Badge variant="default" className="shrink-0 text-xs">已向量</Badge>
                          ) : (
                            <Badge variant="secondary" className="shrink-0 text-xs">未同步</Badge>
                          )}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>

                {viewDoc.plain_text && (
                  <Card>
                    <CardHeader className="py-3">
                      <CardTitle className="text-sm">原文预览</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="text-xs whitespace-pre-wrap font-sans leading-relaxed text-muted-foreground max-h-[250px] overflow-y-auto">
                        {viewDoc.plain_text.slice(0, 5000)}{(viewDoc.plain_text.length > 5000) ? '...' : ''}
                      </pre>
                    </CardContent>
                  </Card>
                )}
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setViewDoc(null)}>关闭</Button>
                {canManage && (
                  <Button variant="destructive" onClick={() => setDeleteId(viewDoc.id)}>
                    <Trash2 className="mr-2 h-4 w-4" />删除文档
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              删除后将从数据库和检索引擎中移除，不可恢复。确定要删除吗？
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
    </div>
  )
}
