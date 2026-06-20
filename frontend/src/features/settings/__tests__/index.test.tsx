/** Tests for the SettingsPage feature — library setup + preferences form.
 *
 * Behavior-focused (rendered text/values + network calls), not exact classes.
 */

import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import { SettingsPage } from '../index'

const API = 'http://localhost:5080/api'

describe('SettingsPage', () => {
  it('prompts to set up a library when none is bound', async () => {
    server.use(http.get(`${API}/library`, () => HttpResponse.json({ library_path: null })))

    render(<SettingsPage />)
    expect(await screen.findByText('Set up your library')).toBeInTheDocument()
  })

  it('binds a library when a path is submitted, then loads settings', async () => {
    let bound: string | null = null
    server.use(
      http.get(`${API}/library`, () => HttpResponse.json({ library_path: bound })),
      http.post(`${API}/library`, async ({ request }) => {
        bound = (await request.json() as { path: string }).path
        return HttpResponse.json({ status: 'ok', library_path: bound })
      }),
    )

    render(<SettingsPage />)
    await userEvent.type(await screen.findByPlaceholderText(/CutFinder Library/), '/tmp/lib')
    await userEvent.click(screen.getByRole('button', { name: /set library/i }))

    // After binding, the settings form loads (a known model name appears).
    expect(await screen.findByDisplayValue('Qwen3.6-35B-A3B')).toBeInTheDocument()
  })

  it('renders model names and the library path when bound', async () => {
    render(<SettingsPage />)
    expect(await screen.findByDisplayValue('Qwen3.6-35B-A3B')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Qwen3-VL-8B')).toBeInTheDocument()
    expect(screen.getByDisplayValue('/Users/jan/Media/CutFinder_Library')).toBeInTheDocument()
  })

  it('defaults the AI output language to the saved preference', async () => {
    render(<SettingsPage />)
    const select = await screen.findByRole('combobox', { name: 'AI output language' })
    expect((select as HTMLSelectElement).value).toBe('zh')
  })

  it('saves updated preferences via PUT /settings', async () => {
    let saved: Record<string, unknown> | null = null
    server.use(
      http.put(`${API}/settings`, async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    render(<SettingsPage />)
    const select = await screen.findByRole('combobox', { name: 'AI output language' })
    await userEvent.selectOptions(select, 'en')
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }))

    await waitFor(() => expect(saved).not.toBeNull())
    expect(saved!.output_language).toBe('en')
  })

  it('renders the vocal-separation toggle reflecting the loaded value (off)', async () => {
    render(<SettingsPage />)
    const toggle = await screen.findByRole('checkbox', {
      name: /Separate vocals before A-roll transcription/i,
    })
    expect((toggle as HTMLInputElement).checked).toBe(false)
  })

  it('sends vocal_separation in the PUT payload when toggled on', async () => {
    let saved: Record<string, unknown> | null = null
    server.use(
      http.put(`${API}/settings`, async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    render(<SettingsPage />)
    const toggle = await screen.findByRole('checkbox', {
      name: /Separate vocals before A-roll transcription/i,
    })
    await userEvent.click(toggle)
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }))

    await waitFor(() => expect(saved).not.toBeNull())
    expect(saved!.vocal_separation).toBe(true)
  })

  it('lets the user add and remove photo extensions', async () => {
    let saved: Record<string, unknown> | null = null
    server.use(
      http.put(`${API}/settings`, async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    render(<SettingsPage />)
    // Default photo extensions render as removable tags.
    expect(await screen.findByText('.heic')).toBeInTheDocument()

    const input = screen.getByPlaceholderText('.webp')
    await userEvent.type(input, 'webp{enter}')
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }))

    await waitFor(() => expect(saved).not.toBeNull())
    expect(saved!.photo_extensions).toEqual(['.jpg', '.jpeg', '.png', '.heic', '.webp'])
  })
})
