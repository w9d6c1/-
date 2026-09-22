import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Upload, X, Loader2, Search, Tag, Image, Trash2,
  RefreshCw, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import {
  getPhotos, uploadPhoto, updatePhoto, deletePhoto, suggestTags,
  fetchPhotoBlob, type PhotoItem,
} from '@/api/photos'

const MAX_BATCH_UPLOAD = 20

function PhotoImg({ objectName, alt, className }: { objectName: string; alt: string; className?: string }) {
  const [src, setSrc] = useState<string>('')
  useEffect(() => {
    let cancelled = false
    fetchPhotoBlob(objectName).then(url => { if (!cancelled) setSrc(url) }).catch(() => {})
    return () => { cancelled = true; if (src) URL.revokeObjectURL(src) }
  }, [objectName])
  if (!src) return <div className={`bg-muted animate-pulse ${className}`} />
  return <img src={src} alt={alt} className={className} />
}

export function PhotoLibrary() {
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [tagFilter, setTagFilter] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0 })
  const [editingTags, setEditingTags] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [previewPhoto, setPreviewPhoto] = useState<PhotoItem | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pageSize = 16

  const loadPhotos = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const res = await getPhotos({ page: p, page_size: pageSize, tag: tagFilter || undefined })
      setPhotos(res.items)
      setTotal(res.total)
    } catch {
      setPhotos([])
    }
    setLoading(false)
  }, [tagFilter])

  useEffect(() => {
    loadPhotos(page)
  }, [page, loadPhotos])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const fileArray = Array.from(files)

    if (fileArray.length > MAX_BATCH_UPLOAD) {
      toast.error(`一次最多上传 ${MAX_BATCH_UPLOAD} 张照片，当前选择了 ${fileArray.length} 张`)
      return
    }

    setUploading(true)
    setUploadProgress({ current: 0, total: fileArray.length })

    let success = 0
    let untagged = 0
    let failed = 0

    for (let i = 0; i < fileArray.length; i++) {
      setUploadProgress({ current: i + 1, total: fileArray.length })
      try {
        const result = await uploadPhoto(fileArray[i])
        success++
        if (!result.tags || result.tags.length === 0) untagged++
      } catch {
        failed++
        toast.error(`${fileArray[i].name} 上传失败`)
      }
    }

    setUploading(false)
    setPage(1)
    await loadPhotos(1)

    if (success > 0) {
      let msg = `上传完成：${success} 张成功${failed > 0 ? `，${failed} 张失败` : ''}`
      if (untagged > 0) {
        msg += `，其中 ${untagged} 张 AI 打标失败，可在"编辑"里点 AI 重新打标或手动添加`
      }
      toast.success(msg)
    } else {
      toast.error('所有照片上传均失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除这张照片？将从 MinIO 和数据库中永久移除。')) return
    try {
      await deletePhoto(id)
      toast.success('照片已删除')
      await loadPhotos(page)
    } catch {
      toast.error('删除失败')
    }
  }

  const handleSaveTags = async (photoId: number) => {
    const tags = editText.split(/[,，\s]+/).filter(Boolean)
    if (tags.length === 0) {
      toast.error('请输入至少一个标签')
      return
    }
    try {
      await updatePhoto(photoId, tags)
      setPhotos(prev => prev.map(p => p.id === photoId ? { ...p, tags } : p))
      setEditingTags(null)
      toast.success('标签已保存')
    } catch {
      toast.error('保存失败')
    }
  }

  const handleSuggestTags = async (photoId: number) => {
    try {
      const { tags } = await suggestTags(photoId)
      toast.success(`AI 建议 ${tags.length} 个标签`)
      setEditText(tags.join(', '))
    } catch {
      toast.error('AI 分析失败')
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">照片库</h1>
          <p className="text-sm text-muted-foreground mt-1">
            上传照片后 AI 自动打标签，创作文章时智能匹配配图
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="按标签搜索..."
                className="pl-9"
                value={tagFilter}
                onChange={e => { setTagFilter(e.target.value); setPage(1) }}
              />
            </div>
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="gap-2"
              >
                {uploading ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />
                  上传中 ({uploadProgress.current}/{uploadProgress.total})</>
                ) : (
                  <><Upload className="h-4 w-4" />上传照片</>
                )}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic"
                multiple
                className="hidden"
                onChange={e => handleUpload(e.target.files)}
              />
            <span className="text-sm text-muted-foreground">
              共 {total} 张照片
            </span>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : photos.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center py-16 space-y-3">
            <Image className="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p className="text-muted-foreground">
              {tagFilter ? '没有匹配标签的照片' : '还没有上传照片'}
            </p>
            <p className="text-xs text-muted-foreground">
              点击"上传照片"，AI 将自动分析并生成标签
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {photos.map(photo => (
              <Card key={photo.id} className="overflow-hidden group">
                <div
                  className="relative aspect-square cursor-pointer bg-muted"
                  onClick={() => setPreviewPhoto(photo)}
                >
                  <PhotoImg
                    objectName={photo.object_name}
                    alt={photo.filename}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                </div>
                <CardContent className="p-3 space-y-2">
                  <p className="text-xs font-medium truncate" title={photo.filename}>
                    {photo.filename}
                  </p>

                  {editingTags === photo.id ? (
                    <div className="space-y-1.5">
                      <Input
                        className="h-7 text-xs"
                        value={editText}
                        onChange={e => setEditText(e.target.value)}
                        placeholder="标签1, 标签2, 标签3"
                        onKeyDown={e => e.key === 'Enter' && handleSaveTags(photo.id)}
                      />
                      <div className="flex gap-1">
                        <Button size="sm" className="h-6 text-xs px-2" onClick={() => handleSaveTags(photo.id)}>
                          保存
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 text-xs px-2" onClick={() => handleSuggestTags(photo.id)}>
                          <RefreshCw className="h-3 w-3 mr-0.5" />AI
                        </Button>
                        <Button size="sm" variant="ghost" className="h-6 text-xs px-1" onClick={() => setEditingTags(null)}>
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1 min-h-[24px]">
                      {photo.tags && photo.tags.length > 0 ? (
                        photo.tags.slice(0, 4).map((tag, i) => (
                          <Badge key={i} variant="secondary" className="text-xs px-1.5 py-0">
                            {tag}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">无标签</span>
                      )}
                    </div>
                  )}

                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-xs px-2"
                      onClick={() => {
                        setEditingTags(photo.id)
                        setEditText(photo.tags?.join(', ') || '')
                      }}
                    >
                      <Tag className="h-3 w-3 mr-0.5" />编辑标签
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-xs px-2 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(photo.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-4">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}

      {previewPhoto && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-8"
          onClick={() => setPreviewPhoto(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-background rounded-xl overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            <button
              className="absolute top-3 right-3 z-10 w-8 h-8 bg-black/50 text-white rounded-full flex items-center justify-center hover:bg-black/70"
              onClick={() => setPreviewPhoto(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <PhotoImg
              objectName={previewPhoto.object_name}
              alt={previewPhoto.filename}
              className="max-w-full max-h-[80vh] object-contain"
            />
            <div className="p-4 space-y-2">
              <p className="text-sm font-medium">{previewPhoto.filename}</p>
              {previewPhoto.description && (
                <p className="text-xs text-muted-foreground">{previewPhoto.description}</p>
              )}
              <div className="flex flex-wrap gap-1">
                {previewPhoto.tags?.map((tag, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">{tag}</Badge>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
