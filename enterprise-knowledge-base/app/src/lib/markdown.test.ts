import { describe, it, expect, vi } from 'vitest'
import { markdownToHtml } from './markdown'

vi.mock('@/api/articles', () => ({
  getPhotoUrl: (name: string) => `/mock-photo/${encodeURIComponent(name)}`,
}))

describe('markdownToHtml()', () => {
  it('wraps plain text in a paragraph', () => {
    const html = markdownToHtml('你好世界')
    expect(html).toContain('<p>你好世界</p>')
  })

  it('keeps blank-line-separated blocks independent', () => {
    const html = markdownToHtml('第一段\n\n第二段')
    expect(html).toContain('<p>第一段</p>')
    expect(html).toContain('<p>第二段</p>')
  })

  it('converts newlines inside a paragraph to <br/>', () => {
    const html = markdownToHtml('行一\n行二')
    expect(html).toContain('<br/>')
  })

  it('renders markdown headings', () => {
    const html = markdownToHtml('## 二级标题\n\n### 三级标题')
    expect(html).toContain('<h2>二级标题</h2>')
    expect(html).toContain('<h3>三级标题</h3>')
  })

  it('renders bold and italic', () => {
    const html = markdownToHtml('**加粗** 与 *斜体*')
    expect(html).toContain('<strong>加粗</strong>')
    expect(html).toContain('<em>斜体</em>')
  })

  it('renders inline code', () => {
    const html = markdownToHtml('使用 `npm test` 运行')
    expect(html).toContain('<code>npm test</code>')
  })

  it('replaces [IMAGE] marker with a suggestion div when no placement given', () => {
    const html = markdownToHtml('[IMAGE:配图建议:施工现场图]')
    expect(html).toContain('📷 配图建议：施工现场图')
    expect(html).not.toContain('<img')
  })

  it('renders an <img> figure when a placement is provided', () => {
    const html = markdownToHtml('[IMAGE:配图建议:施工现场图]', [
      { object_name: 'photo-library/abc.jpg', caption: '施工现场图' },
    ])
    expect(html).toContain('<img src="/mock-photo/photo-library%2Fabc.jpg"')
    expect(html).toContain('施工现场图')
  })

  it('maps image markers to placements by order, not by caption', () => {
    const md = '[IMAGE:配图建议:第一张]\n\n[IMAGE:配图建议:第二张]'
    const html = markdownToHtml(md, [
      { object_name: 'photo-library/first.jpg', caption: 'x' },
      { object_name: 'photo-library/second.jpg', caption: 'x' },
    ])
    const firstImg = html.indexOf('first.jpg')
    const secondImg = html.indexOf('second.jpg')
    expect(firstImg).toBeGreaterThan(-1)
    expect(secondImg).toBeGreaterThan(firstImg)
  })

  it('handles special characters in captions without throwing', () => {
    const html = markdownToHtml('[IMAGE:配图建议:图 & 说明]')
    expect(html).toContain('📷 配图建议：图 & 说明')
  })

  it('handles empty input without throwing', () => {
    expect(typeof markdownToHtml('')).toBe('string')
  })
})
