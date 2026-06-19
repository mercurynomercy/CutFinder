/** Tests for the SubtitlesPage feature — pick video/folder, export, results.
 *
 * Behavior-focused (rendered text + network effects). Each test installs its
 * own MSW handlers via server.use() for determinism.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import { SubtitlesPage } from '../index'

const API = 'http://localhost:5080/api'

describe('SubtitlesPage', () => {
  it('shows the chosen video and folder once picked', async () => {
    server.use(
      http.post(`${API}/pick-file`, () => HttpResponse.json({ path: '/Movies/final cut.mov' })),
      http.post(`${API}/pick-folder`, () => HttpResponse.json({ path: '/Movies/Subs' })),
    )

    render(<SubtitlesPage onClose={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Choose video' }))
    expect(await screen.findByText('final cut.mov')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Choose output folder' }))
    expect(await screen.findByText('/Movies/Subs')).toBeInTheDocument()
  })

  it('disables Export until both a video and folder are chosen', async () => {
    server.use(
      http.post(`${API}/pick-file`, () => HttpResponse.json({ path: '/Movies/a.mov' })),
      http.post(`${API}/pick-folder`, () => HttpResponse.json({ path: '/Movies/Subs' })),
    )

    render(<SubtitlesPage onClose={() => {}} />)

    const exportBtn = screen.getByRole('button', { name: 'Export' })
    expect(exportBtn).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Choose video' }))
    await screen.findByText('a.mov')
    expect(exportBtn).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Choose output folder' }))
    await screen.findByText('/Movies/Subs')
    expect(exportBtn).toBeEnabled()
  })

  it('exports with the chosen video_path/out_dir/formats and lists produced files', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup()
    let body: { video_path?: string; out_dir?: string; formats?: string[] } | null = null
    const reveal = vi.fn()

    server.use(
      http.post(`${API}/pick-file`, () => HttpResponse.json({ path: '/Movies/a.mov' })),
      http.post(`${API}/pick-folder`, () => HttpResponse.json({ path: '/Movies/Subs' })),
      http.post(`${API}/subtitles/export`, async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json({ job_id: 7 })
      }),
      http.get(`${API}/jobs/:id`, () => HttpResponse.json({
        id: 7, status: 'done', total: 1, done: 1, failed: 0, started_at: null, finished_at: null,
      })),
      http.get(`${API}/subtitles/:id`, () => HttpResponse.json({
        job_id: 7, status: 'done', files: ['/Movies/Subs/a.zh.itt', '/Movies/Subs/a.zh.srt'],
      })),
      http.post(`${API}/subtitles/:id/reveal`, ({ params }) => {
        reveal(Number(params.id))
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    render(<SubtitlesPage onClose={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Choose video' }))
    await screen.findByText('a.mov')
    await user.click(screen.getByRole('button', { name: 'Choose output folder' }))
    await screen.findByText('/Movies/Subs')

    await user.click(screen.getByRole('button', { name: 'Export' }))

    // Advance past the 1.5s poll interval so waitForJob resolves.
    await vi.advanceTimersByTimeAsync(2000)

    expect(await screen.findByText('a.zh.itt')).toBeInTheDocument()
    expect(screen.getByText('a.zh.srt')).toBeInTheDocument()
    expect(body).toEqual({ video_path: '/Movies/a.mov', out_dir: '/Movies/Subs', formats: ['itt', 'srt'] })

    await user.click(screen.getByRole('button', { name: 'Reveal in Finder' }))
    await waitFor(() => expect(reveal).toHaveBeenCalledWith(7))

    vi.useRealTimers()
  })
})
