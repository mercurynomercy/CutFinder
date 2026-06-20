/** Thumbnail card component for the gallery grid.

Displays a 16:9 thumbnail image with hover scale effect, selection ring,
A/B roll badge overlay, and optional duration label.
*/

import * as React from 'react'

import { Badge } from '@/components/ChipBadge'
import { cn } from '@/lib/cn'
import { useI18n } from '@/i18n'

export interface ThumbnailCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Thumbnail image URL or path */
  thumbnailUrl?: string | null
  /** Original clip source file path (for alt text / fallback name) */
  sourcePath: string
  /** Library destination path — its basename is shown as the filename when present. */
  libraryPath?: string | null
  /** Clip id for click handler */
  clipId: number
  /** A/B/photo roll type badge display */
  rollType?: 'a' | 'b' | 'photo'
  /** Clip duration in seconds (displayed as label) */
  duration?: number | null
  /** Capture time ISO string (e.g. "2026-01-15T…") — displayed as YYYY-MM-DD */
  captureTime?: string | null
  /** Whether the card is selected (highlighted with ring) */
  isSelected?: boolean
  /** Processing status — 'partial' shows a "needs re-analyze" marker */
  status?: string
  /** AI summary (A-roll) or description (B-roll) — shown under the filename */
  summary?: string | null
  /** Tag names — shown as small chips under the summary */
  tags?: string[]
  /** When provided, shows a re-analyze button on the thumbnail (stops propagation). */
  onReanalyze?: () => void
  /** Whether this card is currently re-analyzing (spins the icon). */
  reanalyzing?: boolean
  /** When provided, shows a play/open button that opens the video (stops propagation). */
  onOpen?: () => void
  /** Whether the clip has keyframe suggestions (shows a corner badge). */
  hasKeyframes?: boolean
}

const ThumbnailCard = React.forwardRef<HTMLDivElement, ThumbnailCardProps>(
  (
    { thumbnailUrl, sourcePath, libraryPath, clipId, rollType, duration, captureTime, isSelected = false, status, summary, tags, onReanalyze, reanalyzing = false, onOpen, hasKeyframes = false, className, ...props },
    ref,
  ) => {
    const { t } = useI18n()
    // Prefer the renamed library copy's filename; fall back to the source name.
    const displayName = (libraryPath || sourcePath).split('/').pop() || sourcePath

    const formatDuration = (s: number) => {
      const min = Math.floor(s / 60)
      const sec = Math.floor(s % 60)
      return `${min}:${sec.toString().padStart(2, '0')}`
    }

    const formatCaptureDate = (iso: string) => {
      return iso.slice(0, 10).replace(/-/g, '/') // "2026-01-15" → "2026/01/15"
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
              src={/^(https?:)?\/\//.test(thumbnailUrl) ? thumbnailUrl : `/api/clips/${clipId}/thumbnail`}
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

          {/* Re-analyze button (top-left) — shown on hover, always for 'partial' */}
          {onReanalyze && (
            <button
              onClick={(e) => { e.stopPropagation(); onReanalyze() }}
              disabled={reanalyzing}
              title={reanalyzing ? t('card.reanalyzing') : t('card.reanalyze')}
              aria-label={t('card.reanalyze')}
              className={cn(
                'absolute left-2 top-2 rounded-md bg-black/60 p-1.5 text-white backdrop-blur-sm transition-opacity hover:bg-black/80 disabled:opacity-60',
                reanalyzing || status === 'partial' ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
              )}
            >
              <svg className={cn('h-4 w-4', reanalyzing && 'animate-spin')} fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
            </button>
          )}

          {/* Play / open button (centered) — shown on hover, opens the video */}
          {onOpen && (
            <button
              onClick={(e) => { e.stopPropagation(); onOpen() }}
              title={t('card.openVideo')}
              aria-label={t('card.openVideo')}
              className="absolute inset-0 m-auto flex h-11 w-11 items-center justify-center rounded-full bg-black/60 text-white opacity-0 backdrop-blur-sm transition-opacity hover:bg-black/80 group-hover:opacity-100"
            >
              <svg className="h-5 w-5 translate-x-px" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 5v14l11-7z" />
              </svg>
            </button>
          )}

          {/* "Partial" marker (bottom-left) — AI analysis failed, can re-analyze */}
          {status === 'partial' && (
            <div
              className="absolute bottom-2 left-2 flex items-center gap-1 rounded bg-amber-400 px-1.5 py-0.5 text-[10px] font-semibold text-black"
              title={t('card.partialTitle')}
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v3.75m0 3.75h.008M10.34 3.94l-7.6 13.16A1.5 1.5 0 004.04 19.5h15.92a1.5 1.5 0 001.3-2.4L13.66 3.94a1.5 1.5 0 00-2.6 0z" />
              </svg>
              {t('card.partial')}
            </div>
          )}

          {/* Keyframe-suggestions badge (top-right) — scissors mark */}
          {hasKeyframes && (
            <div
              className={cn(
                'absolute top-2 flex items-center rounded bg-black/60 p-1 text-white backdrop-blur-sm',
                isSelected ? 'right-9' : 'right-2',  // make room for the selection check
              )}
              title={t('card.hasKeyframes')}
              aria-label={t('card.hasKeyframes')}
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z" />
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m6.2 5.3 3.1 3.9" />
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m12.4 3.4 3.1 4" />
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
              </svg>
            </div>
          )}

          {/* Duration label (bottom-right) — not for photos (no playback time) */}
          {rollType !== 'photo' && duration !== null && duration !== undefined ? (
            <div className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white tabular-numbers">
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

        {/* Info row (filename, summary, tags) — flex-1 so the date pins to the
            card bottom and aligns across cards of differing tag/summary heights */}
        <div className="flex flex-1 flex-col gap-1.5 px-3 py-2">
          <div className="flex items-center gap-1.5">
            {rollType && (
              <Badge type={rollType} className="shrink-0 px-1.5">
                {rollType === 'photo' ? t('card.photo') : rollType === 'a' ? 'A-roll' : 'B-roll'}
              </Badge>
            )}
            <p className="truncate text-xs text-[--text-secondary]" title={libraryPath || sourcePath}>
              {displayName}
            </p>
          </div>

          {summary ? (
            <p className="line-clamp-2 text-[11px] leading-snug text-[--text-muted]" title={summary}>
              {summary}
            </p>
          ) : null}

          {tags && tags.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {tags.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="truncate rounded bg-[--surface-2] px-1.5 py-0.5 text-[10px] text-[--text-secondary]"
                >
                  {t}
                </span>
              ))}
              {tags.length > 3 ? (
                <span className="px-1 py-0.5 text-[10px] text-[--text-muted]">+{tags.length - 3}</span>
              ) : null}
            </div>
          ) : null}

          {captureTime && (
            <p className="mt-auto pt-1 text-right text-[10px] tabular-nums text-[--text-muted]">
              {formatCaptureDate(captureTime)}
            </p>
          )}
        </div>
      </div>
    )
  },
)
ThumbnailCard.displayName = 'ThumbnailCard'

export { ThumbnailCard }
