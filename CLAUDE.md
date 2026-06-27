# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## Superpowers Plugin — Mandatory Workflow for All Features and Bugfixes

**Any feature development or bug fix on this project MUST follow the superpowers plugin workflow. This is not optional.**

Before starting any feature or bugfix, invoke the relevant superpowers skills in order:
1. **brainstorming** — Explore requirements and design before writing code. Saves a design document for validation.
2. **using-git-worktrees** — Creates an isolated workspace on a new branch, verifies clean test baseline.
3. **writing-plans** — Breaks work into bite-sized tasks (2–5 min each) with exact file paths, complete code, and verification steps.
4. **subagent-driven-development** or **executing-plans** — Dispatches fresh subagents per task with two-stage review (spec compliance + code quality), or executes in batches.
5. **test-driven-development** — Enforces RED-GREEN-REFACTOR: write failing test → watch it fail → minimal code → watch it pass → commit. **Deletes any code written before tests.**
6. **requesting-code-review** — Reviews against plan between tasks; critical issues block progress.
7. **finishing-a-development-branch** — Verifies tests, presents merge/PR/keep/discard options, cleans up worktree.

**Check for relevant skills before every task.** These are mandatory workflows, not suggestions. For trivial one-line fixes (typos, obvious bugs), use judgment — but anything that touches logic, behavior, or structure goes through this pipeline.

## 0. Code Work Goes Through codebase-memory-mcp (Hard Boundary)

**Reading, planning, or editing code — ground in the code graph first, not memory.**

- **Plan/edit:** `search_graph`, `trace_path`, `get_code_snippet` to find symbols and know every caller before touching them.
- **After editing:** re-trace callers of changed symbols and run tests/build. "Looks right" ≠ verified.
- Not indexed → `index_repository` first; changed outside this session → `detect_changes` / re-index.
- Text, configs, docs: Grep/Glob/Read freely. Always Read before editing.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Project status

CutFinder is **pre-implementation**. The only content so far is the design spec at `doc/proposal.md` (written in Chinese). There is no source code, build system, or test suite yet. When scaffolding the project, update this file with real build/lint/test commands (including how to run a single test) — do not invent them before they exist.

Read `doc/proposal.md` first; it is the source of truth for scope, the model pipeline, and the hard constraints below. The original author communicates in Chinese, and A-roll narration is Chinese — user-facing text and AI prompts default to Chinese.

## What CutFinder does

A local, offline macOS tool (runs as a local web app on `localhost`) that catalogs personal Vlog footage. It auto-classifies each clip as **A-roll** (has spoken narration) or **B-roll** (pure visuals), generates a Chinese summary + tags for A-roll, generates visual tags for B-roll, makes thumbnails, and organizes copies by shooting date and type so footage is searchable later. Inspired by Argus (github.com/discoposse/argus).

## Non-negotiable constraints

These come directly from the user and override convenience:

1. **Original files are read-only.** Every organizing action happens on *copies* in a separate target library. Never move, rename, or modify source files.
2. **Shooting time must never change.** Embedded QuickTime/EXIF capture time is preserved (it is never written), and copies preserve filesystem times (`shutil.copy2`). Classification date is derived from embedded capture time; fall back to file creation time only when absent, and flag that in the UI.
3. **Fully local / offline.** No footage leaves the machine. All inference runs on the user's Apple Silicon Mac.
4. **Idempotent rescans.** Re-scanning only processes new files (dedup by file fingerprint); never re-copy or duplicate.

## Architecture (planned)

- **Backend:** Python + FastAPI. **DB:** SQLite, stored at `<library>/.cutfinder/catalog.sqlite` (thumbnails under `.cutfinder/thumbnails/`). **Frontend:** Vite + React (thumbnail wall + filter/search). **Video:** ffmpeg/ffprobe for metadata, thumbnails, and frame extraction.

- **Library layout:** copies land at `<library>/YYYY-MM-DD/A-roll/` or `.../B-roll/`. Date-first, then type.

### Model serving — this is the part that requires care

Text and vision models are **both served by OMLX** (github.com/jundot/omlx), a local OpenAI-compatible server at `http://localhost:8000/v1`. They are *not* run as separate mlx-vlm processes — you call the same `/chat/completions` endpoint and switch via the `model` name.

- **A-roll text summary + tags:** `Qwen3.6-35B-A3B` (text-only MoE — it cannot see images).
- **B-roll visual tags + description:** `Qwen3-VL-8B-Instruct` (vision; send extracted frames as base64 images using the standard OpenAI vision message format).
- OMLX handles load/unload and memory (LRU eviction, model pinning, per-model TTL), so both models can be configured to coexist.

**Speech is the exception (OMLX does not serve audio):** A-roll transcription runs as a **separate local process**, selectable via the machine-global `transcription_engine` pref (Settings → Speech engine). One choice governs *all* A-roll speech work — catalog transcription, keyframe reasoning over the stored transcript, and subtitle export:
- **`whisper`** — `mlx-whisper` large-v3 (default `mlx-community/whisper-large-v3-mlx`). See `adapters/mlx_whisper.py`.
- **`qwen`** — local **Qwen3-ASR + Qwen3-ForcedAligner** via `mlx-audio` (`adapters/qwen_transcriber.py`): VAD-chunk the audio → Qwen3-ASR per chunk for accurate Chinese/zh-en text → ForcedAligner for real per-character timestamps → group into cues. More accurate on Chinese and gives non-drifting subtitle timing. The aligner caps at ~400s/call, so chunks are bounded (`qwen_max_chunk_s`, default 60, max 300). **OMLX cannot serve the ForcedAligner over HTTP** (its `/audio/transcriptions` has no text param), so it must run locally. Models download into `models/qwen/`.

A/B classification uses a lightweight **Silero VAD** speech-presence check, also separate.

### Per-clip pipeline

Scan source folder(s) → dedup by fingerprint → ffprobe metadata + ffmpeg thumbnail → Silero VAD speech check:
- **Speech present → A-roll:** the configured speech engine produces the full transcript (stored) → Qwen3.6 (via OMLX) summary + tags.
- **No speech → B-roll:** ffmpeg keyframes → Qwen3-VL (via OMLX, base64) visual tags + description.

Then write metadata/type/summary/tags/transcript/thumbnail path to SQLite and copy the original into the dated library folder. A/B verdicts and tags are AI-generated but **user-correctable**, and corrections are remembered.

## Scope boundaries

In v1: requirements 0–7 (custom folders, time preservation, A/B detection, A-roll summary, date+type organization, tags, thumbnails, OMLX integration). **Deferred:** keyframe suggestions (req 8), Final Cut Pro deep integration (FCPXML/Keywords export), and packaging as a standalone `.app` (Tauri/PyInstaller). Don't pull deferred items into v1 work without asking.
