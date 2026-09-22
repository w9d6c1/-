import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/stores/auth'

export function AuthGuard() {
  const { isLoggedIn } = useAuth()

  if (!isLoggedIn) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
