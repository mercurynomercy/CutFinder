/** Tests for the DetailPanel feature — full-screen clip-detail view. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { DetailPanel } from '../index'
import { server } from '@/test/mocks/server'

describe('DetailPanel', () => {
  it('renders nothing when clipId is null', () => {
    const { container } = render(<DetailPanel clipId={null} onClose={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders as a full-screen view (no modal backdrop) once loaded', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    await screen.findByText('Source file')
    expect(document.querySelector('.bg-black\\/50')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('calls onClose when the back-to-gallery button is clicked', async () => {
    const onClose = vi.fn()
    render(<DetailPanel clipId={1} onClose={onClose} />)
    await screen.findByText('Source file')
    await userEvent.click(screen.getByRole('button', { name: 'Back to gallery' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn()
    render(<DetailPanel clipId={1} onClose={onClose} />)
    await screen.findByText('Source file')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('does not render an editable summary textarea', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    await screen.findByText('Source file')
    expect(screen.queryByRole('textbox', { name: /summary/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('shows the library path (file destination) and capture date together', async () => {
    server.use(
      http.get('http://localhost:5080/api/clips/:id', ({ params }) =>
        HttpResponse.json({
          id: Number(params.id), source_path: '/m/v.mp4', library_path: '/Library/2026-01-15/A-roll/A-0001.mp4',
          roll_type: 'a', roll_source: 'auto', summary: 'sum', description: null,
          duration_s: 10, width: null, height: null, fps: null, codec: null,
          thumbnail_path: null, status: 'done', error: null, capture_time: '2026-01-15T08:00:00Z',
          date_source: 'file', tags: [],
        }),
      ),
    )
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByText('/Library/2026-01-15/A-roll/A-0001.mp4')).toBeInTheDocument()
    expect(screen.getByText(/Capture date \(from file time\)/)).toBeInTheDocument()
  })

  it('shows the Suggested cuts section with a Suggest keyframes button', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByText('Suggested cuts')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Suggest keyframes' })).toBeInTheDocument()
  })

  it('renders keyframe suggestions when present', async () => {
    server.use(
      http.get('http://localhost:5080/api/clips/:id', ({ params }) =>
        HttpResponse.json({
          id: Number(params.id), source_path: '/m/v.mp4', library_path: null,
          roll_type: 'b', roll_source: 'auto', summary: null, description: 'x',
          duration_s: 10, width: null, height: null, fps: null, codec: null,
          thumbnail_path: null, status: 'done', error: null, capture_time: null,
          date_source: 'embedded', tags: [],
          keyframes: [
            { rank: 1, start_s: 3, end_s: 6, reason: 'nice shot', source: 'vision', has_frame: true },
          ],
        }),
      ),
    )
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByText('nice shot')).toBeInTheDocument()
    expect(screen.getByText('0:03–0:06')).toBeInTheDocument()
  })

  it('shows the A/B correction toggle and re-analyze action', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByRole('button', { name: 'A-roll' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'B-roll' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument()
  })
})
