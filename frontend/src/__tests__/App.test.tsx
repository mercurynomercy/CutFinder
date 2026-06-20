/** App-level tests for the header menu "Clean up deleted files" action.
 *
 * The library-cleanup flow lives in the overflow menu (not in Settings): it
 * lists orphaned catalog entries, confirms, then deletes them. A library that
 * is unreachable must be skipped (never wipe the catalog).
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import App from '@/App'

const API = 'http://localhost:5080/api'

describe('App — library cleanup from the header menu', () => {
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
    await userEvent.click(await screen.findByRole('button', { name: /menu/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /clean up deleted files/i }))
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
    await userEvent.click(await screen.findByRole('button', { name: /menu/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /clean up deleted files/i }))

    expect(await screen.findByText(/unreachable/i)).toBeInTheDocument()
    expect(delHit).not.toHaveBeenCalled()
  })
})
