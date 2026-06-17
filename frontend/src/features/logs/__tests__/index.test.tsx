/** Tests for the backend-log modal — visibility, rendering, and live polling. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { LogModal } from '../index'
import { server } from '@/test/mocks/server'

const API = 'http://localhost:5080'

function mockLogs(lines: Array<{ seq: number; level: string; message: string }>) {
  server.use(
    http.get(`${API}/api/logs`, () =>
      HttpResponse.json({
        logs: lines.map((l) => ({ ...l, time: 1_700_000_000, name: 'cutfinder' })),
        last_seq: lines.length ? lines[lines.length - 1].seq : 0,
      }),
    ),
  )
}

describe('LogModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<LogModal open={false} onClose={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows fetched log lines when open', async () => {
    mockLogs([
      { seq: 1, level: 'INFO', message: 'scan started' },
      { seq: 2, level: 'ERROR', message: 'boom failed' },
    ])
    render(<LogModal open onClose={() => {}} />)

    expect(await screen.findByText('scan started')).toBeInTheDocument()
    expect(screen.getByText('boom failed')).toBeInTheDocument()
  })

  it('shows the empty state when there are no logs', async () => {
    mockLogs([])
    render(<LogModal open onClose={() => {}} />)
    expect(await screen.findByText('No logs yet')).toBeInTheDocument()
  })

  it('closes on the close button', async () => {
    mockLogs([])
    const onClose = vi.fn()
    render(<LogModal open onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
