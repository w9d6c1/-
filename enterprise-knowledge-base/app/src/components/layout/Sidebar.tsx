import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  Calendar,
  Settings,
  Users,
  PenLine,
  LogOut,
  Rocket,
  Layers,
  Camera,
  Wand2,
  UserCheck,
  BarChart3,
  Flame,
  Video,
  MessageSquare,
  Headset,
  LayoutGrid,
} from 'lucide-react'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/hot-topics', icon: Flame, label: '今日热点' },
  { to: '/copywriting', icon: Video, label: '短视频文案' },
  { to: '/batch-generate', icon: PenLine, label: '文章创作' },
  { to: '/ai-write', icon: Wand2, label: 'AI 写作' },
  { to: '/articles', icon: FileText, label: '文章管理' },
  { to: '/publish-dashboard', icon: BarChart3, label: '发布概览' },
  { to: '/accounts', icon: UserCheck, label: '平台账号' },
  { to: '/knowledge-base', icon: BookOpen, label: '知识库' },
  { to: '/photos', icon: Camera, label: '照片库' },
  { to: '/templates', icon: Layers, label: '模板管理' },
  { to: '/schedule', icon: Calendar, label: '批次任务' },
  { to: '/users', icon: Users, label: '用户管理' },
  { to: '/settings', icon: Settings, label: '系统设置' },
]

const qaNavItems = [
  { to: '/qa/internal', icon: MessageSquare, label: '内部问答' },
  { to: '/qa/customer', icon: Headset, label: '客服问答' },
  { to: '/console', icon: LayoutGrid, label: '控制台' },
]

export function Sidebar() {
  const location = useLocation()
  const { user, logout } = useAuth()

  const roleLabels: Record<string, string> = {
    superadmin: '超级管理员',
    dept_admin: '部门管理员',
    operator: '操作员',
    readonly: '只读用户',
  }

  return (
    <div className="flex flex-col h-full border-r bg-card">
      <div className="p-4 border-b">
        <h1 className="text-lg font-bold tracking-tight flex items-center gap-2">
          <Rocket className="h-5 w-5 text-primary" />
          AI文章生成器
        </h1>
        <p className="text-xs text-muted-foreground mt-1">批量创作平台</p>
      </div>

      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
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

        <div className="my-2 border-t" />

        {qaNavItems.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname.startsWith(to)
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

      <div className="p-4 border-t">
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{user?.username || '未登录'}</p>
            <p className="text-xs text-muted-foreground">{roleLabels[user?.role || ''] || user?.role}</p>
          </div>
          <button
            onClick={logout}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="退出登录"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
