/** Tests for the DetailPanel feature — behavior-focused (loads + interactions). */

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

  it('loads and shows the clip detail (source file)', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByText('Source file')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    render(<DetailPanel clipId={1} onClose={onClose} />)
    await screen.findByText('Source file')
    await userEvent.click(screen.getByRole('button', { name: /close panel/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn()
    render(<DetailPanel clipId={1} onClose={onClose} />)
    await screen.findByText('Source file')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
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
    // Compact segmented A/B toggle
    expect(await screen.findByRole('button', { name: 'A-roll' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'B-roll' })).toBeInTheDocument()
    // Re-analyze action (icon button)
    expect(screen.getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument()
  })
})
