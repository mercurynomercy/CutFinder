/** Gallery feature — thumbnail wall with responsive grid layout.

Accepts clips as props (controlled mode) so the parent can manage
loading/error state and filtering.  Renders a 16:9 thumbnail grid
(2→3→4→5 columns at sm/md/lg/xl breakpoints).  Supports:
- Loading skeleton state (shimmer placeholders)
- Empty state with helpful messaging when no clips exist
- Click-to-select for opening the detail panel (emits `onSelect` callback)

Usage:
  <Gallery clips={clips} selectedClipId={selected} onSelect={(id) => setSelected(id)} />
*/

import type { ClipSummary } from '@/api/client'
import { ThumbnailCard } from '@/components/ThumbnailCard'

// ── Empty state component ───────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-center">
        {/* Film icon */}
        <svg className="mx-auto h-16 w-16 text-[--text-muted]" fill="none" viewBox="0 0 24 24">
          <path
            stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
          />
        </svg>
        <h3 className="mt-4 text-lg font-medium text-[--text-primary]">No clips yet</h3>
        <p className="mt-1 text-sm text-[--text-muted]">
          Add source folders and run a scan to see your footage here.
        </p>
      </div>
    </div>
  )
}

// ── Main Gallery component (controlled) ───────────────

export interface GalleryProps {
  /** Clips to render. Pass empty array + loading=true for skeleton state. */
  clips: ClipSummary[]
  /** Currently selected clip id (highlights the matching card). */
  selectedClipId: number | null
  /** Called when a thumbnail card is clicked; receives the clip id. */
  onSelect: (clipId: number) => void
  /** Called when a card's re-analyze button is clicked; receives the clip id. */
  onReanalyze?: (clipId: number) => void
  /** Set of clip ids currently being re-analyzed (spins their icon). */
  reanalyzingIds?: Set<number>
}

// ── Date grouping ───────────────────────────────────────────────
// Group key = the clip's capture date (falling back to created_at), matching
// the date shown on each card. Clips arrive pre-sorted by date, so iterating in
// order yields contiguous, correctly-ordered groups.

const UNKNOWN_DATE = '未知日期'

function dateKey(clip: ClipSummary): string {
  const iso = clip.capture_time || clip.created_at
  return iso ? iso.slice(0, 10) : UNKNOWN_DATE
}

function groupByDate(clips: ClipSummary[]): { key: string; label: string; items: ClipSummary[] }[] {
  const groups: { key: string; label: string; items: ClipSummary[] }[] = []
  const byKey = new Map<string, ClipSummary[]>()

  for (const clip of clips) {
    const key = dateKey(clip)
    let items = byKey.get(key)
    if (!items) {
      items = []
      byKey.set(key, items)
      groups.push({ key, label: key === UNKNOWN_DATE ? UNKNOWN_DATE : key.replace(/-/g, '/'), items })
    }
    items.push(clip)
  }

  return groups
}

export function Gallery({ clips, selectedClipId, onSelect, onReanalyze, reanalyzingIds }: GalleryProps) {
  if (clips.length === 0) return <EmptyState />

  const groups = groupByDate(clips)

  return (
    <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-4">
      {groups.map(({ key, label, items }) => (
        <section key={key}>
          <h2 className="sticky top-0 z-10 mb-3 flex items-baseline gap-2 bg-[--bg-canvas]/95 py-1 backdrop-blur-sm">
            <span className="text-sm font-semibold text-[--text-primary]">{label}</span>
            <span className="text-xs text-[--text-muted]">{items.length}</span>
          </h2>
          <div className="grid auto-rows-min grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {items.map((clip) => (
              <ThumbnailCard
                key={clip.id}
                clipId={clip.id}
                sourcePath={clip.source_path}
                rollType={(clip.roll_type === 'a' ? 'a' : clip.roll_type === 'b' ? 'b' : undefined)}
                duration={clip.duration_s ?? undefined}
                thumbnailUrl={(typeof clip.thumbnail_path === 'string' && clip.thumbnail_path) || undefined}
                status={clip.status}
                summary={clip.summary || clip.description || undefined}
                tags={clip.tags?.map((t) => t.name)}
                captureTime={clip.capture_time}
                isSelected={selectedClipId === clip.id}
                onClick={() => onSelect(clip.id)}
                onReanalyze={onReanalyze ? () => onReanalyze(clip.id) : undefined}
                reanalyzing={reanalyzingIds?.has(clip.id)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
