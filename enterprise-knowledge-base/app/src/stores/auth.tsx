import { useState, useEffect, createContext, useContext, useCallback } from 'react'

export interface AuthUser {
  id: number
  username: string
  role: string
  department: string
}

interface AuthContextType {
  token: string | null
  user: AuthUser | null
  isLoggedIn: boolean
  login: (token: string, user: AuthUser) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>(null!)

export function useAuth() {
  return useContext(AuthContext)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const u = localStorage.getItem('user')
      return u ? JSON.parse(u) : null
    } catch {
      return null
    }
  })

  const isLoggedIn = !!(token && user)

  const login = useCallback((t: string, u: AuthUser) => {
    localStorage.setItem('token', t)
    localStorage.setItem('user', JSON.stringify(u))
    setToken(t)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    if (token && !user) {
      localStorage.removeItem('token')
      setToken(null)
    }
  }, [token, user])

  return (
    <AuthContext.Provider value={{ token, user, isLoggedIn, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
