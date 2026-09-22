import { getPhotoUrl } from '@/api/articles'

const IMAGE_MARKER_RE = /\[IMAGE:\s*(?:照片\s*(\d+)\s*[:：])?\s*配图建议[:：]\s*(.+?)\]/gi

export function markdownToHtml(md: string, imagePlacement: { object_name?: string; caption?: string }[] = []): string {
  let html = md

  // 配图标记按出现顺序与后端提取的 placement 一一对应，不再按 caption 兜底错配第一张图
  let pIdx = 0
  html = html.replace(IMAGE_MARKER_RE, (_match: string, _num: string, caption: string) => {
    const cap = caption.trim()
    const placement = imagePlacement[pIdx]
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
