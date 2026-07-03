# Cutplan shot-list fixes — design

Date: 2026-07-03

Two small fixes to the rough-cut shot list (初剪分镜) shown in `frontend/src/features/cutplan/index.tsx` (`ShotList`).

## Problem

1. **Thumbnail navigates to detail view instead of opening the file.** The shot
   thumbnail button calls `onOpenClip(clip_id)`, which closes cutplan and opens
   the clip detail panel. It should behave like the home-page / detail-view play
   button and open the local file in its default app.
2. **Photos render a "B" badge.** A still photo (`roll_type = 'photo'`) shows a
   B-roll badge because the shot's `roll` is taken from the LLM's emitted value,
   which was `"b"`, instead of the clip's real `roll_type`.

## Fix 1 — thumbnail opens the local file

The home/detail play button opens a file via `api.openPath(library_path || source_path)`
(`POST /api/open`). `CutShot` currently carries no path, so the frontend can't
open the file directly.

- **Backend** (`domain/models.py`, `cutplan/director.py`): add `clip_path: str | None`
  to the `Shot` model. In the director's plan builder, populate it from
  `detail.library_path or detail.source_path` (the same resolution `_clip_label`
  already uses). The cut route serializes the domain `CutPlan` via `model_dump()`,
  so no schema/route change is needed. (`ShotOut` in `schemas.py` is unused dead
  code and is left untouched.)
- **Frontend** (`api/client.ts`, `features/cutplan/index.tsx`): add
  `clip_path: string | null` to the `CutShot` interface. Change the thumbnail
  button to call `api.openPath(s.clip_path)` (guarded on a non-null path) instead
  of `onOpenClip`.
- **Cleanup:** `onOpenClip` becomes unused. Remove it from `CutplanPageProps`,
  the two `ShotList` call sites, `ShotList`'s props, and the `<CutplanPage
  onOpenClip=...>` wiring in `App.tsx`.

## Fix 2 — photos badge as photo, not B-roll

- **Backend** (`cutplan/director.py`): trust the clip's DB `roll_type` over the
  model's guess when building the shot:
  `roll = detail.roll if detail else (item.get("roll") or "a")`.
  This makes photos → `'photo'` and also corrects any A/B the model mislabels.
- **Frontend** (`features/cutplan/index.tsx`): the `ShotList` badge already
  colors `'photo'` with `--roll-photo`. Change its label from the raw string
  `s.roll` (which would show "photo") to `t('card.photo')` ("照片"/"Photo"),
  matching the home-page badge.

## Testing

- Backend: extend the director plan-builder unit test (`test_cutplan_director.py`)
  to assert (a) a photo clip yields `roll == 'photo'` even when the tool args say
  `"b"`, and (b) `clip_path` is populated from library/source path.
- Frontend: extend `features/cutplan/__tests__` to assert the thumbnail click
  calls `api.openPath` with the clip path (not detail navigation), and the photo
  badge renders the localized photo label.

## Out of scope

- No change to how A/B/photo classification is computed in the pipeline.
- No change to the markdown export (`format.py`), which already maps roll labels.
