/** Tests for JobsPanel's status bar — fixed to the bottom, not the top. */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { JobsPanel } from '../index'
import { server } from '@/test/mocks/server'

const API = 'http://localhost:5080/api'

describe('JobsPanel', () => {
  it('renders nothing when there is no active job', () => {
    const { container } = render(<JobsPanel activeJobId={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a fixed-bottom status bar (not a top progress bar) while a job is running', async () => {
    server.use(
      http.get(`${API}/jobs/:id`, () =>
        HttpResponse.json({ id: 1, kind: 'scan', status: 'running', total: 40, done: 18, error: null }),
      ),
    )
    render(<JobsPanel activeJobId={1} />)

    const statusbar = await screen.findByTestId('statusbar')
    expect(statusbar.className).toContain('bottom-0')
    expect(document.querySelector('[class*="top-0"][class*="fixed"]')).not.toBeInTheDocument()
    expect(screen.getByText('18/40')).toBeInTheDocument()
  })
})
