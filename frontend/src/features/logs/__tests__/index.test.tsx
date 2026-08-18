/** Tests for the backend-log page — rendering, polling, filters, and navigation. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { LogsPage } from '../index'
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

describe('LogsPage', () => {
  it('shows fetched log lines', async () => {
    mockLogs([
      { seq: 1, level: 'INFO', message: 'scan started' },
      { seq: 2, level: 'ERROR', message: 'boom failed' },
    ])
    render(<LogsPage onClose={() => {}} />)

    expect(await screen.findByText('scan started')).toBeInTheDocument()
    expect(screen.getByText('boom failed')).toBeInTheDocument()
  })

  it('shows the empty state when there are no logs', async () => {
    mockLogs([])
    render(<LogsPage onClose={() => {}} />)
    expect(await screen.findByText(/No logs yet|暂无日志/)).toBeInTheDocument()
  })

  it('calls onClose on the back button', async () => {
    mockLogs([])
    const onClose = vi.fn()
    render(<LogsPage onClose={onClose} />)
    // The back button has an arrow icon + text like "Back" or "返回"
    const backButton = screen.getByRole('button', { name: /back|返回/i })
    await userEvent.click(backButton)
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('shows filter buttons', async () => {
    mockLogs([])
    render(<LogsPage onClose={() => {}} />)
    // Filter buttons: All, INFO, WARN, ERROR, Scan
    expect(screen.getByText('INFO')).toBeInTheDocument()
    expect(screen.getByText('WARN')).toBeInTheDocument()
    expect(screen.getByText('ERROR')).toBeInTheDocument()
  })
})
