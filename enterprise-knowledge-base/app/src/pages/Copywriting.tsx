import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Flame, RefreshCw, Loader2, Sparkles, Wand2, ExternalLink, Plus, Trash2,
  Upload, Link2, PenLine, FileText, Save, CheckCircle2, Copy, Video, Library, X, Download,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import {
  getCopyHotTopics, createManualHot, deleteManualHot, clearManualHot,
  recommendCopyTitles, uploadMaterials, importLink, generateScript,
  getScripts, updateScript, deleteScript, exportScript,
  type CopyHotTopicsResponse, type TitleRecommendItem, type MaterialEntry, type ScriptItem,
} from '@/api/copywriting'
import { StoryboardEditor } from '@/components/StoryboardEditor'

const SOURCES = ['douyin', 'manual'] as const

function CoverThumb({ src, url, size = 'md' }: { src?: string; url?: string; size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-12 w-16' : 'h-16 w-24'
  const inner = (
    <div className={`${cls} rounded-md overflow-hidden bg-muted border shrink-0 flex items-center justify-center relative group`}>
      {src ? (
        <img src={src} alt="封面" className="w-full h-full object-cover" loading="lazy" />
      ) : (
        <Video className="h-5 w-5 text-muted-foreground/40" />
      )}
      {url && (
        <span className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
          <ExternalLink className="h-4 w-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
        </span>
      )}
    </div>
  )
  if (!url) return inner
  return (
    <a href={url} target="_blank" rel="noreferrer" title="打开抖音查看（需登录）">
      {inner}
    </a>
  )
}

export function Copywriting() {
  const [tab, setTab] = useState<'hot' | 'material'>('hot')

  // ===== 热点 =====
  const [hot, setHot] = useState<CopyHotTopicsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activeSource, setActiveSource] = useState<string>('douyin')
  const [manualTitle, setManualTitle] = useState('')
  const [manualUrl, setManualUrl] = useState('')
  const [addingManual, setAddingManual] = useState(false)

  // ===== 文案标题推荐 =====
  const [recommending, setRecommending] = useState(false)
  const [titles, setTitles] = useState<TitleRecommendItem[]>([])

  // ===== 素材 =====
  const [materialFiles, setMaterialFiles] = useState<File[]>([])
  const [materialEntries, setMaterialEntries] = useState<MaterialEntry[]>([])
  const [uploading, setUploading] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [linkContent, setLinkContent] = useState('')
  const [linkImporting, setLinkImporting] = useState(false)
  const [materialTitle, setMaterialTitle] = useState('')
  const [aiRequirement, setAiRequirement] = useState('')

  // ===== 脚本 =====
  const [script, setScript] = useState<ScriptItem | null>(null)
  const [scriptList, setScriptList] = useState<ScriptItem[]>([])
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exportFormat, setExportFormat] = useState<'md' | 'txt' | 'html' | 'docx' | 'pdf'>('md')
  const editorRef = useRef<HTMLDivElement>(null)

  const loadHot = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    try {
      const res = await getCopyHotTopics(refresh)
      setHot(res)
      if (refresh) toast.success('热榜已刷新')
    } catch {
      toast.error('热榜加载失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { loadHot() }, [loadHot])

  const loadScripts = useCallback(async () => {
    try {
      const res = await getScripts({ page_size: 50 })
      setScriptList(res.items || [])
    } catch {
      // 忽略历史加载失败
    }
  }, [])

  useEffect(() => { loadScripts() }, [loadScripts])

  // 脚本生成/打开后自动滚动到编辑器
  useEffect(() => {
    if (script) {
      requestAnimationFrame(() => {
        editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }
  }, [script])

  // ===== 手动热榜 =====
  const handleAddManual = async () => {
    if (!manualTitle.trim()) { toast.error('请输入热点标题'); return }
    setAddingManual(true)
    try {
      await createManualHot({ title: manualTitle.trim(), url: manualUrl.trim() || undefined, source: 'chanmama' })
      setManualTitle('')
      setManualUrl('')
      toast.success('已加入手动热榜')
      loadHot(true)
    } catch {
      toast.error('添加失败')
    } finally {
      setAddingManual(false)
    }
  }

  const handleDelManual = async (id: number) => {
    try {
      await deleteManualHot(id)
      toast.success('已删除')
      loadHot(true)
    } catch {
      toast.error('删除失败')
    }
  }

  const handleClearManual = async () => {
    try {
      const res = await clearManualHot()
      toast.success(`已清空 ${res.deleted} 条`)
      loadHot(true)
    } catch {
      toast.error('清空失败')
    }
  }

  // ===== 文案标题推荐 =====
  const handleRecommend = async () => {
    setRecommending(true)
    setTitles([])
    try {
      const res = await recommendCopyTitles(10, true)
      setTitles(res.recommendations)
      if (res.recommendations.length === 0) toast.info('暂无可结合的选题，可稍后重试')
      else toast.success(`已生成 ${res.recommendations.length} 个文案标题`)
    } catch {
      toast.error('标题推荐失败')
    } finally {
      setRecommending(false)
    }
  }

  // ===== 素材 =====
  const handleUploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    const list = Array.from(files)
    try {
      const res = await uploadMaterials(list)
      setMaterialEntries(prev => [...prev, ...res.entries])
      setMaterialFiles([])
      toast.success(`已上传 ${res.entries.length} 份素材`)
    } catch {
      toast.error('上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleImportLink = async () => {
    if (!linkUrl.trim()) { toast.error('请输入链接'); return }
    setLinkImporting(true)
    try {
      const res = await importLink(linkUrl.trim())
      setLinkContent(res.content)
      toast.success(`已抓取 ${res.content_length} 字内容`)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '链接抓取失败'
      toast.error(msg)
    } finally {
      setLinkImporting(false)
    }
  }

  // ===== 生成脚本 =====
  const buildScript = async (params: {
    title: string
    hot_word?: string
    hot_url?: string
    requirement?: string
    material_entries?: MaterialEntry[]
    material_notes?: string
  }) => {
    if (!params.title.trim()) { toast.error('请填写文案标题'); return }
    setGenerating(true)
    try {
      const res = await generateScript({
        title: params.title.trim(),
        hot_word: params.hot_word,
        hot_url: params.hot_url,
        requirement: params.requirement?.trim() || undefined,
        material_entries: params.material_entries,
        material_notes: params.material_notes,
      })
      setScript(res)
      loadScripts()
      toast.success('脚本已生成')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '脚本生成失败'
      toast.error(msg)
    } finally {
      setGenerating(false)
    }
  }

  const handleTitleToScript = (rec: TitleRecommendItem) => {
    buildScript({ title: rec.title, hot_word: rec.hot_word, hot_url: rec.hot_url })
  }

  const handleMaterialGenerate = () => {
    buildScript({
      title: materialTitle,
      requirement: aiRequirement,
      material_entries: materialEntries.length > 0 ? materialEntries : undefined,
    })
  }

  const handleRegenerate = () => {
    if (!script) return
    buildScript({
      title: script.title,
      hot_word: script.hot_word || undefined,
      hot_url: script.hot_url || undefined,
      requirement: script.requirement || undefined,
      material_notes: script.material_notes || undefined,
    })
  }

  // ===== 脚本编辑 =====
  const handleSaveScript = async () => {
    if (!script) return
    setSaving(true)
    try {
      const updated = await updateScript(script.id, {
        title: script.title,
        hot_word: script.hot_word || undefined,
        hot_url: script.hot_url || undefined,
        voiceover: script.voiceover,
        storyboard: script.storyboard || undefined,
        requirement: script.requirement || undefined,
      })
      setScript(updated)
      loadScripts()
      toast.success('脚本已保存')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteScript = async (id: number) => {
    try {
      await deleteScript(id)
      if (script?.id === id) setScript(null)
      loadScripts()
      toast.success('已删除')
    } catch {
      toast.error('删除失败')
    }
  }

  const handleCopy = () => {
    if (!script) return
    navigator.clipboard.writeText(`${script.title}\n\n【口播稿】\n${script.voiceover}\n\n【分镜头脚本】\n${script.storyboard || ''}`)
    toast.success('已复制脚本')
  }

  const handleExport = async () => {
    if (!script) return
    try {
      const blob = await exportScript(script.id, exportFormat)
      const ext = exportFormat === 'docx' ? 'docx' : exportFormat === 'html' ? 'html' : exportFormat === 'txt' ? 'txt' : exportFormat === 'pdf' ? 'pdf' : 'md'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${script.title}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`已导出为 ${ext.toUpperCase()}`)
    } catch {
      toast.error('导出失败')
    }
  }

  // ===== 渲染 =====

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Video className="h-6 w-6 text-primary" />
            短视频文案
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            结合今日热点（抖音热搜 + 手动热榜）与知识库生成文案标题和短视频脚本
          </p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'hot' | 'material')}>
        <TabsList className="w-full justify-start gap-1">
          <TabsTrigger value="hot" className="gap-1.5">
            <Flame className="h-4 w-4" />
            热点选题
          </TabsTrigger>
          <TabsTrigger value="material" className="gap-1.5">
            <Library className="h-4 w-4" />
            素材导入
          </TabsTrigger>
        </TabsList>

        {/* ============ Tab 1: 热点选题 ============ */}
        <TabsContent value="hot" className="space-y-6 mt-4">
          {/* 热榜 */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Flame className="h-4 w-4 text-orange-500" />
                  今日热点
                </CardTitle>
                <Button variant="outline" size="sm" onClick={() => loadHot(true)} disabled={refreshing}>
                  {refreshing ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                  刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex gap-1.5 mb-3">
                {SOURCES.map(s => (
                  <Button
                    key={s}
                    variant={activeSource === s ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setActiveSource(s)}
                  >
                    {hot?.sources[s]?.label ?? (s === 'douyin' ? '抖音热搜' : '手动热榜')}
                    {hot?.sources[s]?.items && <Badge variant="secondary" className="ml-1 text-[10px]">{hot.sources[s].items.length}</Badge>}
                  </Button>
                ))}
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin mr-2" /> 加载热榜...
                </div>
              ) : (
                <div className="space-y-1 max-h-[360px] overflow-y-auto">
                  {(hot?.sources[activeSource]?.items || []).map((item, i) => (
                    <div key={`${activeSource}-${i}`} className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-muted/50">
                      <span className={`w-6 text-center text-sm font-semibold shrink-0 ${i < 3 ? 'text-orange-500' : 'text-muted-foreground'}`}>
                        {item.rank || i + 1}
                      </span>
                      <CoverThumb src={item.cover} url={item.url} size="sm" />
                      <span className="text-sm flex-1 truncate">{item.title}</span>
                      {item.source && <Badge variant="secondary" className="text-[10px] shrink-0">{item.source}</Badge>}
                      {activeSource === 'manual' && item.id && (
                        <button onClick={() => handleDelManual(item.id!)} className="text-destructive shrink-0">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  ))}
                  {!loading && (hot?.sources[activeSource]?.items || []).length === 0 && (
                    <div className="text-center py-6 text-sm text-muted-foreground">
                      {activeSource === 'manual' ? '暂无手动热榜，可粘贴馋妈妈/抖音标题+链接加入' : '抖音热搜暂不可用'}
                    </div>
                  )}
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1">
                <ExternalLink className="h-3 w-3" /> 点击封面/链接会打开抖音，观看视频需登录抖音账号
              </p>

              {activeSource === 'manual' && (
                <div className="mt-3 pt-3 border-t space-y-2">
                  <div className="flex gap-2">
                    <Input placeholder="热点标题" value={manualTitle} onChange={e => setManualTitle(e.target.value)} className="flex-1" />
                    <Input placeholder="视频链接(可选)" value={manualUrl} onChange={e => setManualUrl(e.target.value)} className="flex-1" />
                    <Button onClick={handleAddManual} disabled={addingManual}>
                      {addingManual ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                      添加
                    </Button>
                  </div>
                  <Button variant="ghost" size="sm" className="text-destructive" onClick={handleClearManual}>
                    <Trash2 className="mr-1 h-3.5 w-3.5" /> 清空手动热榜
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 文案标题推荐 */}
          <Card className="border-primary/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Wand2 className="h-4 w-4 text-primary" />
                生成今天要拍的文案标题
              </CardTitle>
              <CardDescription>AI 结合今日热点（含视频链接）与知识库，推荐可拍摄的短视频文案标题</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button onClick={handleRecommend} disabled={recommending} size="lg" className="w-full">
                {recommending
                  ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 正在分析热点与知识库…（约 10-30 秒）</>
                  : <><Sparkles className="mr-2 h-4 w-4" />生成文案标题</>}
              </Button>

              {titles.length > 0 && (
                <div className="space-y-3">
                  {titles.map((rec, i) => (
                    <div key={i} className="rounded-xl border p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <Badge variant="secondary" className="shrink-0">#{i + 1}</Badge>
                          <span className="text-sm font-medium">{rec.hot_word || '热点'}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <CoverThumb src={rec.cover} url={rec.hot_url || undefined} size="sm" />
                          <Button size="sm" onClick={() => handleTitleToScript(rec)}>
                            <PenLine className="mr-1 h-3.5 w-3.5" /> 生成脚本
                          </Button>
                        </div>
                      </div>
                      <p className="text-base font-medium">{rec.title}</p>
                      {rec.reason && <p className="text-xs text-muted-foreground">切入理由：{rec.reason}</p>}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ============ Tab 2: 素材导入 ============ */}
        <TabsContent value="material" className="space-y-6 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Library className="h-4 w-4 text-primary" />
                素材导入
              </CardTitle>
              <CardDescription>上传照片/文字/视频，或导入链接，AI 将结合素材与知识库生成视频脚本</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>文件上传（照片 / 文字 / 视频）</Label>
                <div className="flex items-center gap-2">
                  <label className="flex-1 border-2 border-dashed rounded-lg flex flex-col items-center justify-center py-6 cursor-pointer hover:border-primary/50 transition-colors">
                    <Upload className="h-8 w-8 text-muted-foreground mb-1" />
                    <span className="text-sm text-muted-foreground">{uploading ? '上传中...' : '点击选择文件（可多选）'}</span>
                    <input
                      type="file"
                      multiple
                      className="hidden"
                      accept="image/*,video/*,.txt,.md,.csv,.markdown"
                      onChange={e => handleUploadFiles(e.target.files)}
                    />
                  </label>
                </div>
                {materialFiles.length > 0 && <p className="text-xs text-muted-foreground">已选 {materialFiles.length} 个文件</p>}
              </div>

              <div className="space-y-2">
                <Label>链接导入</Label>
                <div className="flex gap-2">
                  <Input placeholder="https://...(网页/视频页链接)" value={linkUrl} onChange={e => setLinkUrl(e.target.value)} className="flex-1" />
                  <Button variant="outline" onClick={handleImportLink} disabled={linkImporting}>
                    {linkImporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                    抓取
                  </Button>
                </div>
                {linkContent && (
                  <div className="rounded-lg bg-muted/50 p-3 text-sm max-h-40 overflow-y-auto">
                    <p className="text-xs text-muted-foreground mb-1">已抓取 {linkContent.length} 字（将作为素材供 AI 参考）：</p>
                    {linkContent.slice(0, 500)}
                    {linkContent.length > 500 && '…'}
                  </div>
                )}
              </div>

              {materialEntries.length > 0 && (
                <div className="space-y-2">
                  <Label>已上传素材</Label>
                  <div className="space-y-1.5">
                    {materialEntries.map((e, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm p-2 rounded bg-muted/50">
                        <Badge variant="secondary" className="text-[10px] shrink-0 mt-0.5">
                          {e.type === 'photo' ? '照片' : e.type === 'video' ? '视频' : e.type === 'text' ? '文字' : '其他'}
                        </Badge>
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">{e.filename}</p>
                          <p className="text-xs text-muted-foreground line-clamp-2">{e.description}</p>
                        </div>
                        <button
                          onClick={() => setMaterialEntries(prev => prev.filter((_, j) => j !== i))}
                          className="text-muted-foreground hover:text-destructive shrink-0"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="space-y-2 border-t pt-4">
                <Label>文案标题</Label>
                <Input placeholder="例如：地下室防潮 90% 的人不知道的电渗透技术" value={materialTitle} onChange={e => setMaterialTitle(e.target.value)} />
              </div>

              <div className="space-y-2">
                <Label>对 AI 的要求</Label>
                <Textarea
                  placeholder="例如：做成 30 秒竖屏口播视频，开头用钩子，突出产品卖点，语气接地气…"
                  value={aiRequirement}
                  onChange={e => setAiRequirement(e.target.value)}
                  className="min-h-[80px]"
                />
              </div>

              <Button onClick={handleMaterialGenerate} disabled={generating || !materialTitle.trim()} size="lg" className="w-full">
                {generating
                  ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 正在结合素材与知识库生成脚本…</>
                  : <><Wand2 className="mr-2 h-4 w-4" />生成视频脚本</>}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ============ 脚本编辑器 ============ */}
      {script && (
        <div ref={editorRef} className="scroll-mt-6">
          <Card className="border-primary/40">
            <CardHeader className="border-b">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <FileText className="h-5 w-5 text-primary shrink-0" />
                  <Input
                    value={script.title}
                    onChange={e => setScript(prev => prev ? { ...prev, title: e.target.value } : prev)}
                    className="h-8 flex-1 min-w-[200px] font-medium"
                  />
                </div>
                <div className="flex items-center gap-1.5">
                  <Button variant="outline" size="sm" onClick={handleCopy}>
                    <Copy className="mr-1 h-3.5 w-3.5" /> 复制
                  </Button>
                  <div className="flex items-center gap-1">
                    <select
                      value={exportFormat}
                      onChange={e => setExportFormat(e.target.value as 'md' | 'txt' | 'html' | 'docx' | 'pdf')}
                      className="h-8 rounded-md border bg-background px-2 text-xs"
                      title="导出格式"
                    >
                      <option value="pdf">PDF</option>
                      <option value="md">Markdown</option>
                      <option value="txt">TXT</option>
                      <option value="html">HTML</option>
                      <option value="docx">Word</option>
                    </select>
                    <Button variant="outline" size="sm" onClick={handleExport}>
                      <Download className="mr-1 h-3.5 w-3.5" /> 导出
                    </Button>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleRegenerate} disabled={generating}>
                    {generating ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Wand2 className="mr-1 h-3.5 w-3.5" />}
                    重新生成
                  </Button>
                  <Button size="sm" onClick={handleSaveScript} disabled={saving}>
                    {saving ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1 h-3.5 w-3.5" />}
                    保存
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setScript(null)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              {(script.hot_word || script.hot_url) && (
                <div className="flex items-center gap-2 mt-2">
                  {script.hot_word && <Badge variant="secondary">{script.hot_word}</Badge>}
                  {script.hot_url && (
                    <a href={script.hot_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1">
                      <ExternalLink className="h-3 w-3" /> 查看原视频（需登录抖音）
                    </a>
                  )}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-5 pt-5">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label>口播稿</Label>
                  <span className="text-xs text-muted-foreground">{script.voiceover.length} 字</span>
                </div>
                <Textarea
                  value={script.voiceover}
                  onChange={e => setScript(prev => prev ? { ...prev, voiceover: e.target.value } : prev)}
                  className="min-h-[180px]"
                />
              </div>

              <div className="space-y-1.5">
                <Label>分镜头脚本（可逐格编辑，时长单位为秒）</Label>
                <StoryboardEditor
                  value={script.storyboard || ''}
                  onChange={text => setScript(prev => prev ? { ...prev, storyboard: text } : prev)}
                />
              </div>

              {(script.requirement || script.material_notes) && (
                <details className="rounded-lg border bg-muted/30 p-3 text-sm">
                  <summary className="cursor-pointer text-xs text-muted-foreground font-medium">查看 AI 要求与素材摘要</summary>
                  <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                    {script.requirement && <p><span className="font-medium text-foreground/70">AI 要求：</span>{script.requirement}</p>}
                    {script.material_notes && (
                      <div className="max-h-40 overflow-y-auto whitespace-pre-wrap"><span className="font-medium text-foreground/70">素材摘要：</span>{script.material_notes}</div>
                    )}
                  </div>
                </details>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ============ 脚本记录 ============ */}
      {scriptList.length > 0 && (
        <Card>
          <details className="group">
            <summary className="cursor-pointer list-none">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  脚本记录（{scriptList.length}）
                </CardTitle>
              </CardHeader>
            </summary>
            <CardContent className="pt-0">
              <div className="space-y-2">
                {scriptList.slice(0, 50).map(s => (
                  <div key={s.id} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-sm truncate">{s.title}</span>
                      {s.hot_word && <Badge variant="outline" className="text-[10px] shrink-0">{s.hot_word}</Badge>}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setScript(s)}>
                        编辑
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 text-xs text-destructive" onClick={() => handleDeleteScript(s.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </details>
        </Card>
      )}
    </div>
  )
}
