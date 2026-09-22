import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Download, Save, Eye, Edit3,
  Calendar, FileText, Loader2, Image as ImageIcon,
} from 'lucide-react'
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import { getArticle, updateArticle, exportArticle, getPhotoUrl, type ArticleDetail as IArticleDetail } from '@/api/articles'

const angleLabels: Record<string, string> = {
  technical_detail: '技术原理解析',
  case_study: '案例实践分享',
  benefit_analysis: '优势效益分析',
  comparison: '方案对比分析',
  maintenance_guide: '选购施工指南',
}

export function ArticleDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [article, setArticle] = useState<IArticleDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editedTitle, setEditedTitle] = useState('')
  const [editedContent, setEditedContent] = useState('')

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getArticle(Number(id))
      .then((data) => {
        setArticle(data)
        setEditedTitle(data.title)
        setEditedContent(data.content)
      })
      .catch(() => toast.error('加载文章失败'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!article) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-full">
        <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <p className="text-sm text-muted-foreground mb-4">文章不存在或已被删除</p>
        <Button onClick={() => navigate('/articles')}>返回文章列表</Button>
      </div>
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await updateArticle(article.id, {
        title: editedTitle,
        content: editedContent,
      })
      setArticle(updated)
      setEditing(false)
      toast.success('文章已保存')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleExport = async (format: 'md' | 'html' | 'docx') => {
    try {
      const blob = await exportArticle(article.id, format)
      const ext = format === 'docx' ? 'docx' : format === 'html' ? 'html' : 'md'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${article.title}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`已导出为 ${format.toUpperCase()}`)
    } catch {
      toast.error('导出失败')
    }
  }

  const markdownToHtml = (md: string) => {
    const placements = article.image_placement || []
    let html = md
    let pIdx = 0
    html = html.replace(/\[IMAGE:\s*(?:照片\s*(\d+)\s*[:：])?\s*配图建议[:：]\s*(.+?)\]/gi, (_match: string, _num: string, caption: string) => {
      const cap = caption.trim()
      const placement = placements[pIdx]
      pIdx += 1
      if (placement?.object_name) {
        const imgUrl = getPhotoUrl(placement.object_name)
        return `<figure class="my-6"><img src="${imgUrl}" alt="${cap}" class="rounded-lg border w-full object-cover max-h-96" loading="lazy" /><figcaption class="text-xs text-muted-foreground mt-2 text-center">${cap}</figcaption></figure>`
      }
      return `<div class="bg-muted/50 rounded-lg p-4 my-4 text-sm text-muted-foreground">📷 配图建议：${cap}</div>`
    })
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
    html = html.replace(/`(.+?)`/g, '<code>$1</code>')
    html = html.split(/\n\n+/).map(block => {
      if (block.startsWith('<h') || block.startsWith('<figure') || block.startsWith('<div')) return block
      return `<p>${block.replace(/\n/g, '<br/>')}</p>`
    }).join('\n')
    return html
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => navigate('/articles')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回列表
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{angleLabels[article.angle] || article.angle}</Badge>
          {editing ? (
            <>
              <Button variant="outline" size="sm" onClick={() => { setEditing(false); setEditedTitle(article.title); setEditedContent(article.content) }}>
                取消
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                保存
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <Edit3 className="mr-2 h-4 w-4" />
                编辑
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Download className="mr-2 h-4 w-4" />
                    导出
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onClick={() => handleExport('md')}>Markdown (.md)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport('html')}>HTML (.html)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport('docx')}>Word (.docx)</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </div>
      </div>

      <Tabs defaultValue="content">
        <TabsList>
          <TabsTrigger value="content"><Eye className="h-4 w-4 mr-1.5" />内容</TabsTrigger>
          <TabsTrigger value="meta"><FileText className="h-4 w-4 mr-1.5" />元数据</TabsTrigger>
        </TabsList>

        <TabsContent value="content" className="space-y-4">
          <Card>
            <CardHeader>
              {editing ? (
                <Input value={editedTitle} onChange={e => setEditedTitle(e.target.value)} className="text-xl font-semibold" />
              ) : (
                <CardTitle className="text-xl">{article.title}</CardTitle>
              )}
              <CardDescription>{article.word_count} 字 · {angleLabels[article.angle] || article.angle}</CardDescription>
            </CardHeader>
            <CardContent>
              {editing ? (
                <Textarea
                  value={editedContent}
                  onChange={e => setEditedContent(e.target.value)}
                  className="min-h-[500px] font-mono text-sm"
                />
              ) : (
                <div
                  className="prose prose-sm max-w-none dark:prose-invert"
                  dangerouslySetInnerHTML={{ __html: markdownToHtml(article.content) }}
                  style={{ lineHeight: '1.8' }}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="meta" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">文章元数据</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <FileText className="h-3 w-3" /> 字数
                  </Label>
                  <p className="text-sm font-medium">{article.word_count} 字</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <FileText className="h-3 w-3" /> 内容角度
                  </Label>
                  <p className="text-sm font-medium">{angleLabels[article.angle] || article.angle}</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> 创建时间
                  </Label>
                  <p className="text-sm font-medium">{new Date(article.created_at).toLocaleString('zh-CN')}</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> 更新时间
                  </Label>
                  <p className="text-sm font-medium">{new Date(article.updated_at).toLocaleString('zh-CN')}</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <FileText className="h-3 w-3" /> 批次 ID
                  </Label>
                  <p className="text-sm font-medium">{article.batch_id}</p>
                </div>
              </div>

              {(article.image_placement && article.image_placement.length > 0) && (
                <div className="mt-6 space-y-3">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1">
                    <ImageIcon className="h-3 w-3" /> 文章配图 ({article.image_placement.length} 张)
                  </Label>
                  <div className="grid grid-cols-2 gap-3">
                    {article.image_placement.map((p, i) => (
                      <div key={i} className="rounded-lg border overflow-hidden">
                        {p.object_name ? (
                          <img
                            src={getPhotoUrl(p.object_name)}
                            alt={p.caption}
                            className="w-full h-40 object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="w-full h-40 bg-muted flex items-center justify-center">
                            <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground p-2">{p.caption}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
