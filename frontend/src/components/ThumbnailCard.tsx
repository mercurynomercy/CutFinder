/** Thumbnail card component for the gallery grid.

Displays a 16:9 thumbnail image with hover scale effect, selection ring,
A/B roll badge overlay, and optional duration label.
*/

import * as React from 'react'

import { Badge } from '@/components/ChipBadge'
import { cn } from '@/lib/cn'

export interface ThumbnailCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Thumbnail image URL or path */
  thumbnailUrl?: string | null
  /** Original clip source file path (for alt text) */
  sourcePath: string
  /** Clip id for click handler */
  clipId: number
  /** A/B roll type badge display */
  rollType?: 'a' | 'b'
  /** Clip duration in seconds (displayed as label) */
  duration?: number | null
  /** Whether the card is selected (highlighted with ring) */
  isSelected?: boolean
  /** Processing status — 'partial' shows a "needs re-analyze" marker */
  status?: string
}

const ThumbnailCard = React.forwardRef<HTMLDivElement, ThumbnailCardProps>(
  (
    { thumbnailUrl, sourcePath, clipId, rollType, duration, isSelected = false, status, className, ...props },
    ref,
  ) => {
    const formatDuration = (s: number) => {
      const min = Math.floor(s / 60)
      const sec = s % 60
      return `${min}:${sec.toString().padStart(2, '0')}`
    }

    return (
      <div
        ref={ref}
        data-clip-id={clipId}
        className={cn(
          'group relative flex cursor-pointer flex-col overflow-hidden rounded-lg',
          'border border-[--border] bg-[--surface-1]',
          // Hover scale effect (handled by CSS transition + group hover)
          'transition-all duration-200 ease-out',
          isSelected ? 'ring-2 ring-[--primary]' : 'hover:border-[--border-strong] hover:shadow-lg',
          className,
        )}
        {...props}
      >
        {/* Thumbnail image — 16:9 aspect ratio */}
        <div className="relative w-full pb-[56.25%]"> {/* 16:9 = 9/16 = 56.25% */}
          {thumbnailUrl ? (
            <img
              src={thumbnailUrl.startsWith('/') || thumbnailUrl.startsWith('http') ? thumbnailUrl : `/api/thumbnails/${clipId}`}
              alt={sourcePath}
              className="absolute inset-0 h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
              loading="lazy"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-[--surface-2]">
              {/* Placeholder icon — film strip */}
              <svg className="h-8 w-8 text-[--text-muted]" fill="none" viewBox="0 0 24 24">
                <path
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"
                />
              </svg>
            </div>
          )}

          {/* A/B roll badge overlay (top-left) */}
          {rollType && (
            <div className="absolute left-2 top-2">
              <Badge type={rollType} />
            </div>
          )}

          {/* "Partial" marker (bottom-left) — AI analysis failed, can re-analyze */}
          {status === 'partial' && (
            <div
              className="absolute bottom-2 left-2 flex items-center gap-1 rounded bg-[--warning] px-1.5 py-0.5 text-[10px] font-semibold text-black"
              title="AI 分析未完成，可重新分析"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v3.75m0 3.75h.008M10.34 3.94l-7.6 13.16A1.5 1.5 0 004.04 19.5h15.92a1.5 1.5 0 001.3-2.4L13.66 3.94a1.5 1.5 0 00-2.6 0z" />
              </svg>
              部分
            </div>
          )}

          {/* Duration label (bottom-right) */}
          {duration !== null && duration !== undefined ? (
            <div className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs font-medium tabular-numbers">
              {formatDuration(duration)}
            </div>
          ) : null}

          {/* Selection indicator (top-right) */}
          {isSelected && (
            <div className="absolute right-2 top-2 rounded-full bg-[--primary] p-1">
              <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
          )}
        </div>

        {/* Info row (source path truncated, roll type) */}
        <div className="flex items-center justify-between px-3 py-2">
          <p className="max-w-[70%] truncate text-xs text-[--text-secondary]" title={sourcePath}>
            {sourcePath.split('/').pop() || sourcePath}
          </p>
        </div>
      </div>
    )
  },
)
ThumbnailCard.displayName = 'ThumbnailCard'

export { ThumbnailCard }
