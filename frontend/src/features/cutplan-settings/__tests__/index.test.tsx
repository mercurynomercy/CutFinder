/** Tests for the RoughCutSettingsPage — renders, loads settings, saves via API. */

import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import { RoughCutSettingsPage } from '../index'

const API = 'http://localhost:5080/api'

describe('RoughCutSettingsPage', () => {
  it('renders the settings page title and close button', () => {
    server.use(
      http.get(`${API}/cut/prompt`, () =>
        HttpResponse.json({ prompt: '你是导演…', default: '你是导演…', is_default: true }),
      ),
      http.get(`${API}/settings`, () =>
        HttpResponse.json({ prefs: { cut_director_mode: 'agent', cut_max_tool_rounds: 24, cut_critic_enabled: false, cut_vision_budget: 6, cut_lean_token_budget: 50000, cut_staged_token_budget: 40000 } }),
      ),
    )

    render(<RoughCutSettingsPage onClose={() => {}} theme="dark" onToggleTheme={() => {}} />)

    // Title appears in header h1 and card header — get all occurrences.
    const titles = screen.getAllByText('Rough-cut settings')
    expect(titles.length).toBeGreaterThanOrEqual(2)
    // Close button is present.
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('edits generation options and saves them via PUT /settings', async () => {
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get(`${API}/cut/prompt`, () =>
        HttpResponse.json({ prompt: '你是导演…', default: '你是导演…', is_default: true }),
      ),
      http.get(`${API}/settings`, () =>
        HttpResponse.json({ prefs: { cut_director_mode: 'agent', cut_max_tool_rounds: 24, cut_critic_enabled: false, cut_vision_budget: 6, cut_lean_token_budget: 50000, cut_staged_token_budget: 40000 } }),
      ),
      http.put(`${API}/cut/prompt`, () =>
        HttpResponse.json({ prompt: '你是导演…', default: '你是导演…', is_default: true }),
      ),
      http.put(`${API}/settings`, async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    render(<RoughCutSettingsPage onClose={() => {}} theme="dark" onToggleTheme={() => {}} />)

    // Wait for settings to load — generation options section appears.
    await screen.findByText('Generation options')

    // The critic toggle reflects the loaded value (off) — flip it on by clicking the label.
    const criticLabel = screen.getByText('Critic review pass')
    await userEvent.click(criticLabel)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.cut_critic_enabled).toBe(true)
    expect(putBody!.cut_vision_budget).toBe(6)
    expect(putBody!.cut_director_mode).toBe('agent')
    expect(putBody!.cut_max_tool_rounds).toBe(24)
  })

  it('shows custom prompt badge when prompt is not default', async () => {
    server.use(
      http.get(`${API}/cut/prompt`, () =>
        HttpResponse.json({ prompt: 'Custom prompt…', default: '你是导演…', is_default: false }),
      ),
      http.get(`${API}/settings`, () =>
        HttpResponse.json({ prefs: { cut_director_mode: 'agent', cut_max_tool_rounds: 24, cut_critic_enabled: false, cut_vision_budget: 6, cut_lean_token_budget: 50000, cut_staged_token_budget: 40000 } }),
      ),
    )

    render(<RoughCutSettingsPage onClose={() => {}} theme="dark" onToggleTheme={() => {}} />)

    expect(await screen.findByText('Custom prompt in use')).toBeInTheDocument()
  })
})
