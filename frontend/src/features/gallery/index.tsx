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

// ── Skeleton placeholder (shimmer effect) ───────────────────────

function SkeletonCard() {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-[--border] bg-[--surface-1]">
      <div className="w-full pb-[56.25%] bg-[--surface-2] animate-pulse" />
      <div className="px-3 py-2">
        <div className="h-3 w-3/4 rounded bg-[--surface-2] animate-pulse" />
      </div>
    </div>
  )
}

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
}

export function Gallery({ clips, selectedClipId, onSelect }: GalleryProps) {
  if (clips.length === 0) return <EmptyState />

  return (
    <div className="grid flex-1 grid-cols-2 gap-3 overflow-y-auto p-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {clips.map((clip) => (
        <ThumbnailCard
          key={clip.id}
          clipId={clip.id}
          sourcePath={clip.source_path}
          rollType={(clip.roll_type === 'a' ? 'a' : clip.roll_type === 'b' ? 'b' : undefined)}
          duration={clip.duration_s ?? undefined}
          thumbnailUrl={(typeof clip.thumbnail_path === 'string' && clip.thumbnail_path) || undefined}
          isSelected={selectedClipId === clip.id}
          onClick={() => onSelect(clip.id)}
        />
      ))}
    </div>
  )
}
