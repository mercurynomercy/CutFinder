/** App-level tests for the top bar and launcher-loading navigation. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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

describe('App — filters sidebar collapse', () => {
  it('shows an "expand filters" button in the gallery toolbar once the sidebar is collapsed', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /library/i }))

    await userEvent.click(await screen.findByLabelText('Collapse filters'))
    expect(await screen.findByLabelText('Expand filters')).toBeInTheDocument()
    expect(screen.queryByText('Filters')).not.toBeInTheDocument()
  })
})

describe('App — full-screen clip detail', () => {
  it('replaces the whole screen with DetailPanel when a clip is selected, and returns to the gallery on close', async () => {
    server.use(
      http.get(`${API}/clips`, () =>
        HttpResponse.json([
          { id: 1, source_path: '/a.mp4', roll_type: 'a', duration_s: 5, thumbnail_path: null, status: 'done', tags: [] },
        ]),
      ),
    )
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /library/i }))

    window.dispatchEvent(new CustomEvent('cutfinder:navigate', { detail: { clipId: 1 } }))

    expect(await screen.findByText('Clip detail')).toBeInTheDocument()
    // The gallery's top bar (with the Scan button) is gone — full-screen replacement, not an overlay.
    expect(screen.queryByRole('button', { name: 'Scan' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Back to gallery' }))
    expect(await screen.findByRole('button', { name: 'Scan' })).toBeInTheDocument()
  })
})

describe('App — library cleanup from Settings', () => {
  it('finds orphaned entries and deletes them after confirmation', async () => {
    let deletedIds: number[] | null = null
    server.use(
      http.get(`${API}/library/orphans`, () =>
        HttpResponse.json({
          library_reachable: true,
          orphans: [{ id: 3, source_path: '/s/x.mp4', library_path: '/l/x.mp4', roll_type: 'b' }],
        }),
      ),
      http.post(`${API}/library/orphans/delete`, async ({ request }) => {
        deletedIds = (await request.json() as { clip_ids: number[] }).clip_ids
        return HttpResponse.json({ deleted: deletedIds.length })
      }),
    )

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /library/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'Settings' }))
    await userEvent.click(await screen.findByRole('button', { name: /clean up deleted files/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'OK' }))

    await waitFor(() => expect(deletedIds).toEqual([3]))
  })

  it('skips deletion and shows a notice when the library is unreachable', async () => {
    const delHit = vi.fn()
    server.use(
      http.get(`${API}/library/orphans`, () =>
        HttpResponse.json({ library_reachable: false, orphans: [] }),
      ),
      http.post(`${API}/library/orphans/delete`, () => {
        delHit()
        return HttpResponse.json({ deleted: 0 })
      }),
    )

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /library/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'Settings' }))
    await userEvent.click(await screen.findByRole('button', { name: /clean up deleted files/i }))

    expect(await screen.findByText(/unreachable/i)).toBeInTheDocument()
    expect(delHit).not.toHaveBeenCalled()
  })
})
