import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/stores/auth'
import { AuthGuard } from './AuthGuard'

function renderWithAuth() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div>home page</div>} />
          </Route>
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('AuthGuard', () => {
  it('redirects to /login when not authenticated', () => {
    localStorage.clear()
    renderWithAuth()
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('home page')).not.toBeInTheDocument()
  })

  it('renders the protected outlet when authenticated', () => {
    localStorage.setItem('token', 'valid-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'superadmin', department: '' }))
    renderWithAuth()
    expect(screen.getByText('home page')).toBeInTheDocument()
    expect(screen.queryByText('login page')).not.toBeInTheDocument()
  })
})
