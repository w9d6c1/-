import {
  Gauge, FolderTree, HelpCircle, Newspaper, ClipboardCheck,
  MessageSquare, MessageCircle, BookMarked, ShieldCheck, ScrollText,
} from 'lucide-react'

export interface ConsoleNavItem {
  to: string
  label: string
  icon: typeof Gauge
  roles?: string[]
}

export const consoleNav: ConsoleNavItem[] = [
  { to: '/console', label: '控制台概览', icon: Gauge },
  { to: '/console/categories', label: '分类管理', icon: FolderTree },
  { to: '/console/faqs', label: 'FAQ 管理', icon: HelpCircle },
  { to: '/console/source-contents', label: '多源内容', icon: Newspaper },
  { to: '/console/review', label: '审核中心', icon: ClipboardCheck, roles: ['superadmin', 'dept_admin'] },
  { to: '/console/feedbacks', label: '用户反馈', icon: MessageSquare },
  { to: '/console/unanswered', label: '未命中问题', icon: MessageCircle },
  { to: '/console/dictionary', label: '词库管理', icon: BookMarked },
  { to: '/console/permissions', label: '权限管理', icon: ShieldCheck, roles: ['superadmin'] },
  { to: '/console/audit', label: '操作日志', icon: ScrollText, roles: ['superadmin'] },
]

export function canSeeConsoleItem(item: ConsoleNavItem, role?: string): boolean {
  if (!item.roles) return true
  return !!role && item.roles.includes(role)
}
