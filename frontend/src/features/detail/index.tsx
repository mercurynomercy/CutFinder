/** Detail panel feature — full-screen clip-detail view.

Displays clip metadata, read-only summary/description, tag editor (add/delete
tags with source indicators), collapsible transcript section, A/B roll
correction button, and re-analyze trigger with loading state.

Usage:
  <DetailPanel clipId={clipId} onClose={() => setSelectedClip(null)} />
*/

import React, { useCallback, useEffect, useState } from 'react'

import type { ClipDetail, TagItem, TranscriptData } from '@/api/client'
import { api } from '@/api/client'
import { Chip } from '@/components/ChipBadge'
import { Button } from '@/components/Button'
import { useI18n } from '@/i18n'

/** Format seconds as m:ss for cut-window timecodes. */
function fmtClock(s: number): string {
  const total = Math.max(0, Math.round(s))
  return `${Math.floor(total / 60)}:${(total % 60).toString().padStart(2, '0')}`
}

// ── Tag editor component (add/delete) ────────────────────────────

interface TagEditorProps {
  tags: TagItem[]
  onUpdate: (tags: TagItem[]) => Promise<void>
}

function TagEditor({ tags, onUpdate }: TagEditorProps) {
  const { t } = useI18n()
  const [newTag, setNewTag] = useState('')

  const handleAdd = async () => {
    const name = newTag.trim()
    if (!name) return

    try {
      await onUpdate([...tags.map((t) => ({ name: t.name, source: t.source })), { name, source: 'manual' as const }])
      setNewTag('')
    } catch (err) {
      console.error('Failed to add tag:', err)
    }
  }

  const handleDelete = async (index: number, _name: string) => {
    try {
      await onUpdate(tags.filter((_, i) => i !== index))
    } catch (err) {
      console.error('Failed to remove tag:', err)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleAdd()
  }

  return (
    <div className="space-y-2">
      {/* Existing tags */}
      {tags?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag, i) => (
            <Chip key={tag.name} source={tag.source}>
              {tag.name}
              <button
                onClick={() => handleDelete(i, tag.name)}
                className="ml-1 inline-flex text-[--text-muted] hover:text-[--error]"
                aria-label={t('detail.removeTag', { name: tag.name })}
              >
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24">
                  <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </Chip>
          ))}
        </div>
      )}

      {/* Add tag input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('detail.addTag')}
          className="flex-1 rounded-md border border-[--border] bg-[--surface-3] px-3 py-1.5 text-sm text-[--text-primary] placeholder:text-[--text-muted] outline-none transition-colors focus:border-[--primary]"
        />
        <Button size="sm" onClick={handleAdd} disabled={!newTag.trim()}>
          {t('detail.add')}
        </Button>
      </div>
    </div>
  )
}

// ── Shared accordion (one consistent style for all collapsible sections) ──

interface AccordionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function Accordion({ title, children, defaultOpen = false }: AccordionProps) {
  return (
    <details className="group" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium uppercase tracking-wider text-[--text-muted] transition-colors hover:text-[--text-secondary]">
        <svg className="h-3 w-3 shrink-0 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24">
          <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {title}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  )
}

// ── Collapsible transcript section ────────────────────────────────

interface TranscriptSectionProps {
  data: TranscriptData | undefined
}

function TranscriptSection({ data }: TranscriptSectionProps) {
  const { t } = useI18n()
  if (!data || !data.full_text.trim()) return null

  return (
    <Accordion title={t('detail.transcript')} defaultOpen>
      <div className="text-sm leading-relaxed text-[--text-secondary]">
        {data.full_text}

        {data.segments.length > 0 && (
          <div className="mt-3 space-y-1">
            {data.segments.slice(0, 20).map((seg, i) => (
              <div key={i} className="flex gap-2 text-xs">
                <span className="tabular-numbers text-[--text-muted] shrink-0">
                  {seg.start_s.toFixed(1)}s
                </span>
                <span>{seg.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Accordion>
  )
}

// ── Main Detail Panel component ────────────────────────────────

export interface DetailPanelProps {
  /** Clip id to display. When null/undefined, the panel is hidden. */
  clipId: number | null
  onClose: () => void
  /** Open the clip's video in its default app (macOS `open`). */
  onOpenPath?: (path: string) => void
}

export function DetailPanel({ clipId, onClose, onOpenPath }: DetailPanelProps) {
  const { t } = useI18n()
  const [clip, setClip] = useState<ClipDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const [reanalyzing, setReanalyzing] = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  // (Re)fetch the clip detail — reused after re-analyze / roll correction.
  const loadClip = useCallback((id: number) => {
    setLoading(true)
    setError(null)
    return api.getClip(id)
      .then((data) => {
        setClip(data)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)))
      })
      .finally(() => setLoading(false))
  }, [])

  // Close on Escape key press
  useEffect(() => {
    if (clipId === null) return

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [clipId, onClose])

  const captureDate = (() => {
    if (!clip?.capture_time) return null
    console.log('[DetailPanel] capture_time =', JSON.stringify(clip.capture_time))
    const d = new Date(clip.capture_time)
    if (isNaN(d.getTime())) return null
    const result = d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
    console.log('[DetailPanel] captureDate =', result)
    return result
  })()

  // Fetch clip detail when id changes
  useEffect(() => {
    if (clipId === null) return
    setClip(null)
    loadClip(clipId)
  }, [clipId, loadClip])

  // Trigger a re-analyze job, wait for it to finish, then refresh the panel.
  const runReanalyze = useCallback(async (id: number) => {
    const { job_id } = await api.reanalyzeClip(id)
    // Poll the job until it reaches a terminal state (cap at ~5 min).
    const deadline = Date.now() + 5 * 60_000
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      try {
        const job = await api.getJob(job_id)
        if (['done', 'failed', 'cancelled'].includes(job.status)) break
      } catch {
        // transient error — keep polling
      }
    }
    await loadClip(id)
  }, [loadClip])

  // Re-analyze this single clip (re-runs AI for its current A/B type).
  const handleReanalyze = async () => {
    if (!clip || reanalyzing) return
    setReanalyzing(true)
    try {
      await runReanalyze(clip.id)
    } catch (err) {
      console.error('Failed to re-analyze:', err)
    } finally {
      setReanalyzing(false)
    }
  }

  // Generate keyframe suggestions, wait for the job, then refresh the panel.
  const handleSuggestKeyframes = async () => {
    if (!clip || suggesting) return
    setSuggesting(true)
    try {
      const { job_id } = await api.suggestKeyframes(clip.id)
      const deadline = Date.now() + 5 * 60_000
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 1500))
        try {
          const job = await api.getJob(job_id)
          if (['done', 'failed', 'cancelled'].includes(job.status)) break
        } catch {
          // transient error — keep polling
        }
      }
      await loadClip(clip.id)
    } catch (err) {
      console.error('Failed to suggest keyframes:', err)
    } finally {
      setSuggesting(false)
    }
  }

  // Correct A/B roll classification
  const handleCorrectRoll = async (roll: 'a' | 'b') => {
    if (!clip) return

    try {
      const res = await api.correctRoll(clip.id, roll)
      setClip((prev) => prev ? { ...prev, roll_type: roll, library_path: res.library_path ?? prev.library_path } : null)
    } catch (err) {
      console.error('Failed to correct roll:', err)
    }
  }

  if (clipId === null || clipId === undefined) return null

  const displayFilename = clip ? (clip.library_path || clip.source_path).split('/').pop() || clip.source_path : ''

  return (
    <div className="flex h-screen w-full flex-col bg-[--bg-canvas] text-[--text-primary]">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[--border] bg-[--surface-1] px-6">
        <h1 className="text-sm font-semibold text-[--text-primary]">{t('detail.pageTitle')}</h1>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-[--text-muted] hover:bg-[--surface-3] hover:text-[--text-primary]"
          aria-label={t('detail.backToGallery')}
          title={t('detail.backToGallery')}
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-[--text-muted]">{t('detail.loadingClip')}</p>
        </div>
      ) : error ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-[--error]">{error.message}</p>
        </div>
      ) : clip ? (
        <>
          <div className="flex min-h-0 flex-1 overflow-hidden">
            {/* ── Left: video preview ─────────────────────── */}
            <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
              <div className="group relative aspect-video w-full overflow-hidden rounded-lg bg-black">
                {clip.thumbnail_path ? (
                  <img src={`/api/clips/${clip.id}/thumbnail`} alt="Thumbnail" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <svg className="h-10 w-10 text-[--text-muted]" fill="none" viewBox="0 0 24 24">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9A2.25 2.25 0 0013.5 5.25h-9A2.25 2.25 0 002.25 7.5v9A2.25 2.25 0 004.5 18.75z" />
                    </svg>
                  </div>
                )}
                {onOpenPath && (
                  <button
                    onClick={() => onOpenPath(clip.library_path || clip.source_path)}
                    title={t('detail.openVideo')}
                    aria-label={t('detail.openVideo')}
                    className="absolute inset-0 m-auto flex h-14 w-14 items-center justify-center rounded-full bg-black/60 text-white opacity-0 backdrop-blur-sm transition-opacity hover:bg-black/80 group-hover:opacity-100"
                  >
                    <svg className="h-7 w-7 translate-x-px" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </button>
                )}
              </div>

              <div>
                <p className="font-mono text-sm text-[--text-primary]">{displayFilename}</p>
                {clip.roll_type === 'a' && clip.summary && (
                  <p className="mt-1 text-sm text-[--text-secondary]">{clip.summary}</p>
                )}
                {(clip.roll_type === 'b' || clip.roll_type === 'photo') && clip.description && (
                  <p className="mt-1 text-sm text-[--text-secondary]">{clip.description}</p>
                )}
                {clip.tags?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {clip.tags.map((tag) => <Chip key={tag.name} source={tag.source}>{tag.name}</Chip>)}
                  </div>
                )}
              </div>

              <div className="mt-auto flex flex-wrap items-end justify-between gap-x-4 gap-y-1 border-t border-[--border] pt-3 text-xs text-[--text-muted]">
                {clip.library_path && (
                  <p className="break-all">
                    <span className="font-medium uppercase tracking-wider">{t('detail.fileDestination')}</span>
                    {': '}<span>{clip.library_path}</span>
                  </p>
                )}
                {captureDate && (
                  <p className="tabular-nums">
                    {clip.date_source === 'file' ? t('detail.captureDateFromFile') : t('detail.captureDate')}: {captureDate}
                  </p>
                )}
              </div>
            </div>

            {/* ── Right: detail drawer ─────────────────────── */}
            <aside className="flex w-[480px] shrink-0 flex-col gap-4 overflow-y-auto border-l border-[--border] bg-[--surface-1] p-5">
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                  {t('filters.tags')}
                </label>
                <TagEditor tags={clip.tags} onUpdate={async (next) => {
                  if (!clip) return
                  await api.setTags(clip.id, { tags: next })
                  setClip((prev) => prev ? { ...prev, tags: next } : null)
                }} />
              </div>

              {clip.roll_type !== 'photo' && (
                <div>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <label className="text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                      {t('detail.suggestedCuts')}
                    </label>
                    <button
                      onClick={handleSuggestKeyframes}
                      disabled={suggesting}
                      className="inline-flex items-center gap-1 rounded-md border border-[--border] px-2 py-0.5 text-[11px] font-medium text-[--text-secondary] transition-colors hover:text-[--text-primary] disabled:opacity-50"
                    >
                      <svg className={`h-3 w-3 ${suggesting ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24">
                        <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                      </svg>
                      {suggesting ? t('detail.suggesting') : t('detail.suggestKeyframes')}
                    </button>
                  </div>
                  {clip.keyframes && clip.keyframes.length > 0 ? (
                    <div className="space-y-2">
                      {clip.keyframes.map((k) => (
                        <div key={k.rank} className="flex gap-2 rounded-md border border-[--border] bg-[--surface-2] p-2">
                          <button
                            onClick={() => onOpenPath?.(clip.library_path || clip.source_path)}
                            title={t('detail.openVideo')}
                            className="relative h-12 w-20 shrink-0 overflow-hidden rounded bg-[--surface-3]"
                          >
                            {k.has_frame && (
                              <img src={`/api/clips/${clip.id}/keyframes/${k.rank}/image`} alt="" className="h-full w-full object-cover" />
                            )}
                          </button>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs tabular-nums text-[--text-secondary]">{fmtClock(k.start_s)}–{fmtClock(k.end_s)}</p>
                            {k.reason && <p className="line-clamp-2 text-[11px] leading-snug text-[--text-muted]" title={k.reason}>{k.reason}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[--text-muted]">{t('detail.noKeyframes')}</p>
                  )}
                </div>
              )}

              {clip.roll_type === 'a' && (
                <TranscriptSection data={clip.transcript} />
              )}

              <div className="space-y-3 border-t border-[--border] pt-4">
                <Accordion title={t('detail.sourceFile')}>
                  <p className="break-all text-sm text-[--text-primary]">{clip.source_path}</p>
                </Accordion>

                <Accordion title={t('detail.metadata')}>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between gap-4">
                      <span className="text-[--text-muted]">{t('detail.duration')}</span>
                      <span>{clip.duration_s !== null ? `${(clip.duration_s / 60).toFixed(1)} ${t('detail.minutes')}` : '—'}</span>
                    </div>
                    {clip.width && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">{t('detail.resolution')}</span>
                        <span>{clip.width}×{clip.height}</span>
                      </div>
                    )}
                    {clip.fps && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">{t('detail.frameRate')}</span>
                        <span>{clip.fps} {t('detail.fps')}</span>
                      </div>
                    )}
                    {clip.codec && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">{t('detail.codec')}</span>
                        <span>{clip.codec}</span>
                      </div>
                    )}
                  </div>
                </Accordion>
              </div>
            </aside>
          </div>

          {/* ── Bottom bar ── */}
          {clip.roll_type !== 'photo' && (
            <div className="flex shrink-0 items-center justify-between border-t border-[--border] bg-[--surface-1] px-5 py-3">
              <div className="inline-flex rounded-md border border-[--border] p-0.5">
                {(['a', 'b'] as const).map((roll) => (
                  <button
                    key={roll}
                    onClick={() => handleCorrectRoll(roll)}
                    className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                      clip.roll_type === roll
                        ? 'bg-[--primary] text-white'
                        : 'text-[--text-secondary] hover:text-[--text-primary]'
                    }`}
                  >
                    {roll === 'a' ? 'A-roll' : 'B-roll'}
                  </button>
                ))}
              </div>

              <button
                onClick={handleReanalyze}
                disabled={reanalyzing}
                title={reanalyzing ? t('detail.reanalyzing') : t('detail.reanalyze')}
                aria-label={t('detail.reanalyze')}
                className="inline-flex items-center gap-1.5 rounded-md border border-[--border] px-3 py-1.5 text-xs font-medium text-[--text-secondary] transition-colors hover:text-[--text-primary] disabled:opacity-50"
              >
                <svg className={`h-4 w-4 ${reanalyzing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24">
                  <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                {t('detail.reanalyze')}
              </button>
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}
