import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/stores/auth'
import { Login } from './Login'

vi.mock('@/api/auth', () => ({
  loginByPassword: vi.fn(),
  phoneLogin: vi.fn(),
  sendCode: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

import { loginByPassword, sendCode } from '@/api/auth'
import { toast } from 'sonner'

const mockedLogin = vi.mocked(loginByPassword)
const mockedSendCode = vi.mocked(sendCode)
const mockedToastError = vi.mocked(toast.error)
const mockedToastSuccess = vi.mocked(toast.success)

function renderLogin() {
  return render(
    <AuthProvider>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders phone login as the default tab', () => {
    renderLogin()
    expect(screen.getByText('企业知识库系统')).toBeInTheDocument()
    expect(screen.getByLabelText('手机号')).toBeInTheDocument()
  })

  it('sends an SMS code for a valid phone number', async () => {
    const user = userEvent.setup()
    mockedSendCode.mockResolvedValue({ status: 'ok', code: '123456' })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13812345678')
    await user.click(screen.getByText('获取验证码'))
    await waitFor(() => expect(mockedSendCode).toHaveBeenCalledWith('13812345678'))
    expect(mockedToastSuccess).toHaveBeenCalledWith('验证码：123456')
  })

  it('does not call sendCode for a short phone number', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '138')
    await user.click(screen.getByText('获取验证码'))
    expect(mockedSendCode).not.toHaveBeenCalled()
  })

  it('logs in with username/password and stores the session', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({
      access_token: 'token-abc',
      token_type: 'bearer',
      user: {
        id: 7,
        username: 'op',
        phone: null,
        display_name: null,
        email: null,
        role: 'operator',
        department: '运营部',
        is_active: true,
        created_at: '2026-01-01T00:00:00',
      },
    })
    renderLogin()

    await user.click(screen.getByText('密码登录'))
    await user.type(screen.getByLabelText('用户名'), 'op')
    await user.type(screen.getByLabelText('密码'), 'Secret!1')
    await user.click(screen.getByRole('button', { name: '登 录' }))

    await waitFor(() => expect(mockedLogin).toHaveBeenCalledWith({ username: 'op', password: 'Secret!1' }))
    expect(localStorage.getItem('token')).toBe('token-abc')
    expect(localStorage.getItem('user')).toContain('op')
  })

  it('shows an error and does not store a session on failed login', async () => {
    const user = userEvent.setup()
    mockedLogin.mockRejectedValue({
      response: { data: { detail: '用户名或密码错误' } },
    })
    renderLogin()

    await user.click(screen.getByText('密码登录'))
    await user.type(screen.getByLabelText('用户名'), 'op')
    await user.type(screen.getByLabelText('密码'), 'wrong')
    await user.click(screen.getByRole('button', { name: '登 录' }))

    await waitFor(() => expect(mockedToastError).toHaveBeenCalledWith('用户名或密码错误'))
    expect(localStorage.getItem('token')).toBeNull()
  })
})
