/** Tests for the Gallery feature — controlled thumbnail grid. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Gallery } from '../index'

const MOCK_CLIPS = [
  { id: 1, source_path: '/media/vlog/2024-06/a-roll_01.mp4', roll_type: 'a' as const, thumbnail_path: '/thumbnails/1.jpg', duration_s: 45, tags: [], created_at: '2024-06-15T10:30:00Z' },
  { id: 2, source_path: '/media/vlog/2024-06/b-roll_01.mp4', roll_type: 'b' as const, thumbnail_path: '/thumbnails/2.jpg', duration_s: 120, tags: [], created_at: '2024-06-15T11:00:00Z' },
  { id: 3, source_path: '/media/vlog/2024-06/a-roll_02.mp4', roll_type: 'a' as const, thumbnail_path: null, duration_s: 0, tags: [], created_at: '2024-06-15T12:00:00Z' },
]

describe('Gallery', () => {
  it('renders clips as ThumbnailCard components in a grid', async () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    await waitFor(() => {
      expect(screen.getByText('a-roll_01.mp4')).toBeInTheDocument()
    })
  })

  it('renders the correct number of clip cards', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    expect(cards.length).toBe(3)
  })

  it('shows empty state when clips array is empty', () => {
    render(<Gallery clips={[]} selectedClipId={null} onSelect={() => {}} />)
    expect(screen.getByText(/No clips yet/i)).toBeInTheDocument()
  })

  it('shows empty state with helpful message for zero clips', () => {
    render(<Gallery clips={[]} selectedClipId={null} onSelect={() => {}} />)
    expect(screen.getByText(/No clips yet/i)).toBeInTheDocument()
  })

  it('calls onSelect with clipId when a card is clicked', async () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    await userEvent.click(screen.getByText('a-roll_01.mp4'))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('calls onSelect with different clipId for another card', async () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    await userEvent.click(screen.getByText('b-roll_01.mp4'))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('applies selected ring to the currently selected clip', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={2} onSelect={onSelect} />)
    const secondCard = document.querySelectorAll('[data-clip-id]')[1] as HTMLElement | null
    expect(secondCard).toHaveClass('ring-2')
  })

  it('does not apply selected ring to unselected clips', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={2} onSelect={onSelect} />)
    const firstCard = document.querySelectorAll('[data-clip-id]')[0] as HTMLElement | null
    expect(firstCard).not.toHaveClass('ring-2')
  })

  it('renders A-roll badge for clips with roll_type "a"', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const badgeSpans = document.querySelectorAll('span[class*="rounded-full"]')
    let foundABadge = false
    for (const span of badgeSpans) {
      if ((span.textContent?.trim() || '') === 'A-roll') foundABadge = true
    }
    expect(foundABadge).toBe(true)
  })

  it('renders B-roll badge for clips with roll_type "b"', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const badgeSpans = document.querySelectorAll('span[class*="rounded-full"]')
    let foundBBadge = false
    for (const span of badgeSpans) {
      if ((span.textContent?.trim() || '') === 'B-roll') foundBBadge = true
    }
    expect(foundBBadge).toBe(true)
  })

  it('renders duration label for clips with duration > 0', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    expect(screen.getByText('0:45')).toBeInTheDocument()
  })

  it('renders duration "2:00" for clip with 120 seconds', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    expect(screen.getByText('2:00')).toBeInTheDocument()
  })

  it('does not render duration for clip with duration 0', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    // clip with id=3 has duration_s: 0, so no duration label should appear
    // The gallery maps clips to ThumbnailCard with duration from clip data
  })

  it('renders thumbnails when thumbnail_path is provided', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const imgs = document.querySelectorAll('img')
    expect(imgs.length).toBeGreaterThanOrEqual(2) // clips 1 and 2 have thumbnail_path
  })

  it('renders placeholder for clip without thumbnail', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    // Clip 3 has thumbnail_path: null, so it should show a placeholder icon (film strip)
    const imgs = document.querySelectorAll('img')
    // Only clips 1 and 2 have thumbnails, so there should be exactly 2 images
    expect(imgs.length).toBe(2)
  })

  it('renders with responsive grid classes', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    // The gallery uses a grid with responsive breakpoints: 2→3→4→5 columns
    const grid = document.querySelector('div[class*="grid"]') as HTMLElement | null
    expect(grid).toBeTruthy()
  })

  it('renders grid div as wrapper', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    expect(document.querySelector('div[class*="grid"]')).toBeTruthy()
  })

  it('uses grid-cols-2 as base responsive class', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const grid = document.querySelector('div[class*="grid"]') as HTMLElement | null
    expect(grid?.className).toContain('grid-cols-2')
  })

  it('applies overflow-y-auto class to gallery container', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const container = document.querySelector('div[class*="overflow-y-auto"]') as HTMLElement | null
    expect(container?.className).toContain('overflow-y-auto')
  })

  it('renders with p-4 padding on the gallery container', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const container = document.querySelector('div[class*="overflow-y-auto"]') as HTMLElement | null
    expect(container?.className).toContain('p-4')
  })

  it('groups clips into one date-headed section per capture date', () => {
    const onSelect = vi.fn()
    const clips = [
      { id: 1, source_path: '/v/a.mp4', roll_type: 'a' as const, thumbnail_path: null, duration_s: 1, tags: [], capture_time: '2026-04-25T08:00:00Z' },
      { id: 2, source_path: '/v/b.mp4', roll_type: 'b' as const, thumbnail_path: null, duration_s: 1, tags: [], capture_time: '2026-05-11T08:00:00Z' },
      { id: 3, source_path: '/v/c.mp4', roll_type: 'a' as const, thumbnail_path: null, duration_s: 1, tags: [], capture_time: '2026-05-11T09:00:00Z' },
    ]
    render(<Gallery clips={clips} selectedClipId={null} onSelect={onSelect} />)

    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings.map((h) => h.textContent)).toEqual(['2026/04/251', '2026/05/112'])
  })

  it('prefers capture_time over created_at for grouping', () => {
    const onSelect = vi.fn()
    const clips = [
      { id: 1, source_path: '/v/a.mp4', roll_type: 'a' as const, thumbnail_path: null, duration_s: 1, tags: [], capture_time: '2026-04-25T08:00:00Z', created_at: '2024-01-01T00:00:00Z' },
    ]
    render(<Gallery clips={clips} selectedClipId={null} onSelect={onSelect} />)
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('2026/04/251')
  })

  it('renders clips with their source path as title', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    // The clip card carries its source path as a title (date-group headers also
    // have titles, so query the clip specifically rather than the first [title]).
    expect(screen.getByTitle('/media/vlog/2024-06/a-roll_01.mp4')).toBeInTheDocument()
  })

  it('renders film strip placeholder icon for clips without thumbnails', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    // The placeholder is a film strip icon SVG — check for its presence in the clip without thumbnail
    // Clip 3 has no thumbnail, so it should render a placeholder div with SVG icon
    const allSvg = document.querySelectorAll('svg')
    // There should be at least one SVG (the film strip placeholder for clip 3)
    expect(allSvg.length).toBeGreaterThanOrEqual(1)
  })

  it('passes clipId as data-clip-id attribute to each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    expect(cards[0]).toHaveAttribute('data-clip-id', '1')
    expect(cards[1]).toHaveAttribute('data-clip-id', '2')
    expect(cards[2]).toHaveAttribute('data-clip-id', '3')
  })

  it('renders with relative class on each card root div', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('relative')
    }
  })

  it('renders with rounded-lg class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('rounded-lg')
    }
  })

  it('renders overflow-hidden class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('overflow-hidden')
    }
  })

  it('renders group class on each card for hover effects', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('group')
    }
  })

  it('renders cursor-pointer class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('cursor-pointer')
    }
  })

  it('renders flex-col class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('flex-col')
    }
  })

  it('renders with border-[--border] class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('border-[--border]')
    }
  })

  it('renders with hover:border-[--border-strong] class', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card.className).toContain('hover:border-[--border-strong]')
    }
  })

  it('renders with border class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card).toHaveClass('border')
    }
  })

  it('renders with transition-all class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card.className).toContain('transition-all')
    }
  })

  it('renders with duration-200 class on each card', () => {
    const onSelect = vi.fn()
    render(<Gallery clips={MOCK_CLIPS} selectedClipId={null} onSelect={onSelect} />)
    const cards = document.querySelectorAll('[data-clip-id]')
    for (const card of cards) {
      expect(card.className).toContain('duration-200')
    }
  })

})
