/** Detail panel feature — right-side slide-in drawer.

Displays clip metadata, editable summary/description (with optimistic updates),
tag editor (add/delete tags with source indicators), collapsible transcript section,
A/B roll correction button, and re-analyze trigger with loading state.

Usage:
  <DetailPanel clipId={clipId} onClose={() => setSelectedClip(null)} />
*/

import React, { useCallback, useEffect, useState } from 'react'

import type { ClipDetail, TagItem, TranscriptData } from '@/api/client'
import { api } from '@/api/client'
import { Badge, Chip } from '@/components/ChipBadge'
import { Button } from '@/components/Button'

// ── Tag editor component (add/delete) ────────────────────────────

interface TagEditorProps {
  tags: TagItem[]
  onUpdate: (tags: TagItem[]) => Promise<void>
}

function TagEditor({ tags, onUpdate }: TagEditorProps) {
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
                aria-label={`Remove tag ${tag.name}`}
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
          placeholder="Add tag…"
          className="flex-1 rounded-md border border-[--border] bg-[--surface-3] px-3 py-1.5 text-sm text-[--text-primary] placeholder:text-[--text-muted] outline-none transition-colors focus:border-[--primary]"
        />
        <Button size="sm" onClick={handleAdd} disabled={!newTag.trim()}>
          Add
        </Button>
      </div>
    </div>
  )
}

// ── Collapsible transcript section ────────────────────────────────

interface TranscriptSectionProps {
  data: TranscriptData | undefined
}

function TranscriptSection({ data }: TranscriptSectionProps) {
  const [expanded, setExpanded] = useState(false)

  if (!data || !data.full_text.trim()) return null

  return (
    <div className="rounded-lg border border-[--border] bg-[--surface-2]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm font-medium">Transcript</span>
        <svg className={`h-4 w-4 text-[--text-muted] transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24">
          <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-[--border] px-4 pb-3 pt-2 text-sm leading-relaxed text-[--text-secondary]">
          {data.full_text}

          {/* Segments table (collapsed by default, shown when expanded) */}
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
      )}
    </div>
  )
}

// ── Main Detail Panel component ────────────────────────────────

export interface DetailPanelProps {
  /** Clip id to display. When null/undefined, the panel is hidden. */
  clipId: number | null
  onClose: () => void
}

export function DetailPanel({ clipId, onClose }: DetailPanelProps) {
  const [clip, setClip] = useState<ClipDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // Editing state
  const [editSummary, setEditSummary] = useState('')
  const [saving, setSaving] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)

  // (Re)fetch the clip detail — reused after re-analyze / roll correction.
  const loadClip = useCallback((id: number) => {
    setLoading(true)
    setError(null)
    return api.getClip(id)
      .then((data) => {
        setClip(data)
        setEditSummary(data.summary || '')
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

  // Fetch clip detail when id changes
  useEffect(() => {
    if (clipId === null) return
    setClip(null)
    loadClip(clipId)
  }, [clipId, loadClip])

  // Optimistic save summary/description
  const handleSave = async () => {
    if (!clip) return
    setSaving(true)

    try {
      await api.updateClip(clip.id, { summary: editSummary })
    } catch (err) {
      console.error('Failed to save summary:', err)
    } finally {
      setSaving(false)
    }
  }

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

  // One-click "fix the A/B type and re-run": correct to the other roll, then
  // re-analyze through the right pipeline (e.g. switch a misclassified clip to
  // B-roll so it goes through the vision model).
  const handleSwitchAndReanalyze = async () => {
    if (!clip || reanalyzing) return
    const clipId = clip.id
    const target = clip.roll_type === 'a' ? 'b' : 'a'
    setReanalyzing(true)
    try {
      await api.correctRoll(clipId, target)
      setClip((prev) => prev ? { ...prev, roll_type: target } : null)
      await runReanalyze(clipId)
    } catch (err) {
      console.error('Failed to switch roll & re-analyze:', err)
    } finally {
      setReanalyzing(false)
    }
  }

  // Correct A/B roll classification
  const handleCorrectRoll = async (roll: 'a' | 'b') => {
    if (!clip) return

    try {
      await api.correctRoll(clip.id, roll)
      setClip((prev) => prev ? { ...prev, roll_type: roll } : null)
    } catch (err) {
      console.error('Failed to correct roll:', err)
    }
  }

  if (clipId === null || clipId === undefined) return null

  // Wrapper that prevents clicks from bubbling into backdrop
  const stopPropagation: React.MouseEventHandler = (e) => {
    e.stopPropagation()
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal onClick={onClose}>
      {/* Backdrop — catches clicks (outer div handles click-outside) */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Slide-in drawer — stops propagation so clicks inside don't close */}
      <div
        className="relative flex h-full w-[480px] max-w-full bg-[--surface-1] shadow-xl"
        onClick={stopPropagation}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded p-1 text-[--text-muted] hover:text-[--text-primary]"
          aria-label="Close panel"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="flex h-full w-full flex-col overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center p-8">
              <p className="text-[--text-muted]">Loading clip…</p>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center p-8">
              <p className="text-[--error]">{error.message}</p>
            </div>
          ) : clip ? (
            <>
              {/* ── Video preview area ─────────────────────── */}
              <div className="relative aspect-video w-full bg-[--surface-2]">
                {clip.thumbnail_path ? (
                  <img src={clip.thumbnail_path} alt="Thumbnail" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <svg className="h-10 w-10 text-[--text-muted]" fill="none" viewBox="0 0 24 24">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9A2.25 2.25 0 0013.5 5.25h-9A2.25 2.25 0 002.25 7.5v9A2.25 2.25 0 004.5 18.75z" />
                    </svg>
                  </div>
                )}

                {/* Roll type badge */}
                <div className="absolute left-3 top-3">
                  <Badge type={clip.roll_type === 'a' ? 'a' : clip.roll_type === 'b' ? 'b' : 'a'} />
                </div>
              </div>

              {/* ── Content area ─────────────────────────── */}
              <div className="flex flex-1 flex-col gap-4 p-5">

                {/* ── Source path (info row) ─────────────── */}
                <div>
                  <p className="truncate text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                    Source file
                  </p>
                  <p className="mt-0.5 truncate text-sm text-[--text-primary]">{clip.source_path}</p>
                </div>

                {/* ── Summary (editable, A-roll) ─────────── */}
                {clip.roll_type === 'a' && (
                  <div>
                    <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                      Summary (A-roll)
                    </label>
                    <textarea
                      value={editSummary}
                      onChange={(e) => setEditSummary(e.target.value)}
                      rows={4}
                      className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-2 text-sm text-[--text-primary] outline-none transition-colors focus:border-[--primary]"
                    />
                    <div className="mt-1 flex justify-end">
                      <Button size="sm" variant="secondary" onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving…' : 'Save'}
                      </Button>
                    </div>
                  </div>
                )}

                {/* ── Description (editable, B-roll) ─────── */}
                {clip.roll_type === 'b' && (
                  <div>
                    <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                      Description (B-roll)
                    </label>
                    <textarea
                      value={clip.description || ''}
                      readOnly
                      rows={3}
                      className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-2 text-sm text-[--text-primary]"
                    />
                  </div>
                )}

                {/* ── Tags (add/delete) ─────────────────── */}
                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[--text-muted]">
                    Tags
                  </label>
                  <TagEditor tags={clip.tags} onUpdate={async (next) => {
                    if (!clip) return
                    await api.setTags(clip.id, { tags: next })
                    setClip((prev) => prev ? { ...prev, tags: next } : null)
                  }} />
                </div>

                {/* ── Transcript (collapsible, A-roll only) */}
                {clip.roll_type === 'a' && (
                  <TranscriptSection data={clip.transcript} />
                )}

                {/* ── Metadata section (collapsible) ─────── */}
                <details className="rounded-lg border border-[--border] bg-[--surface-2]/50">
                  <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-[--text-secondary]">
                    Metadata
                  </summary>
                  <div className="border-t border-[--border] px-4 pb-3 pt-2 text-xs space-y-1.5">
                    <div className="flex justify-between gap-4">
                      <span className="text-[--text-muted]">Duration</span>
                      <span>{clip.duration_s !== null ? `${(clip.duration_s / 60).toFixed(1)} min` : '—'}</span>
                    </div>
                    {clip.width && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">Resolution</span>
                        <span>{clip.width}×{clip.height}</span>
                      </div>
                    )}
                    {clip.fps && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">Frame rate</span>
                        <span>{clip.fps} fps</span>
                      </div>
                    )}
                    {clip.codec && (
                      <div className="flex justify-between gap-4">
                        <span className="text-[--text-muted]">Codec</span>
                        <span>{clip.codec}</span>
                      </div>
                    )}
                  </div>
                </details>

              </div>

              {/* ── Footer actions (sticky bottom) ─────── */}
              <div className="flex items-center justify-between border-t border-[--border] px-5 py-3">
                {/* A/B correction buttons */}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={clip.roll_type === 'a' ? 'primary' : 'secondary'}
                    onClick={() => handleCorrectRoll('a')}
                  >
                    A-roll (narration)
                  </Button>
                  <Button
                    size="sm"
                    variant={clip.roll_type === 'b' ? 'primary' : 'secondary'}
                    onClick={() => handleCorrectRoll('b')}
                  >
                    B-roll (visual)
                  </Button>
                </div>

                {/* Re-analyze actions */}
                <div className="flex items-center gap-2">
                  {/* One-click: fix the A/B type and re-run through the right pipeline */}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleSwitchAndReanalyze}
                    disabled={reanalyzing}
                    title={`Switch this clip to ${clip.roll_type === 'a' ? 'B' : 'A'}-roll and re-analyze`}
                  >
                    {`→ ${clip.roll_type === 'a' ? 'B' : 'A'}-roll & re-analyze`}
                  </Button>
                  {/* Re-analyze with the current A/B type */}
                  <Button size="sm" variant="ghost" onClick={handleReanalyze} disabled={reanalyzing}>
                    {reanalyzing ? 'Re-analyzing…' : 'Re-analyze'}
                  </Button>
                </div>
              </div>

            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
