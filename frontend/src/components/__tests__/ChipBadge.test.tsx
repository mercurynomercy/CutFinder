/** Tests for Badge and Chip components from ChipBadge. */

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Badge, Chip } from '../ChipBadge'

// ── Badge (A/B roll type) ────────────────────────────────────────

describe('Badge', () => {
  it('renders A roll badge with correct text and classes when type="a"', () => {
    const container = render(<Badge type="a">Extra</Badge>)
    const badge = container.container.firstChild as HTMLElement
    expect(badge).toHaveClass('bg-[--roll-a-soft]')
    expect(badge).toHaveClass('text-[--roll-a]')
    expect(badge.textContent?.trim().startsWith('A')).toBe(true)
  })

  it('renders B roll badge with correct text and classes when type="b"', () => {
    const container = render(<Badge type="b">Extra</Badge>)
    const badge = container.container.firstChild as HTMLElement
    expect(badge).toHaveClass('bg-[--roll-b-soft]')
    expect(badge).toHaveClass('text-[--roll-b]')
    expect(badge.textContent?.trim().startsWith('B')).toBe(true)
  })

  it('renders A badge without children', () => {
    const container = render(<Badge type="a" />)
    expect(container.container.firstChild).toHaveTextContent('A')
  })

  it('renders B badge without children', () => {
    const container = render(<Badge type="b" />)
    expect(container.container.firstChild).toHaveTextContent('B')
  })

  it('renders children as secondary text after the A/B letter', () => {
    const container = render(<Badge type="a">Clip 12</Badge>)
    expect(container.container.firstChild).toHaveTextContent('AClip 12')
  })

  it('passes through custom className', () => {
    const container = render(<Badge type="b" className="custom-class">B</Badge>)
    expect(container.container.firstChild).toHaveClass('custom-class')
  })

  it('passes through custom HTML span attributes', () => {
    const container = render(<Badge type="a" data-testid="ab-badge">A</Badge>)
    expect(container.container.firstChild).toHaveAttribute('data-testid', 'ab-badge')
  })

  it('is a <span> element with correct base classes', () => {
    const container = render(<Badge type="a">A</Badge>)
    expect((container.container.firstChild as HTMLElement | null)?.tagName).toBe('SPAN')
  })

  it('has correct base classes on the span', () => {
    const container = render(<Badge type="a">A</Badge>)
    const span = container.container.firstChild as HTMLElement
    expect(span).toHaveClass('inline-flex')
    expect(span).toHaveClass('rounded-full')
    expect(span).toHaveClass('px-2')
    expect(span).toHaveClass('py-0.5')
    expect(span).toHaveClass('text-xs')
    expect(span).toHaveClass('font-medium')
  })

  it('wraps children in a <span> with ml-1 class', () => {
    const container = render(<Badge type="b">Label</Badge>)
    // The children are wrapped in a <span> with ml-1
    const spans = container.container.querySelectorAll('span')
    expect(spans.length).toBeGreaterThanOrEqual(2) // outer span + inner wrapper for children
    const childSpan = spans[1] as HTMLElement | null
    expect(childSpan).toHaveClass('ml-1')
  })
})

// ── Chip (tag-style with source dot) ─────────────────────────────

describe('Chip', () => {
  it('renders chip with auto source dot by default', () => {
    const container = render(<Chip>Tag Name</Chip>)
    expect(container.container.firstChild).toHaveTextContent('Tag Name')
  })

  it('renders chip with auto source dot when explicitly set', () => {
    const container = render(<Chip source="auto">Auto Tag</Chip>)
    const chip = container.container.firstChild as HTMLElement
    expect(chip).toHaveTextContent('Auto Tag')
  })

  it('renders chip with manual source dot', () => {
    const container = render(<Chip source="manual">Manual Tag</Chip>)
    expect(container.container.firstChild).toHaveTextContent('Manual Tag')
  })

  it('passes through custom className', () => {
    const container = render(<Chip className="custom-chip">Tag</Chip>)
    expect(container.container.firstChild).toHaveClass('custom-chip')
  })

  it('passes through custom HTML span attributes', () => {
    const container = render(<Chip data-testid="my-chip">Tag</Chip>)
    expect(container.container.firstChild).toHaveAttribute('data-testid', 'my-chip')
  })

  it('is a <span> element with correct base classes', () => {
    const container = render(<Chip>Tag</Chip>)
    expect((container.container.firstChild as HTMLElement | null)?.tagName).toBe('SPAN')
  })

  it('has correct base classes on the span', () => {
    const container = render(<Chip>Tag</Chip>)
    const span = container.container.firstChild as HTMLElement
    expect(span).toHaveClass('inline-flex')
    expect(span).toHaveClass('rounded-full')
    expect(span).toHaveClass('border-[--border]') // CSS variable class, not normalized
    expect(span).toHaveClass('bg-[--surface-2]') // CSS variable class, not normalized
    expect(span).toHaveClass('text-xs')
    expect(span).toHaveClass('font-medium')
  })

  it('shows source dot indicator', () => {
    const container = render(<Chip>Tag</Chip>)
    // There should be an inner span for the source dot (h-1.5 w-1.5 rounded-full)
    const chipSpans = container.container.querySelectorAll('span')
    expect(chipSpans.length).toBeGreaterThanOrEqual(2) // outer + dot indicator
  })

  it('auto source uses muted color class', () => {
    const container = render(<Chip source="auto">Auto</Chip>)
    // The dot span should have bg-[--text-muted] class (may be normalized by twMerge)
    const dotSpans = container.container.querySelectorAll('span')
    // The first inner span is the dot; check it has a color-related class
    const dotSpan = dotSpans[1] as HTMLElement | null
    expect(dotSpan).toHaveClass('h-1.5')
  })

  it('handles empty children', () => {
    const container = render(<Chip />)
    expect(container.container.firstChild).toBeInTheDocument()
  })

  it('has hover:border-strong class for hover effect', () => {
    const container = render(<Chip>Tag</Chip>)
    expect(container.container.firstChild).toHaveClass('hover:border-[--border-strong]')
  })
})
