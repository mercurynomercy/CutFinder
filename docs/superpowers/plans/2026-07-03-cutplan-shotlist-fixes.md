# Cutplan Shot-List Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the rough-cut shot-list thumbnail open the local file directly (like the home/detail play button), and label still photos as photos instead of B-roll.

**Architecture:** Two backend edits in the director's plan builder (source `roll` from the clip's DB record; add a resolved `clip_path` to each shot) plus frontend edits in `ShotList` (thumbnail → `api.openPath`, photo badge label) and removal of the now-dead `onOpenClip` prop plumbing. The cut route serializes the domain `CutPlan` via `model_dump()`, so adding a field to the `Shot` model is enough on the wire — no route/schema change.

**Tech Stack:** Python + FastAPI + pydantic (backend), Vite + React + TypeScript + Vitest/Testing Library (frontend).

## Global Constraints

- User-facing text defaults to Chinese; reuse existing i18n keys (`t('card.photo')` → "照片"/"Photo").
- Match existing code style; touch only what each task requires.
- `roll` is a property of the source clip, never reclassified by the model.
- Backend unit tests: `cd backend && uv run pytest`. Frontend tests: `cd frontend && npm test`.

---

### Task 1: Backend — shot `roll` comes from the clip's DB record

**Files:**
- Modify: `backend/cutfinder/cutplan/director.py:890`
- Test: `backend/tests/unit/test_cutplan_director.py`

**Interfaces:**
- Consumes: `ClipDetail.roll` (existing), `Shot(roll=...)` (existing).
- Produces: shots whose `roll` equals the clip's DB `roll_type` when detail is available.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_cutplan_director.py` (the helpers `FakeLLM`, `FakeRetriever`, `FakeInspector`, `_tc`, `AgentStep`, `ClipBrief`, `ClipDetail`, `CutDirector`, `RoughCutRequest` are already imported/defined at the top of that file):

```python
def test_shot_roll_taken_from_clip_not_model() -> None:
    # Model mislabels a photo clip as "b"; the plan must trust the DB roll.
    llm = FakeLLM([
        AgentStep(content="ok", tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 5, "roll": "b", "in_s": 0, "out_s": 4, "content": "情侣自拍"},
        ]})]),
    ])
    details = {5: ClipDetail(clip_id=5, roll="photo", duration_s=4.0, library_path="/lib/photo-0008.JPG")}
    retr = FakeRetriever([ClipBrief(clip_id=5, roll="photo")], details)
    director = CutDirector(llm, retr, FakeInspector(), ui_language="zh")

    result = director.run(RoughCutRequest(), [], "剪一条")

    assert result.plan is not None
    assert result.plan.shots[0].roll == "photo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_cutplan_director.py::test_shot_roll_taken_from_clip_not_model -v`
Expected: FAIL — `assert 'b' == 'photo'` (model's `"b"` currently wins).

- [ ] **Step 3: Write minimal implementation**

In `backend/cutfinder/cutplan/director.py`, change the `roll=` line inside the `Shot(...)` construction (currently line 890):

```python
                roll=str(detail.roll if detail else (item.get("roll") or "a")),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_cutplan_director.py -v`
Expected: PASS — the new test passes and existing director tests (e.g. `test_aroll_spine_plus_broll_finalizes`, which uses clips whose DB roll matches the model) still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/cutfinder/cutplan/director.py backend/tests/unit/test_cutplan_director.py
git commit -m "fix(cutplan): source shot roll from clip record so photos aren't B-roll"
```

---

### Task 2: Backend — add `clip_path` to shots

**Files:**
- Modify: `backend/cutfinder/domain/models.py:217-229` (the `Shot` model)
- Modify: `backend/cutfinder/cutplan/director.py` (the `Shot(...)` construction, currently ending at line 899)
- Test: `backend/tests/unit/test_cutplan_director.py`

**Interfaces:**
- Consumes: `ClipDetail.library_path`, `ClipDetail.source_path` (existing fields).
- Produces: `Shot.clip_path: str | None` = `library_path or source_path`. Serialized to the API via `CutPlan.model_dump()` — frontend `CutShot` will read `clip_path`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_cutplan_director.py`:

```python
def test_shot_clip_path_from_library_or_source() -> None:
    llm = FakeLLM([
        AgentStep(content="ok", tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12, "content": "开场白"},
        ]})]),
    ])
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a")], _details())
    director = CutDirector(llm, retr, FakeInspector(), ui_language="zh")

    result = director.run(RoughCutRequest(), [], "剪一条")

    assert result.plan is not None
    # _details()[1] has library_path="/lib/A-0001.mov"
    assert result.plan.shots[0].clip_path == "/lib/A-0001.mov"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_cutplan_director.py::test_shot_clip_path_from_library_or_source -v`
Expected: FAIL — `AttributeError` / pydantic: `Shot` has no `clip_path`.

- [ ] **Step 3: Write minimal implementation**

In `backend/cutfinder/domain/models.py`, add a field to the `Shot` model (after `thumb_ref`, ~line 229):

```python
    clip_path: str | None = None     # library/source path for "open file" (filled by director)
```

In `backend/cutfinder/cutplan/director.py`, add `clip_path=` to the `Shot(...)` construction (alongside `thumb_ref=...`, ~line 898):

```python
                clip_path=(detail.library_path or detail.source_path) if detail else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_cutplan_director.py -v`
Expected: PASS — new test passes, existing tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add backend/cutfinder/domain/models.py backend/cutfinder/cutplan/director.py backend/tests/unit/test_cutplan_director.py
git commit -m "feat(cutplan): add clip_path to shots for open-file"
```

---

### Task 3: Frontend — thumbnail opens the local file; remove `onOpenClip`

**Files:**
- Modify: `frontend/src/api/client.ts:215-226` (the `CutShot` interface)
- Modify: `frontend/src/features/cutplan/index.tsx` (props, both `<ShotList>` call sites, `ShotList` signature + thumbnail button)
- Modify: `frontend/src/App.tsx:366`
- Test: `frontend/src/features/cutplan/__tests__/index.test.tsx`

**Interfaces:**
- Consumes: `Shot.clip_path` from Task 2 (wire field `clip_path`), `api.openPath(path: string)` (existing).
- Produces: `ShotList` with signature `{ plan: CutPlan }` (no `onOpenClip`). `CutplanPageProps` = `{ onClose: () => void }`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/features/cutplan/__tests__/index.test.tsx`, add `clip_path` to the shot in the top-level `PLAN` constant so it looks like:

```javascript
    {
      clip_id: 1, roll: 'a', in_s: 0, out_s: 12, content: '开场白',
      rationale: '叙事开场', chapter: '开场', clip_label: 'A-0001.mov',
      clip_path: '/lib/A-0001.mov', thumb_ref: '/api/clips/1/thumbnail',
    },
```

Then add a new test (the file already imports `vi`, `screen`, `userEvent`, `server`, `http`, `HttpResponse`, `API`; add `import { api } from '@/api/client'` at the top):

```javascript
  it('clicking a shot thumbnail opens the local file', async () => {
    const openSpy = vi.spyOn(api, 'openPath').mockResolvedValue({ status: 'ok', path: '/lib/A-0001.mov' })
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 1, title: 't', status: 'idle', created_at: null, updated_at: null }] }),
      ),
      http.get(`${API}/cut/sessions/1`, () =>
        HttpResponse.json({
          session: { id: 1, title: 't', status: 'idle', created_at: null, updated_at: null },
          messages: [{ role: 'assistant', content: '已生成', created_at: null }],
          plan: PLAN,
        }),
      ),
    )

    render(<CutplanPage onClose={() => {}} />)

    const label = await screen.findByText('A-0001.mov')
    await userEvent.click(label.closest('button')!)

    expect(openSpy).toHaveBeenCalledWith('/lib/A-0001.mov')
    openSpy.mockRestore()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- cutplan/__tests__/index`
Expected: FAIL — the thumbnail button currently calls `onOpenClip` (undefined here), so `api.openPath` is never called.

- [ ] **Step 3: Write minimal implementation**

3a. In `frontend/src/api/client.ts`, add to the `CutShot` interface (after `clip_date`):

```typescript
  clip_path: string | null
```

3b. In `frontend/src/features/cutplan/index.tsx`, change `CutplanPageProps` (remove the `onOpenClip` field and its comment):

```typescript
export interface CutplanPageProps {
  onClose: () => void
}
```

3c. Change the component signature:

```typescript
export function CutplanPage({ onClose }: CutplanPageProps) {
```

3d. Change both `<ShotList .../>` usages (in the preview pane and the fullscreen overlay) to drop the prop:

```typescript
                <ShotList plan={plan} />
```

and

```typescript
            {plan ? <ShotList plan={plan} /> : <p className="text-sm text-[--text-muted]">{t('roughcut.noPlan')}</p>}
```

3e. Change the `ShotList` signature (remove `onOpenClip`):

```typescript
function ShotList({ plan }: { plan: CutPlan }) {
```

3f. Change the thumbnail button (replace the `onClick`/`className` that reference `onOpenClip`/`s.clip_id`):

```typescript
                    <button type="button" onClick={() => s.clip_path && api.openPath(s.clip_path)} className={`flex flex-col items-center gap-0.5 ${s.clip_path ? 'cursor-pointer' : ''}`}>
```

3g. In `frontend/src/App.tsx:366`, drop the `onOpenClip` prop:

```typescript
    return <CutplanPage onClose={() => setShowCutplan(false)} />
```

- [ ] **Step 4: Run tests + typecheck to verify they pass**

Run: `cd frontend && npm test -- cutplan && npm run build`
Expected: PASS — the new test passes, `strict.test.tsx` still passes, and the TypeScript build succeeds (no unused `onOpenClip`, `setSelectedClipId` in App.tsx is still used by the detail panel wiring so no orphan).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/features/cutplan/index.tsx frontend/src/App.tsx frontend/src/features/cutplan/__tests__/index.test.tsx
git commit -m "fix(cutplan): shot thumbnail opens the local file directly"
```

---

### Task 4: Frontend — photo badge shows "照片" not "photo"

**Files:**
- Modify: `frontend/src/features/cutplan/index.tsx` (the roll badge label in `ShotList`, currently line 773)
- Test: `frontend/src/features/cutplan/__tests__/index.test.tsx`

**Interfaces:**
- Consumes: `t('card.photo')` (existing i18n key → "照片"/"Photo"), `ShotList` (already calls `useI18n()`).
- Produces: photo shots render the localized photo label in the badge.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/features/cutplan/__tests__/index.test.tsx`:

```javascript
  it('renders a photo shot with the photo badge, not B-roll', async () => {
    const photoPlan = {
      ...PLAN,
      shots: [{
        clip_id: 8, roll: 'photo', in_s: 0, out_s: 4, content: '[Photo] 情侣自拍',
        rationale: '视觉总结', chapter: '开场', clip_label: 'photo-0008.JPG',
        clip_path: '/lib/photo-0008.JPG', thumb_ref: '/api/clips/8/thumbnail',
      }],
    }
    server.use(
      http.get(`${API}/cut/sessions`, () =>
        HttpResponse.json({ sessions: [{ id: 1, title: 't', status: 'idle', created_at: null, updated_at: null }] }),
      ),
      http.get(`${API}/cut/sessions/1`, () =>
        HttpResponse.json({
          session: { id: 1, title: 't', status: 'idle', created_at: null, updated_at: null },
          messages: [{ role: 'assistant', content: '已生成', created_at: null }],
          plan: photoPlan,
        }),
      ),
    )

    render(<CutplanPage onClose={() => {}} />)

    await screen.findByText('photo-0008.JPG')
    // The default test locale is English → 'Photo'; assert we never render the raw 'photo'.
    expect(screen.getByText('Photo')).toBeInTheDocument()
    expect(screen.queryByText('photo')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- cutplan/__tests__/index`
Expected: FAIL — badge currently renders the raw string `"photo"`, so `getByText('Photo')` fails (and the raw `'photo'` is present).

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/features/cutplan/index.tsx`, change the badge label expression (currently line 773) to add a `'photo'` branch:

```typescript
                        {s.roll === 'a' ? 'A' : s.roll === 'b' ? 'B' : s.roll === 'photo' ? t('card.photo') : s.roll}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- cutplan`
Expected: PASS — the photo badge test passes; existing cutplan tests still pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/cutplan/index.tsx frontend/src/features/cutplan/__tests__/index.test.tsx
git commit -m "fix(cutplan): label photo shots as 照片 in the shot-list badge"
```

---

## Self-Review

- **Spec coverage:** Fix 1 backend → Task 2; Fix 1 frontend (open file + remove `onOpenClip`) → Task 3; Fix 2 backend (root cause) → Task 1; Fix 2 frontend (badge label) → Task 4. Testing section of the spec covered by tests in Tasks 1–4. All spec requirements mapped.
- **Placeholder scan:** No TBD/TODO; every code step shows exact code and commands.
- **Type consistency:** `Shot.clip_path: str | None` (Task 2) ↔ `CutShot.clip_path: string | null` (Task 3); `api.openPath(path: string)` used with `s.clip_path` guarded on non-null; `ShotList` signature reduced to `{ plan }` consistently across both call sites and the definition.
