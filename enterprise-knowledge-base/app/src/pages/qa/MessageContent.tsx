import { useMemo } from 'react'
import type { Citation, ImageInfo } from '@/api/agent'

const COMBINED_RE = /\[图(\d+)\]|\[(\d+)\]/g

type Segment =
  | { type: 'text'; text: string }
  | { type: 'image'; id: number }
  | { type: 'cite'; index: number }

interface Props {
  content: string
  citations?: Citation[]
  images?: ImageInfo[]
  isStreaming?: boolean
}

export function MessageContent({ content, citations, images, isStreaming }: Props) {
  const imageMap = useMemo(() => {
    const map = new Map<number, ImageInfo>()
    for (const img of images || []) map.set(img.id, img)
    return map
  }, [images])

  const segments = useMemo<Segment[]>(() => {
    const text = content || ''
    const result: Segment[] = []
    let lastIndex = 0
    const re = new RegExp(COMBINED_RE.source, 'g')
    let match: RegExpExecArray | null
    while ((match = re.exec(text)) !== null) {
      if (match.index > lastIndex) {
        result.push({ type: 'text', text: text.slice(lastIndex, match.index) })
      }
      if (match[1] !== undefined) {
        result.push({ type: 'image', id: parseInt(match[1], 10) })
      } else {
        result.push({ type: 'cite', index: parseInt(match[2], 10) })
      }
      lastIndex = match.index + match[0].length
    }
    if (lastIndex < text.length) {
      result.push({ type: 'text', text: text.slice(lastIndex) })
    }
    return result
  }, [content])

  const citedIndices = useMemo(
    () => new Set(segments.filter(s => s.type === 'cite').map(s => (s as { index: number }).index)),
    [segments],
  )

  const activeCitations = useMemo(
    () => (citations || []).filter(c => citedIndices.has(c.index)).sort((a, b) => a.index - b.index),
    [citations, citedIndices],
  )

  const visible = segments.filter(seg => {
    if (seg.type === 'image') {
      const info = imageMap.get(seg.id)
      return !!info || !!isStreaming
    }
    return true
  })

  return (
    <div className="break-words">
      <div className="leading-7 whitespace-pre-wrap">
        {visible.map((seg, i) => {
          if (seg.type === 'text') {
            return <span key={i}>{seg.text}</span>
          }
          if (seg.type === 'cite') {
            return (
              <sup
                key={i}
                onClick={() => {
                  document.getElementById(`cite-ref-${seg.index}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                }}
                className="cursor-pointer text-primary font-semibold text-xs mx-0.5"
              >
                [{seg.index}]
              </sup>
            )
          }
          const info = imageMap.get(seg.id)
          if (!info) {
            return (
              <div key={i} className="my-2 h-28 w-40 rounded-md bg-muted animate-pulse" />
            )
          }
          const cite = citations?.find(c => c.index === info.doc_index)
          return (
            <figure key={i} className="my-2">
              <img
                src={info.url}
                alt=""
                className="max-w-full max-h-[420px] rounded-md border cursor-zoom-in"
                onClick={() => window.open(info.url, '_blank', 'noopener')}
              />
              {cite && <figcaption className="text-xs text-muted-foreground mt-1">来自《{cite.title}》</figcaption>}
            </figure>
          )
        })}
      </div>

      {activeCitations.length > 0 && (
        <div className="mt-4 p-4 rounded-lg border bg-muted/40">
          <div className="text-xs font-semibold text-muted-foreground mb-2">参考文献</div>
          {activeCitations.map(c => (
            <div key={c.index} id={`cite-ref-${c.index}`} className="py-1.5 text-xs leading-relaxed border-b border-dashed last:border-0">
              <span className="font-semibold text-primary mr-2">[{c.index}]</span>
              <span className="text-muted-foreground mr-1.5">{c.is_internal ? '内部文档' : c.source_name || c.platform || '外部来源'}</span>
              {!c.is_internal && c.url ? (
                <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">《{c.title}》</a>
              ) : (
                <span className="font-medium">《{c.title}》</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
