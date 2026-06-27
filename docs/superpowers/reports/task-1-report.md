# Task 1 Report: Rewrite `doc/proposal.md`

**Status:** DONE

## Commits
- `cba07b8 docs(proposal): rewrite and simplify requirements document`

## Self-test Results
All self-test checklist items passed:
- [x] All requirement numbers (0–8) match current codebase state — all 9 requirements marked as implemented, consistent with actual features
- [x] Tech stack selections accurate — Python/FastAPI backend at `backend/cutfinder/`, SQLite, Vite+React+Tailwind+shadcn/ui frontend at `frontend/src/`, ffmpeg/ffprobe, OMLX
- [x] Model names correct — `Qwen3.6-35B-A3B` (text), `Qwen3-VL-8B` (vision, matching config.py default)
- [x] Implemented features correctly marked — keyframes (#8), subtitle export, Demucs vocal separation, native macOS .app, progress resume (resumePoll), cut director agent (beta), photo analysis with HEIC support, orphan cleanup all marked as implemented
- [x] No incremental update history cluttering the document — clean rewrite, no version changelog
- [x] No TBD/TODO placeholder text found

## Config Defaults Verified Against codebase (`config.py` Prefs class)
- `vad_threshold`: 0.35 (not original proposal's stale 0.15)
- `broll_frame_count`: 5 (not original's stale 3)
- `extensions`: `.mov .mp4 .m4v` (video); `photo_extensions`: `.jpg .jpeg .png .heic`
- `keyframe_auto`: false (default off)
- `transcription_engine`: whisper; `qwen_max_chunk_s`: 60 (max 300)
- All cut-director agent params match config.py defaults

## Concerns
None. Document is clean and accurate against the current codebase state at `backend/cutfinder/` (60+ Python files) and `frontend/src/features/` (12 feature modules).
