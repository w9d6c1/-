import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth } from './auth'

function Probe() {
  const { token, user, isLoggedIn, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="token">{token ?? 'null'}</span>
      <span data-testid="user">{user ? user.username : 'null'}</span>
      <span data-testid="logged">{String(isLoggedIn)}</span>
      <button onClick={() => login('tok-1', { id: 1, username: 'admin', role: 'superadmin', department: '技术部' })}>
        login
      </button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

function renderAuth() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

describe('AuthProvider', () => {
  it('starts logged out with empty localStorage', () => {
    renderAuth()
    expect(screen.getByTestId('token').textContent).toBe('null')
    expect(screen.getByTestId('logged').textContent).toBe('false')
  })

  it('login persists token and user to localStorage', async () => {
    const user = userEvent.setup()
    renderAuth()
    await user.click(screen.getByText('login'))
    expect(localStorage.getItem('token')).toBe('tok-1')
    expect(localStorage.getItem('user')).toContain('admin')
    expect(screen.getByTestId('token').textContent).toBe('tok-1')
    expect(screen.getByTestId('user').textContent).toBe('admin')
    expect(screen.getByTestId('logged').textContent).toBe('true')
  })

  it('logout clears token and user', async () => {
    const user = userEvent.setup()
    renderAuth()
    await user.click(screen.getByText('login'))
    await user.click(screen.getByText('logout'))
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(screen.getByTestId('logged').textContent).toBe('false')
  })

  it('restores session from localStorage on mount', () => {
    localStorage.setItem('token', 'restored-token')
    localStorage.setItem('user', JSON.stringify({ id: 2, username: 'restored', role: 'operator', department: '运营部' }))
    renderAuth()
    expect(screen.getByTestId('token').textContent).toBe('restored-token')
    expect(screen.getByTestId('user').textContent).toBe('restored')
    expect(screen.getByTestId('logged').textContent).toBe('true')
  })

  it('treats corrupt user JSON as logged out', () => {
    localStorage.setItem('token', 'stale-token')
    localStorage.setItem('user', 'not-json{{{')
    renderAuth()
    expect(screen.getByTestId('user').textContent).toBe('null')
    expect(screen.getByTestId('logged').textContent).toBe('false')
  })
})
