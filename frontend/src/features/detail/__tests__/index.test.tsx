/** Tests for the DetailPanel feature — behavior-focused (loads + interactions). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DetailPanel } from '../index'

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

  it('shows the A/B correction and re-analyze actions', async () => {
    render(<DetailPanel clipId={1} onClose={() => {}} />)
    expect(await screen.findByRole('button', { name: /A-roll \(narration\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /B-roll \(visual\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument()
    // one-click "fix A/B type and re-run" action
    expect(screen.getByRole('button', { name: /& re-analyze/ })).toBeInTheDocument()
  })
})
