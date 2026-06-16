/** Tests for the JobsPanel feature — task list + toast notifications.
 *
 * Behavior-focused: asserts rendered text/state, not exact Tailwind classes.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { JobsPanel } from '../index'

// Mock useJobEvents — control events per test via mock implementation.
// vi.hoisted ensures the mock fn exists before the hoisted vi.mock factory runs.
const useJobEventsMock = vi.hoisted(() => vi.fn())
vi.mock('@/api/sse', () => ({ useJobEvents: useJobEventsMock }))

describe('JobsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useJobEventsMock.mockReturnValue({ loading: false, error: null, events: [] })
  })

  it('renders nothing when there is no active job and no events', () => {
    const { container } = render(<JobsPanel activeJobId={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the clip path in the progress card when a clip_done event arrives', async () => {
    useJobEventsMock.mockReturnValue({
      loading: false,
      error: null,
      events: [{ type: 'clip_done', job_id: 1, clip_id: 42, path: '/media/clip.mp4' }],
    })
    render(<JobsPanel activeJobId={1} />)

    expect(await screen.findByText('/media/clip.mp4')).toBeInTheDocument()
  })

  it('shows an info toast on job_started', async () => {
    useJobEventsMock.mockReturnValue({
      loading: false,
      error: null,
      events: [{ type: 'job_started', job_id: 1 }],
    })
    render(<JobsPanel activeJobId={1} />)

    expect(
      await screen.findByText('Scan started — processing clips'),
    ).toBeInTheDocument()
  })

  it('shows a success toast with the processed count on job_completed', async () => {
    useJobEventsMock.mockReturnValue({
      loading: false,
      error: null,
      events: [{ type: 'job_completed', job_id: 1, done: 5 }],
    })
    render(<JobsPanel activeJobId={1} />)

    expect(
      await screen.findByText('Scan completed — 5 clips processed'),
    ).toBeInTheDocument()
  })

  it('shows an error toast on job_failed', async () => {
    useJobEventsMock.mockReturnValue({
      loading: false,
      error: null,
      events: [{ type: 'job_failed', job_id: 1 }],
    })
    render(<JobsPanel activeJobId={1} />)

    expect(
      await screen.findByText('Scan failed — check logs for details'),
    ).toBeInTheDocument()
  })

  it('does not loop/crash when the same events stay referentially stable across renders', async () => {
    const events = [{ type: 'clip_done', job_id: 1, clip_id: 7, path: '/a.mp4' }]
    useJobEventsMock.mockReturnValue({ loading: false, error: null, events })
    const { rerender } = render(<JobsPanel activeJobId={1} />)
    rerender(<JobsPanel activeJobId={1} />)

    await waitFor(() => expect(screen.getByText('/a.mp4')).toBeInTheDocument())
  })
})
