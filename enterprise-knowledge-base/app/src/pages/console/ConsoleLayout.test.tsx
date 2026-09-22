import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { AuthProvider } from '@/stores/auth'
import { ConsoleLayout } from './ConsoleLayout'

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname}</div>
}

describe('ConsoleLayout 路由隔离', () => {
  it('控制台被挂载但非当前页时，不劫持 /qa/* 路由（不被重定向到 /console）', () => {
    render(
      <MemoryRouter initialEntries={['/qa/internal']}>
        <AuthProvider>
          <ConsoleLayout />
          <LocationProbe />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('loc').textContent).toBe('/qa/internal')
  })

  it('在 /console 下正常渲染子路由', () => {
    render(
      <MemoryRouter initialEntries={['/console']}>
        <AuthProvider>
          <ConsoleLayout />
          <LocationProbe />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('loc').textContent).toBe('/console')
  })
})
