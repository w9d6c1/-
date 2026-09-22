import { HashRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/stores/auth'
import { AuthGuard } from '@/components/AuthGuard'
import { AppLayout } from '@/components/layout/AppLayout'
import { KeepAlivePages } from '@/components/layout/KeepAlivePages'
import { Login } from '@/pages/Login'

export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AuthGuard />}>
            <Route element={<AppLayout />}>
              <Route path="/*" element={<KeepAlivePages />} />
            </Route>
          </Route>
        </Routes>
      </HashRouter>
      <Toaster position="top-right" />
    </AuthProvider>
  )
}
