/** Settings feature — configuration page for source/library folders, model selectors,
extension whitelist, B-roll frame count, and VAD threshold with validation.

Fetches current settings from GET /api/settings on mount and saves via PUT /api/settings
on form submission.  All fields have basic validation (required, min/max, type checks).

Usage:
  <SettingsPage onSave={(prefs) => handleSave(prefs)} />
*/

import { useCallback, useEffect, useRef, useState } from 'react'

import type { SettingsPrefs, UpdateSettingsBody } from '@/api/client'
import { api, ApiError } from '@/api/client'
import { Button } from '@/components/Button'

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

// ── Folder picker (macOS <input webkitdirectory>) ───────────────

interface FolderPickerButtonProps {
  label: string
  icon?: React.ReactNode | null
  onChange: (folderPath: string) => void
}

function FolderPickerButton({ label, icon = null, onChange }: FolderPickerButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[--surface-2] px-3 py-1.5 text-xs font-medium text-[--text-secondary] hover:bg-[--surface-3]"
      >
        {icon}
        {label}
      </button>
      {/* Hidden file input — webkitdirectory enables folder selection on macOS */}
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        // @ts-expect-error webkitdirectory is a non-standard but widely-supported attribute
        webkitdirectory=""
        // @ts-expect-error webkitmozdirectory is an older Firefox variant
        webkitmozdirectory=""
        onChange={(e) => {
          const files = e.target.files
          if (!files || files.length === 0) return

          // Find the common ancestor folder from selected file paths
          const path = files[0].webkitRelativePath || ''
          // e.g. "MyFolder/sub/dir/video.mp4" → "MyFolder/"
          const parts = path.split('/')
          if (parts.length <= 1) return // single file selected, not a folder

          const ancestorPath = parts.slice(0, -1).join('/')
          if (ancestorPath) onChange(ancestorPath)

          // Reset so the same folder can be re-selected
          e.target.value = ''
        }}
      />
    </>
  )
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

  // Library binding (when no library is bound, the user sets one here first).
  const [libraryPath, setLibraryPath] = useState<string | null | undefined>(undefined)
  const [newLibraryPath, setNewLibraryPath] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const lib = await api.getLibrary()
      setLibraryPath(lib.library_path)
      if (lib.library_path) {
        const data = await api.getSettings()
        setPrefs(data.prefs)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const handleSetLibrary = async () => {
    const path = newLibraryPath.trim()
    if (!path) return
    setSaving(true)
    setError(null)
    try {
      await api.setLibrary(path)
      setNewLibraryPath('')
      await load()
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setSaving(false)
    }
  }

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

  const handleRemoveSourceFolder = (folder: string) => {
    if (!prefs || !prefs.source_folders?.includes(folder)) return
    updateField('source_folders', prefs.source_folders.filter((f: string) => f !== folder))
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

  // No library bound yet — prompt the user to set one (binds at runtime).
  if (libraryPath === null) {
    return (
      <div className="p-6">
        <h2 className="mb-2 text-lg font-medium text-[--text-primary]">Set up your library</h2>
        <p className="mb-4 max-w-prose text-sm text-[--text-secondary]">
          No library is configured yet. Enter an absolute path where CutFinder should
          store organized copies, thumbnails, and its catalog.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newLibraryPath}
            onChange={(e) => setNewLibraryPath(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void handleSetLibrary() }}
            placeholder="/Users/you/Movies/CutFinder Library"
            className="flex-1 rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
          />
          <FolderPickerButton label="Choose…" icon={null} onChange={(folder) => setNewLibraryPath(folder)} />
          <Button onClick={handleSetLibrary} disabled={saving || !newLibraryPath.trim()}>
            {saving ? 'Setting…' : 'Set library'}
          </Button>
        </div>
        {error && <p className="mt-2 text-xs text-[--error]">{error.message}</p>}
      </div>
    )
  }

  if (error) return <div className="p-6 text-[--error]">Failed to load settings: {error.message}</div>
  if (!prefs) return null

  // Prepend dot to extensions for display, ensure they start with a dot
  const extDisplay = (prefs.extensions || []).map((e: string) => e.startsWith('.') ? e : `.${e}`)

  return (
    <div className="flex flex-1 overflow-auto p-6">
      <form onSubmit={(e) => { e.preventDefault(); handleSave() }} className="w-full max-w-2xl space-y-6">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-xl font-semibold tracking-tight text-[--text-primary]">Settings</h1>
          <Button variant="ghost" size="sm" onClick={() => onSave?.()}>
            Back to gallery
          </Button>
        </div>

        {/* ── Source folders (read-only input for scan) ─────────────── */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Source folders</legend>
          <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">
            这些文件夹是你的原始视频素材（只读，不会被修改或移动）。扫描时 CutFinder
            只会读取这些文件夹里的文件。
          </p>
          <div className="mt-3 space-y-2">
            {(prefs.source_folders || []).map((folder: string, i: number) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="text"
                  value={folder}
                  readOnly
                  className="flex-1 rounded-md border border-[--border] bg-[--surface-3] px-3 py-1.5 text-sm outline-none opacity-70"
                />
                <button
                  type="button"
                  onClick={() => handleRemoveSourceFolder(folder)}
                  className="shrink-0 rounded-md p-1 text-[--text-muted] hover:bg-[--surface-3] hover:text-[--error]"
                  aria-label={`Remove ${folder}`}
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                    <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          {/* Hidden file input for folder picker — macOS only (webkitdirectory) */}
          <FolderPickerButton
            label="Add folder"
            icon={
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2 12.75a4.75 4.75 0 0 1 .836-2.69l2.475-3.08A4.75 4.75 0 0 1 8.692 3h6.616a4.75 4.75 0 0 1 3.352 1.38l2.475 3.08a4.75 4.75 0 0 1 .836 2.69v6.5a4.75 4.75 0 0 1-4.75 4.75H6.75a4.75 4.75 0 0 1-4.75-4.75z" />
              </svg>
            }
            onChange={(folder) => {
              if (!prefs || prefs.source_folders.includes(folder)) return
              updateField('source_folders', [...(prefs.source_folders || []), folder])
            }}
          />
        </fieldset>

        {/* ── Library path (where organized copies go) ─────────────── */}
        <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
          <legend className="text-sm font-medium text-[--text-primary]">Library path</legend>
          <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">
            组织后的素材副本、缩略图和目录数据库会存储在这里。一旦设置，此路径不可更改。
          </p>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={prefs.library_path || ''}
              readOnly
              className="flex-1 rounded-md border border-[--border] bg-[--surface-3] px-3 py-1.5 text-sm outline-none opacity-70"
            />
            <FolderPickerButton
              label="Choose…"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2 12.75a4.75 4.75 0 0 1 .836-2.69l2.475-3.08A4.75 4.75 0 0 1 8.692 3h6.616a4.75 4.75 0 0 1 3.352 1.38l2.475 3.08a4.75 4.75 0 0 1 .836 2.69v6.5a4.75 4.75 0 0 1-4.75 4.75H6.75a4.75 4.75 0 0 1-4.75-4.75z" />
                </svg>
              }
              onChange={(folder) => updateField('library_path', folder)}
            />
          </div>
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
