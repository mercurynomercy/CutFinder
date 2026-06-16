/** Settings feature — configuration page for source/library folders, model selectors,
extension whitelist, B-roll frame count, and VAD threshold with validation.

Fetches current settings from GET /api/settings on mount and saves via PUT /api/settings
on form submission.  All fields have basic validation (required, min/max, type checks).

Usage:
  <SettingsPage onSave={(prefs) => handleSave(prefs)} />
*/

import { useCallback, useEffect, useState } from 'react'

import type { UpdateSettingsBody } from '@/api/client'
import { api } from '@/api/client'
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

// ── Folder picker (native macOS dialog via backend osascript) ───
// A browser <input webkitdirectory> only exposes the folder *name*
// (webkitRelativePath), never an absolute path — useless for a local tool
// that resolves real filesystem paths. So we ask the backend to open a native
// macOS chooser (POST /api/pick-folder) which returns the absolute path.

interface FolderPickerButtonProps {
  label: string
  icon?: React.ReactNode | null
  onChange: (folderPath: string) => void
}

function FolderPickerButton({ label, icon = null, onChange }: FolderPickerButtonProps) {
  const [picking, setPicking] = useState(false)

  const handlePick = async () => {
    setPicking(true)
    try {
      const { path } = await api.pickFolder()
      if (path) onChange(path) // null = user cancelled the dialog
    } catch {
      // backend unreachable / non-macOS — silently ignore
    } finally {
      setPicking(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handlePick}
      disabled={picking}
      className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[--surface-2] px-3 py-1.5 text-xs font-medium text-[--text-secondary] hover:bg-[--surface-3] disabled:opacity-50"
    >
      {icon}
      {picking ? '选择中…' : label}
    </button>
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

  // Machine-global env settings (OMLX endpoint/key, whisper path). These live
  // in ~/.cutfinder/config.json — no .env needed. The API key is write-only:
  // GET returns a mask, and we only send it when the user types a new value.
  const [omlxBaseUrl, setOmlxBaseUrl] = useState('')
  const [whisperPath, setWhisperPath] = useState('')
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)

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
        setOmlxBaseUrl(data.env.OMLX_BASE_URL || '')
        setWhisperPath(data.env.WHISPER_MODEL_PATH || '')
        setApiKeyConfigured(Boolean(data.env.OMLX_API_KEY))
        setApiKeyInput('')
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

  // Switch the active library at runtime. Unlike other prefs (saved via
  // PUT /settings into the *current* library), the library binding lives in
  // ~/.cutfinder/active_library and must be changed via POST /api/library —
  // otherwise the app keeps using the old library no matter what's picked.
  const handleSwitchLibrary = async (path: string) => {
    const p = path.trim()
    if (!p || p === libraryPath) return
    const ok = window.confirm(
      `切换素材库到:\n${p}\n\n应用将改用这个目录的目录数据库、缩略图和设置（每个库各自独立）。当前库不会被修改。是否继续？`,
    )
    if (!ok) return
    setSaving(true)
    setError(null)
    try {
      await api.setLibrary(p)
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
    updateField('extensions', (prefs.extensions ?? []).filter((e: string) => e !== ext))
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
      // library_path is the active-library binding, not a normal pref — it's
      // changed via setLibrary (POST /api/library). Stripping it here keeps the
      // saved pref from diverging from the real binding.
      const body: UpdateSettingsBody = { ...prefs }
      delete body.library_path
      // Machine-global keys: always send the (non-secret) endpoint + whisper
      // path; only send the API key when the user typed a new one, so the
      // stored secret is never overwritten by the mask.
      body.OMLX_BASE_URL = omlxBaseUrl.trim()
      body.WHISPER_MODEL_PATH = whisperPath.trim()
      if (apiKeyInput.trim()) body.OMLX_API_KEY = apiKeyInput.trim()
      await api.putSettings(body)
      if (apiKeyInput.trim()) {
        setApiKeyConfigured(true)
        setApiKeyInput('')
      }
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
      {/* Title + Back button — full width at top */}
      <div className="mx-auto w-full max-w-5xl space-y-6">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-xl font-semibold tracking-tight text-[--text-primary]">Settings</h1>
          <Button variant="ghost" size="sm" onClick={() => onSave?.()}>
            Back to gallery
          </Button>
        </div>

        {/* Responsive two-column grid — single column on narrow screens */}
        <form onSubmit={(e) => { e.preventDefault(); handleSave() }} className="grid grid-cols-1 gap-6 lg:grid-cols-2">

          {/* ── Column 1 ───────────────────────────────────── */}
          <div className="space-y-6">

            {/* ── Source folders ─────────────────────── */}
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
                    <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 10.5v6m3-3H9m4.06-7.19-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
                  </svg>
                }
                onChange={(folder) => {
                  if (!prefs || (prefs.source_folders ?? []).includes(folder)) return
                  updateField('source_folders', [...(prefs.source_folders || []), folder])
                }}
              />
            </fieldset>

            {/* ── Library path ─────────────────────── */}
            <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <legend className="text-sm font-medium text-[--text-primary]">Library path</legend>
              <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">
                组织后的素材副本、缩略图和目录数据库会存储在这里。切换到其他目录会改用那个库（每个库各自独立，当前库不会被修改）。
              </p>
              <div className="mt-2 flex gap-2">
                <input
                  type="text"
                  value={libraryPath || ''}
                  readOnly
                  className="flex-1 rounded-md border border-[--border] bg-[--surface-3] px-3 py-1.5 text-sm outline-none opacity-70"
                />
                <FolderPickerButton
                  label="Choose…"
                  icon={
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 0 0-1.883 2.542l.857 6a2.25 2.25 0 0 0 2.227 1.932H19.05a2.25 2.25 0 0 0 2.227-1.932l.857-6a2.25 2.25 0 0 0-1.883-2.542m-16.5 0V6A2.25 2.25 0 0 1 6 3.75h3.879a1.5 1.5 0 0 1 1.06.44l2.122 2.12a1.5 1.5 0 0 0 1.06.44H18A2.25 2.25 0 0 1 20.25 9v.776" />
                    </svg>
                  }
                  onChange={(folder) => void handleSwitchLibrary(folder)}
                />
              </div>
            </fieldset>

            {/* ── OMLX connection (machine-global) ─────── */}
            <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <legend className="text-sm font-medium text-[--text-primary]">OMLX connection</legend>
              <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">
                本地 OMLX 推理服务的地址和密钥（全机共用，存储在 ~/.cutfinder/config.json，无需 .env 文件）。这里保存的值优先生效，会覆盖 .env / 环境变量。
              </p>

              <label className="mt-3 block text-sm text-[--text-secondary]">Base URL</label>
              <input
                type="text" value={omlxBaseUrl}
                onChange={(e) => setOmlxBaseUrl(e.target.value)}
                placeholder="http://localhost:8000/v1"
                className="mt-1 w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
              />

              <label className="mt-3 block text-sm text-[--text-secondary]">API key</label>
              <p className="mb-1 text-xs text-[--text-muted]">
                {apiKeyConfigured ? '已配置 — 留空则保持不变，输入新值则覆盖' : '尚未配置'}
              </p>
              <input
                type="password" value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={apiKeyConfigured ? '••••••••（留空不修改）' : 'omlx-…'}
                autoComplete="new-password"
                className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
              />

              <label className="mt-3 block text-sm text-[--text-secondary]">Text model</label>
              <p className="mb-1 text-xs text-[--text-muted]">用于 A-roll 的中文摘要 + 标签生成（通过 OMLX，纯文本模型）。留空则用默认 Qwen3.6-35B-A3B。</p>
              <input
                type="text" value={prefs.text_model}
                onChange={(e) => updateField('text_model', e.target.value)}
                placeholder="Qwen3.6-35B-A3B"
                className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
              />

              <label className="mt-3 block text-sm text-[--text-secondary]">Vision model</label>
              <p className="mb-1 text-xs text-[--text-muted]">用于 B-roll 的视觉标签 + 描述生成（通过 OMLX，多模态模型）。留空则用默认 Qwen3-VL-8B。</p>
              <input
                type="text" value={prefs.vision_model}
                onChange={(e) => updateField('vision_model', e.target.value)}
                placeholder="Qwen3-VL-8B"
                className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
              />
            </fieldset>

          </div>

          {/* ── Column 2 ───────────────────────────────────── */}
          <div className="space-y-6">

            {/* ── Whisper (speech-to-text) ─────────────── */}
            <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <legend className="text-sm font-medium text-[--text-primary]">Whisper（语音转写）</legend>
              <p className="mt-1 text-xs leading-relaxed text-[--text-secondary]">
                A-roll 中文语音转文字（独立本地进程，不经过 OMLX）。
              </p>
              <div className="mt-3 space-y-4">
                <label className="block text-sm text-[--text-secondary]">Whisper model</label>
                <p className="mb-1 text-xs text-[--text-muted]">HuggingFace 模型 id；若下方填了本地路径则以本地路径为准</p>
                <input
                  type="text" value={prefs.whisper_model} readOnly
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm"
                />

                <label className="mt-2 block text-sm text-[--text-secondary]">Whisper model path（本地覆盖，可选）</label>
                <p className="mb-1 text-xs text-[--text-muted]">本地 mlx-whisper 模型目录；填了则离线加载并覆盖上面的模型 id，留空则用 HuggingFace 缓存</p>
                <input
                  type="text" value={whisperPath}
                  onChange={(e) => setWhisperPath(e.target.value)}
                  placeholder="（可选）/path/to/whisper-large-v3-mlx"
                  className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm font-mono outline-none focus:border-[--primary]"
                />
              </div>
            </fieldset>

            {/* ── Processing options ─────────────────── */}
            <fieldset className="rounded-lg border border-[--border] bg-[--surface-1] p-4">
              <legend className="text-sm font-medium text-[--text-primary]">Processing options</legend>

              {/* Extensions */}
              <div className="mt-3">
                <label className="mb-1 block text-sm text-[--text-secondary]">Supported extensions</label>
                <p className="mb-1 text-xs text-[--text-muted]">扫描时只处理这些后缀的视频文件</p>
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
              <p className="mb-1 text-xs text-[--text-muted]">B-roll 视觉分析时提取的视频帧数，越多越准确但处理更慢</p>
              <input
                type="number" min={1} step={1} value={prefs.broll_frame_count}
                onChange={(e) => updateField('broll_frame_count', parseInt(e.target.value, 10))}
                className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
              />

              {/* VAD threshold */}
              <label className="mt-4 block text-sm text-[--text-secondary]">VAD threshold (0–1)</label>
              <p className="mb-1 text-xs text-[--text-muted]">语音检测灵敏度阈值，越高越严格（只标记有明显人声的片段为 A-roll）</p>
              <input
                type="number" min={0} max={1} step={0.05} value={prefs.vad_threshold}
                onChange={(e) => updateField('vad_threshold', parseFloat(e.target.value))}
                className="w-full rounded-md border border-[--border] bg-[--surface-2] px-3 py-1.5 text-sm outline-none focus:border-[--primary]"
              />

              {/* AI output language */}
              <label className="mt-4 block text-sm text-[--text-secondary]">AI output language</label>
              <p className="mb-1 text-xs text-[--text-muted]">AI 生成的摘要、标签等文字输出的语言</p>
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

          </div>

        </form>

        {/* ── Save button — full width, below grid ─────────── */}
        <div className="flex justify-end pt-4">
          <Button type="submit" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </Button>
        </div>

      </div>
    </div>
  )
}
