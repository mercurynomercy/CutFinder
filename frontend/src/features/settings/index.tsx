/** Settings feature — configuration page for source/library folders, model selectors,
extension whitelist, B-roll frame count, and VAD threshold with validation.

Fetches current settings from GET /api/settings on mount and saves via PUT /api/settings
on form submission.  All fields have basic validation (required, min/max, type checks).

Usage:
  <SettingsPage onSave={(prefs) => handleSave(prefs)} />
*/

import { useEffect, useState } from 'react'

import type { SettingsPrefs, UpdateSettingsBody } from '@/api/client'
import { api, ApiError } from '@/api/client'

// ── Validation helpers ────────────────────────────────────────────

interface FieldError {
  field: string
  message: string
}

function validatePrefs(prefs: UpdateSettingsBody): FieldError[] {
  const errors: FieldError[] = []

  if (prefs.broll_frame_count !== undefined) {
    const v = prefs.broll_frame_count as number
    if (!Number.isInteger(v) || v < 1) {
      errors.push({ field: 'broll_frame_count', message: 'Must be an integer >= 1' })
    }
  }

  if (prefs.vad_threshold !== undefined) {
    const v = prefs.vad_threshold as number
    if (typeof v !== 'number' || isNaN(v) || v <= 0 || v > 1) {
      errors.push({ field: 'vad_threshold', message: 'Must be a number between 0 and 1' })
    }
  }

  return errors
}

// ── Extension tag (for the whitelist) ────────────────────────────

function ExtensionTag({ value, onRemove }: { value: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[--surface-3] px-2 py-0.5 text-xs font-mono">
      {value}
      <button onClick={onRemove} className="text-[--text-muted] hover:text-[--error]" aria-label={`Remove ${value}`}>
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24">
          <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </span>
  )
}

// ── Main Settings component ──────────────────────────────────────

export interface SettingsPageProps {
  /** Called when settings are successfully saved. */
  onSave?: () => void
}

export function SettingsPage({ onSave }: SettingsPageProps) {
  const [prefs, setPrefs] = useState<UpdateSettingsBody | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([])

  // Form inputs
  const [extensions, setExtensions] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.getSettings()
      .then((data) => {
        if (!cancelled) setPrefs(data.prefs)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err : new Error(String(err)))
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [])

  const updateField = <K extends keyof UpdateSettingsBody>(key: K, value: UpdateSettingsBody[K]) => {
    setPrefs((prev) => (prev ? { ...prev, [key]: value } : prev))
    // Clear field error for this key if present
    setFieldErrors((prev) => prev.filter((e) => e.field !== key))
  }

  const handleAddExtension = () => {
    const ext = extensions.trim().replace(/^\.*/, '.') // ensure leading dot
    if (!ext || !prefs) return

    const current = prefs.extensions || []
    if (current.includes(ext)) { setExtensions(''); return }

    updateField('extensions', [...current, ext])
    setExtensions('')
  }

  const handleRemoveExtension = (ext: string) => {
    if (!prefs) return
    updateField('extensions', prefs.extensions.filter((e: string) => e !== ext))
  }

  const handleSave = async () => {
    if (!prefs) return

    const errors = validatePrefs(prefs)
    setFieldErrors(errors)
    if (errors.length > 0) return

    setSaving(true)
    try {
      await api.putSettings(prefs)
      onSave?.()
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="p-6 text-[--text-muted]">Loading settings…</div>
  if (error) return <div className="p-6 text-[--error]">Failed to load settings: {error.message}</div>
  if (!prefs) return null

  // Prepend dot to extensions for display, ensure they start with a dot
  const extDisplay = (prefs.extensions || []).map((e: string) => e.startsWith('.') ? e : `.${e}`)

  return (
    <div className="flex flex-1 overflow-auto p-6">
      <form onSubmit={(e) => { e.preventDefault(); handleSave() }} className="w-full max-w-2xl space-y-6">
        <h1 className="text-xl font-semibold tracking-tight text-[--text-primary]">Settings</h1>

        {/* ── Source folders ─────────────────────── */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Source folders</legend>
          <div className="mt-3 space-y-2">
            {(prefs.source_folders || []).map((folder: string, i: number) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="text"
                  value={folder}
                  onChange={(e) => {
                    const folders = [...prefs.source_folders] as string[]
                    folders[i] = e.target.value
                    updateField('source_folders', folders as unknown as UpdateSettingsBody[keyof UpdateSettingsBody])
                  }}
                  className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
                />
              </div>
            ))}
          </div>
        </fieldset>

        {/* ── Library path ─────────────────────── */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Library path</legend>
          <input
            type="text"
            value={prefs.library_path || ''}
            onChange={(e) => updateField('library_path', e.target.value)}
            className="mt-2 w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          />
        </fieldset>

        {/* ── Model selectors ─────────────────── */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Models</legend>
          <div className="mt-3 space-y-3">
            <label className="block text-sm text-[--text-secondary]">Text model</label>
            <input
              type="text" value={prefs.text_model} readOnly
              className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm"
            />

            <label className="mt-2 block text-sm text-[--text-secondary]">Vision model</label>
            <input
              type="text" value={prefs.vision_model} readOnly
              className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm"
            />

            <label className="mt-2 block text-sm text-[--text-secondary]">Whisper model</label>
            <input
              type="text" value={prefs.whisper_model} readOnly
              className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm"
            />
          </div>
        </fieldset>

        {/* ── Extension whitelist + B-roll frames + VAD threshold ─ */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Processing options</legend>

          {/* Extensions */}
          <div className="mt-3">
            <label className="mb-1 block text-sm text-[--text-secondary]">Supported extensions</label>
            <div className="mb-2 flex gap-1.5">
              {extDisplay.map((ext, i) => (
                <ExtensionTag key={i} value={ext} onRemove={() => handleRemoveExtension(ext)} />
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text" value={extensions} onChange={(e) => setExtensions(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAddExtension() }}
                placeholder=".webm"
                className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
              />
              <Button size="sm" variant="secondary" onClick={handleAddExtension}>+</Button>
            </div>
          </div>

          {/* B-roll frame count */}
          <label className="mt-4 block text-sm text-[--text-secondary]">B-roll frame count</label>
          <input
            type="number" min={1} step={1} value={prefs.broll_frame_count}
            onChange={(e) => updateField('broll_frame_count', parseInt(e.target.value, 10))}
            className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          />

          {/* VAD threshold */}
          <label className="mt-4 block text-sm text-[--text-secondary]">VAD threshold (0–1)</label>
          <input
            type="number" min={0} max={1} step={0.05} value={prefs.vad_threshold}
            onChange={(e) => updateField('vad_threshold', parseFloat(e.target.value))}
            className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          />

          {/* AI output language */}
          <label className="mt-4 block text-sm text-[--text-secondary]">AI output language</label>
          <select
            value={prefs.output_language}
            onChange={(e) => updateField('output_language', e.target.value as 'zh' | 'en')}
            className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          >
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>

          {/* Field errors */}
          {fieldErrors.map((err) => (
            <p key={err.field} className="mt-1 text-xs text-[--error]">{err.message}</p>
          ))}
        </fieldset>

        {/* ── Save button (sticky bottom) ─────── */}
        <div className="flex justify-end pt-4">
          <Button type="submit" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </Button>
        </div>

      </form>
    </div>
  )
}
