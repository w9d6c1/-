import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Dashboard } from './Dashboard'
import type { DashboardStats } from '@/api/dashboard'

vi.mock('@/api/dashboard', () => ({
  getDashboardStats: vi.fn(),
}))
vi.mock('@/api/documents', () => ({
  getDocuments: vi.fn(),
}))
vi.mock('@/api/articles', () => ({
  getBatches: vi.fn(),
  getPhotoUrl: vi.fn((n: string) => `/mock/${n}`),
}))

import { getDashboardStats } from '@/api/dashboard'
import { getDocuments } from '@/api/documents'
import { getBatches } from '@/api/articles'

const stats: DashboardStats = {
  today_chats: 42,
  faq_hit_rate: 0.85,
  feedback_good_rate: 0.9,
  pending_reviews: 3,
  pending_unanswered: 1,
  trend: [{ date: '2026-01-01', count: 10 }, { date: '2026-01-02', count: 20 }],
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getDashboardStats).mockResolvedValue(stats)
    vi.mocked(getDocuments).mockResolvedValue({ total: 128 } as never)
    vi.mocked(getBatches).mockResolvedValue({ total: 5 } as never)
  })

  it('renders stat cards from API data', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('仪表盘')).toBeInTheDocument())
    expect(screen.getByText('今日咨询')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('128')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('FAQ 命中率 85%')).toBeInTheDocument()
  })

  it('shows pending review and unanswered warnings', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    )
    await screen.findByText('有 3 条文档待审核')
    expect(screen.getByText('有 1 条未回答问题')).toBeInTheDocument()
  })

  it('renders quick action shortcuts', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    )
    await screen.findByText('快捷操作')
    expect(screen.getByText('批量生成营销文章')).toBeInTheDocument()
    expect(screen.getByText('管理知识库文档')).toBeInTheDocument()
    expect(screen.getByText('查看文章批次')).toBeInTheDocument()
  })

  it('does not crash when APIs fail (silent degradation)', async () => {
    vi.mocked(getDashboardStats).mockRejectedValue(new Error('down'))
    vi.mocked(getDocuments).mockRejectedValue(new Error('down'))
    vi.mocked(getBatches).mockRejectedValue(new Error('down'))
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('仪表盘')).toBeInTheDocument())
    expect(screen.getByText('今日咨询')).toBeInTheDocument()
    expect(screen.getAllByText('0').length).toBeGreaterThan(0)
  })
})
