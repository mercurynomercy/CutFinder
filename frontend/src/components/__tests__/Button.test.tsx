/** Tests for the Button component — CVA-based button with variants and sizes. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '../Button'

describe('Button', () => {
  it('renders as a <button> element with default variant (primary)', () => {
    render(<Button>Hello</Button>)
    expect(screen.getByRole('button', { name: 'Hello' })).toBeInTheDocument()
  })

  it('renders children content correctly', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button', { name: 'Click me' })).toHaveTextContent('Click me')
  })

  it('passes through custom className', () => {
    const container = render(<Button className="custom-extra">Btn</Button>)
    expect(container.container.firstChild).toHaveClass('custom-extra')
  })

  it('passes through custom data attributes', () => {
    const container = render(<Button data-testid="my-btn" data-custom="val">Btn</Button>)
    expect(container.container.firstChild).toHaveAttribute('data-custom', 'val')
  })

  // ── Variants ───────────────────────────────────────────────

  const variantTests = [
    { name: 'primary', expectedClasses: ['bg-[--primary]', 'text-[--primary-fg]'] },
    { name: 'secondary', expectedClasses: ['bg-[--surface-2]', 'text-[--text-primary]'] },
    { name: 'ghost', expectedClasses: ['hover:bg-[--surface-2]', 'text-[--text-secondary]'] },
    { name: 'danger', expectedClasses: ['bg-[--error]', 'hover:bg-red-600'] },
  ]

  for (const { name, expectedClasses } of variantTests) {
    it(`applies correct classes for variant="${name}"`, () => {
      const container = render(<Button variant={name as 'primary' | 'secondary' | 'ghost' | 'danger'}>Btn</Button>)
      for (const cls of expectedClasses) {
        expect(container.container.firstChild).toHaveClass(cls.replace('bg-[', 'bg-[')) // twMerge may normalize
      }
    })

    it(`renders and is clickable for variant="${name}"`, async () => {
      const onClick = vi.fn()
      render(<Button variant={name as 'primary' | 'secondary' | 'ghost' | 'danger'} onClick={onClick}>Click</Button>)
      await userEvent.click(screen.getByRole('button', { name: 'Click' }))
      expect(onClick).toHaveBeenCalledTimes(1)
    })
  }

  // ── Sizes ────────────────────────────────────────────────

  const sizeTests = [
    { name: 'sm', expectedClasses: ['h-8'] },
    { name: 'md', expectedClasses: ['h-9'] },
    { name: 'lg', expectedClasses: ['h-10'] },
  ]

  for (const { name, expectedClasses } of sizeTests) {
    it(`applies correct classes for size="${name}"`, () => {
      const container = render(<Button size={name as 'sm' | 'md' | 'lg'}>Btn</Button>)
      for (const cls of expectedClasses) {
        expect(container.container.firstChild).toHaveClass(cls)
      }
    })

    it(`renders and is clickable for size="${name}"`, async () => {
      const onClick = vi.fn()
      render(<Button size={name as 'sm' | 'md' | 'lg'} onClick={onClick}>Click</Button>)
      await userEvent.click(screen.getByRole('button', { name: 'Click' }))
      expect(onClick).toHaveBeenCalledTimes(1)
    })
  }

  // ── Default variants ───────────────────────────────────────

  it('uses primary variant and md size by default', () => {
    const container = render(<Button>Default</Button>)
    expect(container.container.firstChild).toHaveClass('bg-[--primary]') // primary default variant
    expect(container.container.firstChild).toHaveClass('h-9') // md default size
  })

  it('is disabled when disabled prop is true', () => {
    const container = render(<Button disabled>Disabled</Button>)
    expect(container.container.firstChild).toBeDisabled()
  })

  it('does not fire click when disabled', async () => {
    const onClickDisabled = vi.fn()
    render(<Button disabled onClick={onClickDisabled}>Click</Button>)
    await userEvent.click(screen.getByRole('button', { name: 'Click' }))
    expect(onClickDisabled).not.toHaveBeenCalled()
  })

  it('supports combined variant and size', () => {
    const container = render(<Button variant="ghost" size="lg">Combo</Button>)
    expect(container.container.firstChild).toHaveClass('hover:bg-[--surface-2]') // ghost
    expect(container.container.firstChild).toHaveClass('h-10') // lg
  })

  it('passes through other HTML button attributes', () => {
    const container = render(
      <Button type="submit" aria-label="Submit form">Go</Button>,
    )
    const btn = container.container.firstChild as HTMLButtonElement
    expect(btn.type).toBe('submit')
    expect(btn.getAttribute('aria-label')).toBe('Submit form')
  })
})
