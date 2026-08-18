/** Tests for the LauncherPage — CutFinder's entry screen with 5 navigation cards. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LauncherPage } from '../index'

describe('LauncherPage', () => {
  it('renders all five navigation cards', () => {
    render(<LauncherPage theme="light" onToggleTheme={vi.fn()} onNavigate={vi.fn()} />)
    expect(screen.getByRole('button', { name: /library/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /task queue/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rough cut/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /subtitle export/i })).toBeInTheDocument()
  })

  it('navigates to the right screen when a card is clicked', async () => {
    const onNavigate = vi.fn()
    render(<LauncherPage theme="light" onToggleTheme={vi.fn()} onNavigate={onNavigate} />)

    await userEvent.click(screen.getByRole('button', { name: /library/i }))
    expect(onNavigate).toHaveBeenCalledWith('gallery')

    await userEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(onNavigate).toHaveBeenCalledWith('settings')

    await userEvent.click(screen.getByRole('button', { name: /task queue/i }))
    expect(onNavigate).toHaveBeenCalledWith('jobs')

    await userEvent.click(screen.getByRole('button', { name: /rough cut/i }))
    expect(onNavigate).toHaveBeenCalledWith('cutplan')

    await userEvent.click(screen.getByRole('button', { name: /subtitle export/i }))
    expect(onNavigate).toHaveBeenCalledWith('subtitles')
  })

  it('calls onToggleTheme when the theme button is clicked', async () => {
    const onToggleTheme = vi.fn()
    render(<LauncherPage theme="light" onToggleTheme={onToggleTheme} onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /switch to dark mode/i }))
    expect(onToggleTheme).toHaveBeenCalled()
  })
})
