import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../client'

function mockFetch() {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({}),
  } as Response)
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('_fetch Content-Type header', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('omits Content-Type on a GET with no body', async () => {
    const fn = mockFetch()
    await api.getSettings()
    const init = fn.mock.calls[0][1] as RequestInit
    const headers = (init.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('sends Content-Type: application/json when there is a body', async () => {
    const fn = mockFetch()
    await api.putSettings({ text_model: 'x' } as never)
    const init = fn.mock.calls[0][1] as RequestInit
    const headers = (init.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })
})
