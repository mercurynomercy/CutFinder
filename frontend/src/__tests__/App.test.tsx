/** App-level tests for the top bar and launcher-loading navigation. */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import type { ClipSummary } from '@/api/client'
import App from '@/App'

const API = 'http://localhost:5080/api'

describe('App — top bar navigation', () => {
  it('renders a global search box, task/rough-cut nav links, a settings icon, and a scan button — no overflow menu', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /library/i }))

    expect(screen.getByPlaceholderText('Search clips…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /task queue/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rough cut/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Scan' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /menu/i })).not.toBeInTheDocument()
  })
})

describe('App — navigating from the launcher while clips are still loading', () => {
  it('lands on the target page (not the bare loading skeleton) when a launcher card is clicked before /api/clips resolves', async () => {
    // Hold GET /api/clips open so `loading` stays true past the launcher click below.
    let resolveClips: (clips: ClipSummary[]) => void = () => {}
    const clipsPromise = new Promise<ClipSummary[]>((resolve) => { resolveClips = resolve })
    server.use(
      http.get(`${API}/clips`, async () => {
        const clips = await clipsPromise
        return HttpResponse.json(clips)
      }),
    )

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /settings/i }))

    // Settings should render — not the header-less loading skeleton.
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()

    // Let the deferred fetch resolve so it doesn't leak into later tests.
    resolveClips([])
  })
})
