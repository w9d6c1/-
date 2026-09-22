import { useState, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Dashboard } from '@/pages/Dashboard'
import { Articles } from '@/pages/Articles'
import { ArticleDetail } from '@/pages/ArticleDetail'
import { KnowledgeBase } from '@/pages/KnowledgeBase'
import { BatchGenerate } from '@/pages/BatchGenerate'
import { Schedule } from '@/pages/Schedule'
import { SettingsPage } from '@/pages/Settings'
import { Users } from '@/pages/Users'
import { PublishManager } from '@/pages/PublishManager'
import { PublishDashboard } from '@/pages/PublishDashboard'
import { Accounts } from '@/pages/Accounts'
import { TemplateManager } from '@/pages/TemplateManager'
import { PhotoLibrary } from '@/pages/PhotoLibrary'
import { AIWrite } from '@/pages/AIWrite'
import { HotTopics } from '@/pages/HotTopics'
import { Copywriting } from '@/pages/Copywriting'
import { InternalChat } from '@/pages/qa/InternalChat'
import { CustomerChat } from '@/pages/qa/CustomerChat'
import { ConsoleLayout } from '@/pages/console/ConsoleLayout'

interface TopPage {
  key: string
  path: string
  element: ReactNode
  matchPrefix?: boolean
}

const topPages: TopPage[] = [
  { key: 'dashboard', path: '/', element: <Dashboard /> },
  { key: 'hot-topics', path: '/hot-topics', element: <HotTopics /> },
  { key: 'copywriting', path: '/copywriting', element: <Copywriting /> },
  { key: 'batch-generate', path: '/batch-generate', element: <BatchGenerate /> },
  { key: 'ai-write', path: '/ai-write', element: <AIWrite /> },
  { key: 'articles', path: '/articles', element: <Articles /> },
  { key: 'publish-dashboard', path: '/publish-dashboard', element: <PublishDashboard /> },
  { key: 'accounts', path: '/accounts', element: <Accounts /> },
  { key: 'knowledge-base', path: '/knowledge-base', element: <KnowledgeBase /> },
  { key: 'photos', path: '/photos', element: <PhotoLibrary /> },
  { key: 'templates', path: '/templates', element: <TemplateManager /> },
  { key: 'schedule', path: '/schedule', element: <Schedule /> },
  { key: 'users', path: '/users', element: <Users /> },
  { key: 'settings', path: '/settings', element: <SettingsPage /> },
  { key: 'qa-internal', path: '/qa/internal', element: <InternalChat /> },
  { key: 'qa-customer', path: '/qa/customer', element: <CustomerChat /> },
  { key: 'console', path: '/console', element: <ConsoleLayout />, matchPrefix: true },
]

const detailPatterns = [/^\/articles\/[^/]+$/, /^\/batch\/[^/]+\/publish$/]

export function KeepAlivePages() {
  const { pathname } = useLocation()

  const isDetail = detailPatterns.some(re => re.test(pathname))
  const top = topPages.find(p => {
    if (p.path === '/') return pathname === '/'
    if (p.matchPrefix) return pathname === p.path || pathname.startsWith(p.path + '/')
    return pathname === p.path
  }) ?? null

  const [prevTopKey, setPrevTopKey] = useState<string | null>(null)
  const [visited, setVisited] = useState<Record<string, ReactNode>>({})

  if (top && top.key !== prevTopKey) {
    setPrevTopKey(top.key)
    setVisited(prev => (prev[top.key] ? prev : { ...prev, [top.key]: top.element }))
  }

  if (!top && !isDetail) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="relative h-full">
      <div className={isDetail ? 'hidden' : 'h-full'}>
        {Object.entries(visited).map(([key, element]) => (
          <div
            key={key}
            className={key === top?.key ? 'h-full overflow-y-auto' : 'hidden'}
          >
            {element}
          </div>
        ))}
      </div>
      <Routes>
        <Route
          path="/articles/:id"
          element={
            <div className="absolute inset-0 overflow-y-auto bg-background">
              <ArticleDetail />
            </div>
          }
        />
        <Route
          path="/batch/:id/publish"
          element={
            <div className="absolute inset-0 overflow-y-auto bg-background">
              <PublishManager />
            </div>
          }
        />
      </Routes>
    </div>
  )
}
