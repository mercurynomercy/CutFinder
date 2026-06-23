/** Tests for the CutplanPage feature — sessions, chat turn, shot list, delete. */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/mocks/server'
import { CutplanPage } from '../index'

const API = 'http://localhost:5080/api'

const PLAN = {
  shots: [
    {
      clip_id: 1, roll: 'a', in_s: 0, out_s: 12, content: '开场白',
      rationale: '叙事开场', chapter: '开场', clip_label: 'A-0001.mov',
      thumb_ref: '/api/clips/1/thumbnail',
    },
  ],
  chapters: ['开场'],
  total_s: 12, target_min_s: null, target_max_s: null,
  within_target: true, note: '', markdown: '## 开场\n...\n**总时长：0:12**\n',
}

describe('CutplanPage', () => {
  it('lists sessions and renders the shot list when one is selected', async () => {
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 1, title: '周末 vlog', status: 'idle', created_at: null, updated_at: null }] }),
      ),
      http.get(`${API}/cut/sessions/1`, () =>
        HttpResponse.json({
          session: { id: 1, title: '周末 vlog', status: 'idle', created_at: null, updated_at: null },
          messages: [
            { role: 'user', content: '剪一条', created_at: null },
            { role: 'assistant', content: '好的，这是分镜', created_at: null },
          ],
          plan: PLAN,
        }),
      ),
    )

    render(<CutplanPage onClose={() => {}} />)

    await userEvent.click(await screen.findByText('周末 vlog'))

    // Conversation + shot list both render.
    expect(await screen.findByText('好的，这是分镜')).toBeInTheDocument()
    expect(screen.getByText('开场')).toBeInTheDocument() // chapter heading
    expect(screen.getByText('A-0001.mov')).toBeInTheDocument()
    expect(screen.getByText('开场白')).toBeInTheDocument()
  })

  it('sends a message, polls the job, then shows the assistant reply + plan', async () => {
    const user = userEvent.setup()
    let sent: { text?: string } | null = null

    server.use(
      http.get(`${API}/cut/sessions`, () => HttpResponse.json({ sessions: [] })),
      http.post(`${API}/cut/sessions`, () =>
        HttpResponse.json({ id: 5, title: '', status: 'idle', created_at: null, updated_at: null }),
      ),
      http.post(`${API}/cut/sessions/5/messages`, async ({ request }) => {
        sent = (await request.json()) as { text?: string }
        return HttpResponse.json({ job_id: 9, session_id: 5 })
      }),
      http.get(`${API}/jobs/9`, () =>
        HttpResponse.json({ id: 9, status: 'done', total: 1, done: 1, failed: 0, started_at: null }),
      ),
      http.get(`${API}/cut/sessions/5`, () =>
        HttpResponse.json({
          session: { id: 5, title: '', status: 'idle', created_at: null, updated_at: null },
          messages: [
            { role: 'user', content: '剪 15 分钟', created_at: null },
            { role: 'assistant', content: '已生成分镜', created_at: null },
          ],
          plan: PLAN,
        }),
      ),
    )

    render(<CutplanPage onClose={() => {}} />)

    const box = await screen.findByPlaceholderText(/Make a 15/)
    await user.type(box, '剪 15 分钟')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(sent?.text).toBe('剪 15 分钟'))
    expect(await screen.findByText('已生成分镜')).toBeInTheDocument()
    expect(await screen.findByText('A-0001.mov')).toBeInTheDocument()
  })

  it('restores the last session on mount and shows its plan without a click', async () => {
    localStorage.setItem('cutfinder:cut-active-session', '1')
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 1, title: '周末 vlog', status: 'idle', created_at: null, updated_at: null }] }),
      ),
      http.get(`${API}/cut/sessions/1`, () =>
        HttpResponse.json({
          session: { id: 1, title: '周末 vlog', status: 'idle', created_at: null, updated_at: null },
          messages: [{ role: 'assistant', content: '已生成', created_at: null }],
          plan: PLAN,
        }),
      ),
    )

    render(<CutplanPage onClose={() => {}} />)

    // Auto-restored — the shot list shows up with no interaction.
    expect(await screen.findByText('A-0001.mov')).toBeInTheDocument()
    localStorage.clear()
  })

  it('shows the thinking indicator and resumes when the restored session is still running', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 7, title: 't', status: 'running', created_at: null, updated_at: null }] }),
      ),
      http.get(`${API}/cut/sessions/7`, () => {
        calls += 1
        // Stay running for the first couple of polls so the thinking indicator
        // has a real window before the turn resolves.
        const running = calls <= 2
        return HttpResponse.json({
          session: { id: 7, title: 't', status: running ? 'running' : 'idle', created_at: null, updated_at: null },
          messages: running
            ? [{ role: 'user', content: '剪一条', created_at: null }]
            : [{ role: 'user', content: '剪一条', created_at: null }, { role: 'assistant', content: '完成了', created_at: null }],
          plan: running ? null : PLAN,
        })
      }),
    )

    render(<CutplanPage onClose={() => {}} />)

    // First load: running → thinking indicator visible.
    expect(await screen.findByText('Director is working…')).toBeInTheDocument()
    // After the resume poll: assistant reply + plan appear.
    expect(await screen.findByText('完成了', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.getByText('A-0001.mov')).toBeInTheDocument()
  })

  it('deletes a conversation', async () => {
    const del = vi.fn()
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 1, title: 'to delete', status: 'idle', created_at: null, updated_at: null }] }),
      ),
      http.delete(`${API}/cut/sessions/1`, () => {
        del()
        return HttpResponse.json({ status: 'ok', session_id: 1 })
      }),
    )

    render(<CutplanPage onClose={() => {}} />)

    // Reveal the row, then click its delete button (hidden until hover, but present in DOM).
    await screen.findByText('to delete')
    await userEvent.click(screen.getByRole('button', { name: 'Delete conversation' }))
    // Confirm dialog → OK.
    await userEvent.click(await screen.findByRole('button', { name: 'OK' }))

    await waitFor(() => expect(del).toHaveBeenCalled())
  })
})
