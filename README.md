# CutFinder

> A local, offline tool that automatically classifies, tags, summarizes, and organizes your Vlog footage. Inspired by [Argus](https://github.com/discoposse/argus).

**中文文档 → [README-zh.md](./README-zh.md)**

CutFinder takes a pile of **A-roll** (clips with spoken narration — Chinese by default) and **B-roll** (pure visuals, no narration) and automatically **classifies, tags, summarizes, and thumbnails** every clip, so you can later find any shot by date, type, tag, or spoken line. Built for macOS (Apple Silicon) + Final Cut Pro workflows — **fully offline, all AI runs on your own machine.**

> **Status: core functionality is complete and runs end-to-end.** Backend adapters, the orchestration layer, the API wiring layer (`create_app`), and the frontend are all implemented and connected. `make test-unit` (367 unit tests), frontend `vitest` (190 tests), `npm run build` (type-clean), `make check-omlx`, and `make dev` all pass. The model inference chain (text / vision / transcription / VAD) is verified against a real OMLX server plus local integration tests (see [Testing](#testing)).

---

## What it does

- **Automatic A-roll / B-roll classification** — detects the presence of spoken narration (Silero VAD). The verdict is correctable by hand, and corrections are remembered.
- **A-roll summary + tags** — `mlx-whisper` transcribes the Chinese narration → a Qwen text model summarizes it. The full transcript is stored and searchable.
- **B-roll visual tags + description** — extracted frames are sent to a vision model that describes what's on screen.
- **Switchable interface language (EN / ZH)** — the entire UI can be flipped between **English and Chinese** in Settings (defaults to English, remembered per device), fully independent of the AI output language below.
- **Switchable AI output language** — summaries / visual descriptions can be generated in **Chinese or English** (defaults to Chinese), chosen in Settings.
- **Auto-organize and rename by capture date + type** — copies land in `<library>/YYYY-MM-DD/A-roll(or B-roll)/` and are renamed in order as `A-0001.ext` / `B-0001.ext` (counted per date/type folder). Even when AI analysis fails, the original is still filed by date + type (status flagged `partial`); the AI summary/tags are best-effort. The detail panel shows the new copy path (File destination); the original source path is collapsed under Source file.
- **Thumbnail wall + multi-dimensional search** — clips are **grouped by capture date** (one block per date with a sticky date header). A search box in the left sidebar filters live by filename / summary / description / tags, plus filters by date / type / tag (collapsible filter panel) and newest/oldest sort. The tag filter is sorted by frequency, searchable, and collapses when there are many tags. Clips with incomplete analysis (`partial`) carry a "partial" badge on the thumbnail.
- **One-click Open / Reveal in Finder** — thumbnails and the detail panel open the video in the default player; date-group headers open that date's folder in Finder (macOS `open`).
- **Re-analyze a single clip** — re-run the AI with one click (when changing models or unhappy with the result), preserving your manual corrections and tags. If the A/B verdict was wrong, toggle the type in the detail panel — the copy is **moved** to the correct A-roll/B-roll folder and renamed, and `library_path` is updated.
- **Keyframe suggestions (cut points + highlight frames)** — for each clip, up to N ranked editing suggestions (default 3, configurable): **A-roll uses the text model over the transcript**, **B-roll uses Qwen3-VL over sampled frames**. Each suggestion carries in/out timecodes, a representative frame, and a one-line rationale. Suggestions can auto-queue after a scan (a Settings toggle) or be generated on demand in the detail panel; gallery cards show a "has suggestions" badge.
- **Subtitle export for finished cuts** — pick any edited video → re-transcribe with `mlx-whisper` (vocals isolated first to strip BGM) → export Final Cut Pro-native **iTT + SRT** into a folder you choose (source video stays read-only, subtitle language follows the AI output language, transcribe-only — no translation). The export shows a **live progress bar synced to the real backend progress**, advancing through two phases: vocal separation, then transcription.
- **Capture-date display** — both thumbnail cards and the detail panel show each clip's capture time (embedded capture time preferred, falling back to file creation time).
- **Task queue management** — a dedicated Task Queue page lists every scan / re-analyze job, with delete, retry-failed, and global pause/resume; scanning prompts you when the queue is paused.
- **Native folder picker** — choosing the footage folder / library in Settings opens the macOS native picker and returns a real absolute path (browser pickers can't).
- **Bind your library in Settings** — pick or type one absolute path on first use; it takes effect **at runtime with no restart** (a `CUTFINDER_LIBRARY` env var also works).
- **Auto-refresh after scan** — when a scan finishes, the app polls job status and refreshes the thumbnail wall automatically.
- **Dark professional UI** — near-black panels make thumbnails pop; A-roll/B-roll are distinguished by color + icon, close to FCP's feel (see [`doc/ui-design.md`](./doc/ui-design.md)).

### Never touch the originals (core constraints)

- **Originals are read-only** — all organizing happens on copies in a separate library.
- **Capture time never changes** — embedded QuickTime/EXIF capture time is never written. Copies preserve filesystem modified/accessed times, and additionally preserve the **creation (birth) time** on macOS. Renames/relocations are same-volume renames and touch no timestamps.
- **Offline** — footage never leaves your machine.
- **Idempotent** — re-scans only process new files (dedup by fingerprint); nothing is copied twice.

---

## Architecture overview

```
Frontend (Vite + React + Tailwind, dark-first)   :5080
   │ HTTP (REST + SSE), via Vite dev proxy → :5081
API layer (FastAPI, thin)                          :5081
   │  create_app() wires real adapters into a mutable LibraryContext (library bound at runtime)
Orchestration (Pipeline Orchestrator + background queue/SSE progress)
   │  depends only on interfaces (Protocols)
Adapters ── ffmpeg/ffprobe · Silero VAD · mlx-whisper · OMLX (text + vision) · SQLite
```

Every external dependency hides behind an interface; business logic depends only on those interfaces, so modules are independently swappable and testable. See [`doc/detailed-design.md`](./doc/detailed-design.md).

### Model serving

| Purpose | Model (id on OMLX) | How it runs |
|---|---|---|
| A-roll summary/tags (text) | `Qwen3.6-35B-A3B` | OMLX (OpenAI-compatible API) |
| B-roll visual recognition (vision) | `Qwen3-VL-8B` | OMLX (same API, frames sent as base64) |
| A-roll speech transcription | `mlx-whisper` (default `mlx-community/whisper-large-v3-mlx`) | Separate process (OMLX does not serve audio) |
| A/B speech detection | Silero VAD | Local |
| Vocal separation (strip BGM before transcribing) | Demucs (`htdemucs`, ~80 MB) | Local (torch/MPS); isolates vocals, then transcribes |

Background music mixed into footage gets transcribed as garbage or triggers Whisper hallucinations. Before transcribing, [Demucs](https://github.com/adefossez/demucs) isolates the vocal stem and drops the accompaniment. **Subtitle export (finished cuts) always separates**; the **A-roll ingest pipeline has a `vocal_separation` toggle, off by default** (raw footage usually has no added music). On separation failure it falls back to the raw audio so transcription never breaks.

The text and vision models are both served by [OMLX](https://github.com/jundot/omlx), a local Apple-Silicon inference server (menu-bar app).

> ⚠️ The model names must match exactly the ids your OMLX has loaded. The default vision model is `Qwen3-VL-8B`; if your OMLX exposes a suffixed id, change `vision_model` / `text_model` in Settings or in `<library>/.cutfinder/config.json`.

---

## Requirements

### Required

| Dependency | Notes |
|------|------|
| **macOS + Apple Silicon** | AI inference needs the Metal GPU — cannot run in Docker / x86 macOS |
| [OMLX](https://github.com/jundot/omlx) ≥ 0.1 | Local Apple-Silicon model server (menu-bar app); preload `Qwen3.6-35B-A3B` (text) and `Qwen3-VL-8B` (vision) |
| [uv](https://docs.astral.sh/uv/) | Python dependency management (`pip install uv`) |
| **Python ≥ 3.12** | uv provisions a 3.12 venv per `mise.toml` |
| **Node.js ≥ 20** + `npm` | Frontend dev server and build tooling |
| [ffmpeg](https://ffmpeg.org/) (`ffprobe` + `ffmpeg`) | Video metadata extraction and thumbnail generation (`brew install ffmpeg`) |

### Optional

- [mise](https://mise.jdx.dev/) — auto-manages Python / Node versions (`mise.toml`)
- [Homebrew](https://brew.sh/) — to install ffmpeg / OMLX

> ⚠️ **AI inference must run natively** — it cannot run inside a Docker container.

---

## Setup & Run

### 1. Install dependencies

```bash
git clone <repo> && cd CutFinder
make setup                      # mise install + brew bundle + uv sync + npm install
```

> OMLX can be configured in the **Settings page** (step 2) — no `.env` required. If you prefer a `.env`, run `cp .env.example .env` and fill in the values.

> No mise? Run `brew install mise` first, or do it manually:
> ```bash
> cd backend && uv sync           # Python deps (pytest / mypy / ruff included via uv sync)
> cd ../frontend && npm install   # Vite + React + Tailwind
> ```

### 2. Configure the OMLX connection

Two things to configure: OMLX URL and API key. Either way works:

- **Settings page (recommended, no `.env`)** — after launching, open http://localhost:5080 → **Settings** → **OMLX connection** → fill in Base URL / API key → Save. These are stored in `~/.cutfinder/config.json` (**shared machine-wide**, no need to re-enter per library) and take effect immediately.

- **`.env` (optional, for temporary overrides)** — place a `.env` in the **repo root**:

  ```ini
  # OMLX local inference server (OpenAI-compatible). Defaults to :8000; change to match your port.
  OMLX_BASE_URL=http://localhost:8000/v1
  OMLX_API_KEY=your-omlx-key
  ```

  `make dev` / `make check-omlx` / `make test-integration` load it automatically; if you start the backend manually with `uvicorn`, export it first with `set -a; source .env; set +a`.

> **Priority** (high → low): **Settings global config** (`~/.cutfinder/config.json`) > **env vars / `.env`**. The Settings page is authoritative — values saved there always win, even if `.env` sets the same key (note `make dev` exports `.env` into the environment, so both belong to the same "fallback" layer). `.env` / env vars only fill keys the Settings page hasn't set.

### 3. Verify OMLX is ready

```bash
make check-omlx                 # checks that the text/vision models are loaded
# → OMLX OK — models: [...]
#   All required text/vision models are present.
```

> `make check-omlx` reads only `.env` / env vars, **not** the Settings global config. If you configure via the UI (no `.env`), skip this and verify in-app on your first scan, or run it ad-hoc: `OMLX_BASE_URL=... OMLX_API_KEY=... make check-omlx`.

### 4. Start the dev servers (recommended: one command for both)

```bash
make dev
# Backend → http://localhost:5081 (FastAPI)
# Frontend → http://localhost:5080 (Vite, /api proxied to backend 5081)
```

Open **http://localhost:5080**. `Ctrl+C` stops both servers.

### 5. Bind your library (first run)

The library directory holds the organized copies, thumbnails, and the SQLite catalog (all under `<library>/.cutfinder/`). Two ways:

- **Settings page (recommended)** — open http://localhost:5080 → **Settings** → **Set up your library** → click **Choose…** to pick a directory with the macOS native picker (or type an absolute path). It takes effect **at runtime with no restart**, and the choice is remembered (persisted to `~/.cutfinder`).
- **Env var** — add `CUTFINDER_LIBRARY=/path/to/library` to the root `.env`, then `make dev`.

> Without a bound library the backend still starts, but directory-type endpoints return 503 and the Settings page shows the binding wizard until you bind one.

### Manual split start (for debugging)

```bash
# Terminal 1 — backend (export .env first)
cd backend
set -a; source ../.env; set +a
CUTFINDER_LIBRARY=/path/to/library uv run uvicorn cutfinder.api.app:app --reload --port 5081

# Terminal 2 — frontend
cd frontend && npx vite        # http://localhost:5080
```

### Download the models (optional pre-warm before first transcription)

```bash
make models                     # pre-download mlx-whisper large-v3-mlx + Demucs htdemucs
```

This pre-downloads both the Whisper model and the Demucs `htdemucs` vocal-separation model into the project's **`models/` folder** (gitignored). After that, transcription / subtitle export runs fully offline.

You don't have to run this — both models are **downloaded automatically on first use** into `models/whisper/` and `models/demucs/`. `make models` just warms them ahead of time so the first run isn't slowed by a download. No path configuration needed.

---

## Testing

### Backend (pytest)

```bash
cd backend

uv run pytest tests/unit             # unit tests only (367, no external services, seconds)
uv run pytest -m integration         # integration tests (need a real OMLX / ffmpeg / sample clips)
uv run mypy cutfinder/               # type check (strict, clean)
uv run ruff check cutfinder/         # linting (clean)
```

Integration tests **auto-skip** when `.env` / OMLX / sample clips are missing — no false failures. To actually exercise the OMLX chain:

```bash
cd backend
set -a; source ../.env; set +a
uv run pytest -m integration
```

### Frontend (Vitest + Playwright)

```bash
cd frontend

npx vitest run                  # unit / component tests
npx playwright test             # e2e (auto-starts the Vite dev server)
```

### Makefile shortcuts

```bash
make test-unit         # backend unit tests (fast, tests/unit, no external deps) — use this day to day
make test              # full backend (incl. -m integration; runs for real if OMLX/.env are present, may be slow)
make test-integration  # only -m integration (auto-loads .env; needs ffmpeg/OMLX)
make e2e               # Playwright e2e
```

> Vitest is still run from frontend/: `cd frontend && npx vitest run`

### Known leftovers (don't affect running)

- In real integration runs, **visual/text tag text may mix Chinese and English** (a model/prompt characteristic of Qwen3-VL-8B / the text model, not an adapter bug); the structured result (description/summary + tags) is always valid.
- **AI summaries are non-deterministic** — OMLX calls use `temperature=0.7` (and the strict `json_schema` that made quantized models loop was dropped in favor of lenient parsing). Stable on clear footage; on edge clips with noisy/vague audio a summary may not be produced — the clip is still filed (status `partial`) and can be re-analyzed by hand.

---

## Docs

- [Proposal `doc/proposal.md`](./doc/proposal.md) — goals, requirements, scope, tech choices
- [Detailed design `doc/detailed-design.md`](./doc/detailed-design.md) — modules, interfaces, data model, API, testing & deployment
- [UI design system `doc/ui-design.md`](./doc/ui-design.md) — color/font/spacing tokens, component specs, page layouts (dark-first)
- [Task list `doc/tasks/`](./doc/tasks/progress.md) — per-module tasks and overall progress
- [`CLAUDE.md`](./CLAUDE.md) — project constraints and architecture cheat-sheet for AI collaborators

---

## Install as a macOS App (CutFinder.app)

The easiest way to run CutFinder is the native **`CutFinder.app`** — a small Swift/AppKit wrapper that hosts the UI in a native window (WKWebView, no browser tab), manages the local service, and installs everything it needs on first launch.

### Build the .app

```bash
make app          # → dist/CutFinder.app (and dist/CutFinder.dmg)
```

`make app` compiles the Swift wrapper with **SwiftPM**, so the build host needs the **Xcode Command Line Tools** (`xcode-select --install`) plus Node (to build the bundled frontend). Anyone running a *prebuilt* `.app` needs none of that.

### Install & first launch

Drag `dist/CutFinder.app` to `/Applications` and double-click:

- **First launch self-installs everything.** A native setup screen shows progress while it syncs its runtime, installs `uv` and `ffmpeg` (auto `brew install` when Homebrew is present, otherwise it guides you), creates the Python environment (`uv sync`), and downloads the Whisper + Demucs models (~3 GB). Later launches start in a second.
- **The service starts automatically** and the UI loads in the app's own window — no browser. Use the **Service menu (服务)** to Start / Stop / Restart the backend, or "Open in browser" if you prefer a tab.
- **Standard Mac app behavior** — full application menu; closing the window keeps the service running; clicking the Dock icon reopens the window; ⌘Q stops the service cleanly (no orphaned process).
- The runtime lives in `~/Library/Application Support/CutFinder/` (**outside the .app bundle**, for clean updates/signing); logs are at `launch.log` there. The `.app` bundles a **prebuilt frontend** + backend source — one service serves both the UI and the API, so **no Node is needed at runtime**.

### Signing & notarization

`make app` signs the app with **Developer ID + Hardened Runtime** automatically when a signing identity is present, and notarizes + staples it when `CUTFINDER_NOTARY_PROFILE` is set; otherwise it produces an **unsigned dev build** (first open needs right-click → **Open**). Because the Python env and models live outside the bundle, only the small Swift binary is signed.

> ⚠️ Two things stay separate (they can't live inside the .app):
> 1. **OMLX** is a third-party menu-bar model server — install it and load the `Qwen` text/vision models yourself. CutFinder detects it on first run and **guides you if it's missing** (scanning / transcription / thumbnails still work without it; only A-roll summaries and B-roll tags need it).
> 2. The **Whisper** (~3 GB) and **Demucs `htdemucs`** models download automatically on first use (or pre-warm with `make models`).
>
> Brand art sources are in `branding/`.

---

## Roadmap

- **v1**: requirements 0–7 (custom folders, preserve capture time, A/B detection, A-roll summary, date+type organization, tags, thumbnails, OMLX integration) — **done**.
- **Beyond v1, done**: keyframe suggestions / cut points (requirement 8); self-installing **native `CutFinder.app` shell** (Swift/AppKit + WKWebView, `make app`) — standard app menu, stable Dock lifecycle, Dock-click reopens the window, auto-installs deps on first run, manages the service, and is code-signing/notarization-ready.
- **Next / TODO**:
  - **Export transcript as Final Cut Pro-importable subtitles** — A-roll already has time-coded `Segment`s, so iTT / SRT export is just timecode formatting (no model call). A backend `GET /api/clips/{id}/transcript.srt|.itt` + a detail-panel "Export subtitles" button would do it.
  - **Final Cut Pro deep integration** (FCPXML / Keywords export; can merge with the above: subtitles as a caption track loaded into FCP with each clip).
  - PyInstaller fully-offline bundle / Tauri native window.
