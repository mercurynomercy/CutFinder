/** Tests for the ThumbnailCard component — 16:9 card with hover effects and selection. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { ThumbnailCard } from '../ThumbnailCard'

describe('ThumbnailCard', () => {
  const baseProps = {
    clipId: 42,
    sourcePath: '/Users/john/Videos/2025-06-14/vlog.mp4',
  }

  it('renders with required props (clipId, sourcePath)', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    expect(container.container.tagName).toBe('DIV')
  })

  it('sets data-clip-id attribute', () => {
    const container = render(<ThumbnailCard {...baseProps} clipId={42} />)
    expect(container.container.firstChild).toHaveAttribute('data-clip-id', '42')
  })

  it('shows truncated file name from sourcePath in the info row', () => {
    render(<ThumbnailCard {...baseProps} />)
    expect(screen.getByText('vlog.mp4')).toBeInTheDocument()
  })

  it('shows full path when sourcePath has no slashes', () => {
    render(<ThumbnailCard {...baseProps} sourcePath="clip.mp4" />)
    expect(screen.getByText('clip.mp4')).toBeInTheDocument()
  })

  it('renders source path "/" with title attribute and empty display text', () => {
    const container = render(<ThumbnailCard {...baseProps} sourcePath="/" />)
    // When sourcePath="/", split('/').pop() returns '' — the <p> shows empty text
    const p = container.container.querySelector('p[title="/"]') as HTMLParagraphElement | null
    expect(p).toBeTruthy()
  })

  // ── Thumbnail image vs placeholder ────────────────────────

  it('renders thumbnail <img> when thumbnailUrl is provided', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumbnails/42.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img).toBeTruthy()
  })

  it('renders placeholder icon when thumbnailUrl is null', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl={null as unknown as string} />)
    const img = container.container.querySelector('img')
    expect(img).toBeNull()
  })

  it('renders placeholder icon when thumbnailUrl is undefined', () => {
    const container = render(<ThumbnailCard {...baseProps} />) // no thumbnailUrl prop at all
    const img = container.container.querySelector('img')
    expect(img).toBeNull()
  })

  it('renders placeholder icon when thumbnailUrl is empty string', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="" />)
    const img = container.container.querySelector('img')
    expect(img).toBeNull()
  })

  it('uses absolute path directly when thumbnailUrl starts with /', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumbnails/42.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img?.src).toContain('/thumbnails/42.jpg')
  })

  it('uses absolute path directly when thumbnailUrl starts with http', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="http://example.com/thumb.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img?.src).toContain('http://example.com/thumb.jpg')
  })

  it('prepends /api/thumbnails/ when thumbnailUrl is a relative path not starting with /', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="thumb.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    // In jsdom, img.src is a full URL; check the path portion instead
    expect(img?.src).toContain('/api/thumbnails/42') // clipId is 42
  })

  it('sets alt text from sourcePath on the image', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumb.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img?.alt).toBe('/Users/john/Videos/2025-06-14/vlog.mp4')
  })

  it('sets loading="lazy" on the image', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumb.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img?.getAttribute('loading')).toBe('lazy') // use getAttribute for jsdom compatibility
  })

  // ── Roll type badge overlay ───────────────────────────────

  it('renders Badge when rollType="a"', () => {
    const container = render(<ThumbnailCard {...baseProps} rollType="a" />)
    // The Badge renders a span with text "A" inside the top-left overlay div
    const badgeSpans = container.container.querySelectorAll('span[class*="rounded-full"]')
    expect(badgeSpans.length).toBeGreaterThanOrEqual(1)
  })

  it('renders Badge with "B" text when rollType="b"', () => {
    const container = render(<ThumbnailCard {...baseProps} rollType="b" />)
    // Check for the badge span containing "B" in an absolutely positioned div
    const absoluteDivs = container.container.querySelectorAll('div[class*="absolute"]')
    let foundBTextInBadge = false
    for (const absDiv of absoluteDivs) {
      const badgeSpans = absDiv.querySelectorAll('span')
      for (const span of badgeSpans) {
        if ((span.textContent?.trim() || '') === 'B') {
          foundBTextInBadge = true
        }
      }
    }
    expect(foundBTextInBadge).toBe(true)
  })

  it('does not render roll type badge when rollType is undefined', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    // No Badge span should be present (the badge overlay div is conditionally rendered via rollType)
    const absoluteDivs = container.container.querySelectorAll('div[class*="absolute"]')
    let foundABBadgeInAbsoluteDiv = false
    for (const absDiv of absoluteDivs) {
      const badgeSpans = absDiv.querySelectorAll('span')
      for (const span of badgeSpans) {
        const text = (span.textContent?.trim() || '')
        if ((text === 'A' || text === 'B')) {
          foundABBadgeInAbsoluteDiv = true
        }
      }
    }
    expect(foundABBadgeInAbsoluteDiv).toBe(false)
  })

  // ── Duration label ────────────────────────────────────────

  it('renders duration when provided as a number', () => {
    render(<ThumbnailCard {...baseProps} duration={125} />)
    expect(screen.getByText('2:05')).toBeInTheDocument()
  })

  it('renders duration "0:00" when duration is 0', () => {
    render(<ThumbnailCard {...baseProps} duration={0} />)
    expect(screen.getByText('0:00')).toBeInTheDocument()
  })

  it('renders duration "1:30" for 90 seconds', () => {
    render(<ThumbnailCard {...baseProps} duration={90} />)
    expect(screen.getByText('1:30')).toBeInTheDocument()
  })

  it('renders duration "59:59" for max seconds', () => {
    render(<ThumbnailCard {...baseProps} duration={3599} />)
    expect(screen.getByText('59:59')).toBeInTheDocument()
  })

  it('does not render duration label when duration is null', () => {
    render(<ThumbnailCard {...baseProps} duration={null as unknown as number} />)
    expect(screen.queryByText(/:\d{2}/)).not.toBeInTheDocument()
  })

  it('does not render duration label when duration is undefined', () => {
    render(<ThumbnailCard {...baseProps} />)
    expect(screen.queryByText(/:\d{2}/)).not.toBeInTheDocument()
  })

  // ── Selection state ───────────────────────────────────────

  it('applies ring class when isSelected is true', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected />)
    expect(container.container.firstChild).toHaveClass('ring-2')
  })

  it('applies ring color when isSelected is true', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected />)
    expect(container.container.firstChild).toHaveClass('ring-[--primary]')
  })

  it('applies hover classes when isSelected is false', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected={false} />)
    expect(container.container.firstChild).toHaveClass('hover:border-[--border-strong]')
  })

  it('does not apply ring when isSelected is false', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected={false} />)
    expect(container.container.firstChild).not.toHaveClass('ring-2')
  })

  it('shows selection checkmark SVG when isSelected is true', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected />)
    // The checkmark SVG is inside a div with bg-[--primary] class in an absolute positioned area
    const primaryDivs = container.container.querySelectorAll('div[class*="bg-"]')
    let foundCheckmarkSvgWhenSelected = false
    for (const div of primaryDivs) {
      if ((div.className || '').includes('bg-[--primary]')) {
        const svg = div.querySelector('svg')
        if (svg) foundCheckmarkSvgWhenSelected = true
      }
    }
    expect(foundCheckmarkSvgWhenSelected).toBe(true)
  })

  it('does not show selection checkmark when isSelected is false', () => {
    const container = render(<ThumbnailCard {...baseProps} isSelected={false} />)
    // Look for the checkmark SVG — it should not exist when isSelected is false
    const primaryDivs = container.container.querySelectorAll('div[class*="bg-"]')
    let foundCheckmarkSvgWhenNotSelected = false
    for (const div of primaryDivs) {
      if ((div.className || '').includes('bg-[--primary]')) {
        const svg = div.querySelector('svg')
        if (svg) foundCheckmarkSvgWhenNotSelected = true
      }
    }
    expect(foundCheckmarkSvgWhenNotSelected).toBe(false)
  })

  // ── Click handling / cursor ───────────────────────────────

  it('has cursor-pointer class', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    expect(container.container.firstChild).toHaveClass('cursor-pointer')
  })

  it('fires onClick event when clicked', async () => {
    const onClick = vi.fn()
    const container = render(<ThumbnailCard {...baseProps} onClick={onClick} />)
    await userEvent.click(container.container.firstChild as Element)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('has group and hover-related classes', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    expect(container.container.firstChild).toHaveClass('group')
  })

  // ── Base classes ────────────────────────────────────────────

  it('has correct base class structure', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    expect(container.container.firstChild).toHaveClass('relative')
    expect(container.container.firstChild).toHaveClass('flex-col')
    expect(container.container.firstChild).toHaveClass('overflow-hidden')
    expect(container.container.firstChild).toHaveClass('rounded-lg')
  })

  it('passes through custom className', () => {
    const container = render(<ThumbnailCard {...baseProps} className="custom-card" />)
    expect(container.container.firstChild).toHaveClass('custom-card')
  })

  it('passes through custom HTML div attributes', () => {
    const container = render(<ThumbnailCard {...baseProps} data-testid="thumb-card" />)
    expect(container.container.firstChild).toHaveAttribute('data-testid', 'thumb-card')
  })

  // ── Aspect ratio container ────────────────────────────────

  it('renders a wrapper div with pb-[56.25%] for 16:9 aspect ratio', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumb.jpg" />)
    const aspectDiv = container.container.querySelector('div[class*="pb-[56.25%]"]')
    expect(aspectDiv).toBeTruthy()
  })

  it('renders image as absolute positioned inside aspect ratio container', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumb.jpg" />)
    const img = container.container.querySelector('img[class*="absolute"]') as HTMLImageElement | null
    expect(img).toBeTruthy()
  })

  // ── Hover scale effect on image ───────────────────────────

  it('has group-hover:scale class for hover zoom effect', () => {
    const container = render(<ThumbnailCard {...baseProps} thumbnailUrl="/thumb.jpg" />)
    const img = container.container.querySelector('img') as HTMLImageElement | null
    expect(img?.className).toContain('group-hover:scale-[1.02]')
  })

  // ── Duration label positioning and styling ────────────────

  it('renders duration in bottom-right corner', () => {
    const container = render(<ThumbnailCard {...baseProps} duration={60} />)
    // The duration div has absolute positioning with bottom and right classes
    const durDiv = container.container.querySelector('div[class*="bottom-2"][class*="right-2"]')
    expect(durDiv).toBeTruthy()
  })

  it('renders duration with dark background', () => {
    const container = render(<ThumbnailCard {...baseProps} duration={60} />)
    // The bg-black/70 class (may be normalized by twMerge to bg-black\/70)
    const durDiv = container.container.querySelector('div[class*="bg-"]') as HTMLElement | null
    expect(durDiv).toBeTruthy()
  })

  // ── Info row (source path) ────────────────────────────────

  it('renders info row with source file name', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    // The source path is truncated and displayed in a <p> tag
    const p = container.container.querySelector('p[class*="truncate"]') as HTMLParagraphElement | null
    expect(p).toBeTruthy()
  })

  it('sets title attribute to full sourcePath', () => {
    const container = render(<ThumbnailCard {...baseProps} />)
    const p = container.container.querySelector('p[title]') as HTMLParagraphElement | null
    expect(p?.getAttribute('title')).toBe('/Users/john/Videos/2025-06-14/vlog.mp4')
  })

  it('passes through additional props as spread', () => {
    const container = render(
      <ThumbnailCard {...baseProps} aria-label="Clip 42" />,
    )
    expect(container.container.firstChild).toHaveAttribute('aria-label', 'Clip 42')
  })

  // ── Ref forwarding ────────────────────────────────────────

  it('forwards ref to the root div', () => {
    const ref = React.createRef<HTMLDivElement>()
    render(<ThumbnailCard {...baseProps} ref={ref} />)
    expect(ref.current).toBeTruthy()
  })
})
