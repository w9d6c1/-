import { useState, useEffect, useCallback } from 'react'
import { Check, RefreshCw, Search, Image, Loader2, AlertCircle, Library, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { matchPhotos, matchPhotosWeighted, selectPhotos, getPhotos, getPhotoUrl, type PhotoItem } from '@/api/photos'

interface MatchPhoto extends PhotoItem {
  confidence?: number
  reason?: string
}

interface PhotoMatcherProps {
  topic: string
  count: number
  batchId?: number | null
  templateInstruction?: string
  onConfirm?: (photoIds: number[]) => void
}

function PhotoThumb({ photo, selected, onToggle, confidence }: {
  photo: PhotoItem
  selected: boolean
  onToggle: () => void
  confidence?: number
}) {
  const [src, setSrc] = useState<string>('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const url = getPhotoUrl(photo.object_name)
    const token = localStorage.getItem('token')
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.blob()
      })
      .then(blob => {
        if (!cancelled) setSrc(URL.createObjectURL(blob))
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => { cancelled = true; if (src) URL.revokeObjectURL(src) }
  }, [photo.object_name])

  return (
    <div
      onClick={onToggle}
      className={`relative border-2 rounded-lg overflow-hidden cursor-pointer transition-all ${
        selected ? 'border-primary shadow-md ring-2 ring-primary/30' : 'border-border hover:border-primary/50'
      }`}
    >
      {src ? (
        <img src={src} alt={photo.filename} className="w-full h-32 object-cover" />
      ) : failed ? (
        <div className="w-full h-32 bg-destructive/10 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-destructive/50" />
        </div>
      ) : (
        <div className="w-full h-32 bg-muted flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}
      {selected && (
        <div className="absolute top-1 right-1 bg-primary text-primary-foreground rounded-full p-0.5">
          <Check className="w-3.5 h-3.5" />
        </div>
      )}
      {confidence !== undefined && (
        <div className="absolute top-1 left-1">
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{Math.round(confidence * 100)}%</Badge>
        </div>
      )}
      <div className="p-1.5 bg-card">
        <p className="text-[10px] text-muted-foreground truncate">{photo.filename}</p>
        {photo.tags && photo.tags.length > 0 && (
          <div className="flex gap-0.5 flex-wrap mt-0.5">
            {photo.tags.slice(0, 3).map((tag: string, i: number) => (
              <span key={i} className="text-[9px] bg-secondary text-secondary-foreground px-1 rounded">{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function PhotoMatcher({ topic, count, batchId, templateInstruction, onConfirm }: PhotoMatcherProps) {
  const [pool, setPool] = useState<PhotoItem[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [libraryPhotos, setLibraryPhotos] = useState<PhotoItem[]>([])
  const [libSearch, setLibSearch] = useState('')
  const [libLoading, setLibLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const fetchCount = Math.min(count + 7, 20)

  const loadMatches = useCallback(async () => {
    if (!topic) return
    setLoading(true)
    setError('')
    try {
      const result = templateInstruction
        ? await matchPhotosWeighted(topic, templateInstruction, fetchCount, 30)
        : await matchPhotos(topic, fetchCount, 30)
      type RawMatch = MatchPhoto & { photo_id?: number }
      const raw = result as unknown as { matches?: RawMatch[] } | RawMatch[]
      const matches = Array.isArray(raw) ? raw : (raw.matches ?? [])
      setPool(matches.map(m => ({ ...m, id: m.photo_id ?? m.id })))
      setSelected(new Set())
    } catch {
      setError('照片匹配失败')
    } finally {
      setLoading(false)
    }
  }, [topic, fetchCount, templateInstruction])

  useEffect(() => {
    loadMatches()
  }, [loadMatches])

  const loadLibrary = useCallback(async (search?: string) => {
    setLibLoading(true)
    try {
      const tagParam = search || undefined
      const resp = await getPhotos({ page: 1, page_size: 100, tag: tagParam })
      setLibraryPhotos(resp.items || [])
    } catch {
      toast.error('加载照片库失败')
    } finally {
      setLibLoading(false)
    }
  }, [])

  useEffect(() => {
    loadLibrary()
  }, [loadLibrary])

  const togglePhoto = (photoId: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(photoId)) {
        next.delete(photoId)
      } else {
        next.add(photoId)
      }
      return next
    })
  }

  const handleConfirm = async () => {
    const photoIds = Array.from(selected)
    if (photoIds.length === 0) {
      toast.error('请至少选择一张照片')
      return
    }
    setConfirming(true)
    try {
      if (batchId) {
        await selectPhotos(batchId, photoIds)
      }
      onConfirm?.(photoIds)
    } catch (e) {
      console.error('Failed to select photos:', e)
      toast.error('关联照片失败')
    } finally {
      setConfirming(false)
    }
  }

  const matchedIds = new Set(pool.map(p => p.id))
  const libraryOnly = libraryPhotos.filter(p => !matchedIds.has(p.id))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          已选 {selected.size} 张
        </div>
        <Button variant="outline" size="sm" onClick={loadMatches} disabled={loading}>
          <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
          重新匹配
        </Button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-6 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          正在智能匹配照片...
        </div>
      )}

      {error && (
        <div className="flex items-center justify-center py-6 text-destructive gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {!loading && !error && pool.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-medium">智能匹配</h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {pool.slice(0, fetchCount).map((photo, idx) => (
              <PhotoThumb
                key={photo.id}
                photo={photo}
                selected={selected.has(photo.id)}
                onToggle={() => togglePhoto(photo.id)}
                confidence={(fetchCount - idx) / fetchCount}
              />
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Library className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-medium">照片库</h3>
            <span className="text-xs text-muted-foreground">({libraryOnly.length} 张)</span>
          </div>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="按标签筛选..."
                className="pl-8 h-8 w-48 text-xs"
                value={libSearch}
                onChange={e => setLibSearch(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') loadLibrary(libSearch) }}
              />
            </div>
            <Button variant="outline" size="sm" onClick={() => loadLibrary(libSearch)} disabled={libLoading}>
              {libLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '筛选'}
            </Button>
          </div>
        </div>

        {libLoading && libraryPhotos.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mr-2" />
            加载照片库...
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {libraryOnly.map(photo => (
              <PhotoThumb
                key={photo.id}
                photo={photo}
                selected={selected.has(photo.id)}
                onToggle={() => togglePhoto(photo.id)}
              />
            ))}
            {libraryOnly.length === 0 && (
              <div className="col-span-full text-center py-8 text-muted-foreground">
                <Image className="w-10 h-10 mx-auto mb-2 opacity-30" />
                照片库暂无照片，请先上传照片
              </div>
            )}
          </div>
        )}
      </div>

      {selected.size > 0 && (
        <div className="flex justify-end sticky bottom-4">
          <Button onClick={handleConfirm} disabled={confirming} size="lg">
            {confirming ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
            确认选择 ({selected.size} 张)
          </Button>
        </div>
      )}
    </div>
  )
}
