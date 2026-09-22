import { Sidebar } from './Sidebar'
import { KeepAlivePages } from './KeepAlivePages'

export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden bg-background">
        <KeepAlivePages />
      </main>
    </div>
  )
}
