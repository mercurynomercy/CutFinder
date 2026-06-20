/** Reusable confirmation dialog rendered as a React modal.

Replaces `window.confirm()` so it works inside WKWebView (macOS native app)
where JS dialogs are blocked.

Usage:
  <ConfirmDialog open title="Switch library" message={path} onConfirm={() => …} onCancel={() => …} />

*/

import { useEffect } from 'react'
import { useI18n } from '@/i18n'

export interface ConfirmDialogProps {
  open: boolean
  title: string   // dialog heading (e.g. "切换素材库")
  message: string // body text, may contain newlines or placeholders
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'OK', cancelLabel = 'Cancel', onConfirm, onCancel }: ConfirmDialogProps) {
  const { t } = useI18n()

  // Allow overriding labels with i18n keys.
  const confirmText = t(`confirm.confirm`) || confirmLabel
  const cancelText = t(`confirm.cancel`) || cancelLabel

  // Esc key closes.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center p-6" role="dialog" aria-modal onClick={onCancel}>
      <div className="absolute inset-0 bg-black/60" />

      <div
        className="relative flex w-full max-w-md flex-col overflow-hidden rounded-xl border border-[--border] bg-[--surface-1] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-[--border] px-5 py-3">
          <h2 className="text-sm font-semibold text-[--text-primary]">{title}</h2>
          <button
            onClick={onCancel}
            className="rounded-md p-1 text-[--text-muted] hover:text-[--text-primary]"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <pre className="whitespace-pre-wrap px-5 py-4 text-sm leading-relaxed text-[--text-primary]">{message}</pre>

        {/* Footer */}
        <div className="flex shrink-0 justify-end gap-2 border-t border-[--border] px-5 py-3">
          <button
            onClick={onCancel}
            className="rounded-md border border-[--border] bg-[--surface-2] px-4 py-1.5 text-sm font-medium text-[--text-secondary] transition-colors hover:text-[--text-primary]"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-md bg-[--primary] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:brightness-110"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
