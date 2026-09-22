import { describe, it, expect, beforeEach } from 'vitest'
import { AxiosError } from 'axios'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from './client'

function ok(config: InternalAxiosRequestConfig, data: unknown = { ok: true }): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

describe('api client interceptors', () => {
  beforeEach(() => {
    localStorage.clear()
    window.location.hash = ''
  })

  it('injects Bearer token from localStorage', async () => {
    localStorage.setItem('token', 'jwt-test-token')
    let seenAuth: unknown = undefined
    client.defaults.adapter = async (config) => {
      seenAuth = config.headers?.Authorization
      return ok(config)
    }
    await client.get('/some/endpoint')
    expect(seenAuth).toBe('Bearer jwt-test-token')
  })

  it('sends no Authorization header without a token', async () => {
    let seenAuth: unknown = 'sentinel'
    client.defaults.adapter = async (config) => {
      seenAuth = config.headers?.Authorization
      return ok(config)
    }
    await client.get('/some/endpoint')
    expect(seenAuth).toBeUndefined()
  })

  it('clears stored credentials and redirects to login on 401', async () => {
    localStorage.setItem('token', 'expired-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'a' }))
    client.defaults.adapter = async (config) => {
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, null, {
        data: { detail: 'Not authenticated' },
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config,
      })
    }
    await expect(client.get('/private')).rejects.toBeInstanceOf(AxiosError)
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(window.location.hash).toContain('#/login')
  })

  it('rejects and does not redirect on non-401 errors', async () => {
    localStorage.setItem('token', 'jwt')
    client.defaults.adapter = async (config) => {
      throw new AxiosError('Bad Request', 'ERR_BAD_REQUEST', config, null, {
        data: { detail: 'bad' },
        status: 400,
        statusText: 'Bad Request',
        headers: {},
        config,
      })
    }
    await expect(client.get('/private')).rejects.toBeInstanceOf(AxiosError)
    expect(window.location.hash).toBe('')
    expect(localStorage.getItem('token')).toBe('jwt')
  })
})
