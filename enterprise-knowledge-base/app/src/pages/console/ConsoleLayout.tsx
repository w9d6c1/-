import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/stores/auth'
import { canSeeConsoleItem, consoleNav } from './consoleNav'
import { Overview } from './Overview'
import { Categories } from './Categories'
import { Faqs } from './Faqs'
import { Dictionary } from './Dictionary'
import { Permissions } from './Permissions'
import { AuditLog } from './AuditLog'
import { SourceContents } from './SourceContents'
import { ReviewCenter } from './ReviewCenter'
import { Feedbacks } from './Feedbacks'
import { Unanswered } from './Unanswered'

export function ConsoleLayout() {
  const { pathname } = useLocation()
  const { user } = useAuth()
  const items = consoleNav.filter(item => canSeeConsoleItem(item, user?.role))

  return (
    <div className="flex h-full">
      <aside className="w-52 shrink-0 border-r bg-card overflow-y-auto">
        <nav className="p-2 space-y-1">
          {items.map(({ to, icon: Icon, label }) => {
            const isActive = to === '/console' ? pathname === '/console' : pathname.startsWith(to)
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            )
          })}
        </nav>
      </aside>

      <div className="flex-1 overflow-y-auto">
        {/* 仅在 /console 下渲染内部路由：控制台被 keep-alive 隐藏时不能劫持其他路由 */}
        {pathname.startsWith('/console') && (
          <Routes>
            <Route path="/console" element={<Overview />} />
            <Route path="/console/categories" element={<Categories />} />
            <Route path="/console/faqs" element={<Faqs />} />
            <Route path="/console/source-contents" element={<SourceContents />} />
            <Route path="/console/review" element={<ReviewCenter />} />
            <Route path="/console/feedbacks" element={<Feedbacks />} />
            <Route path="/console/unanswered" element={<Unanswered />} />
            <Route path="/console/dictionary" element={<Dictionary />} />
            <Route path="/console/permissions" element={<Permissions />} />
            <Route path="/console/audit" element={<AuditLog />} />
            <Route path="*" element={<Navigate to="/console" replace />} />
          </Routes>
        )}
      </div>
    </div>
  )
}
