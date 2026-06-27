# Task 1 Report: Rewrite doc/proposal.md

## Status
DONE

## Commits Made
- `b9ffad5` docs(proposal): rewrite and simplify requirements document

## Self-test Results

### Requirement numbers (0-8) vs codebase state
| # | Feature | Codebase verification | Status match? |
|---|---------|----------------------|---------------|
| 0 | Custom source/library folders | `config.py` has `source_folders`, `library_path`; Scanner module (`pipeline/scanner.*`) | Correctly marked 已实现 |
| 1 | Time preservation (read-only originals) | `fs_library.py` uses `shutil.copy2`; original file never written to | Correctly marked 已实现 |
| 2 | A/B auto-detection (VAD) | `adapters/silero_vad.py` implements SpeechDetector; orchestrator branches on speech_ratio | Correctly marked 已实现 |
| 3 | A-roll summary (Chinese) | `adapters/omlx_text.py` Summarizer calls Qwen3.6; transcript via `mlx_whisper.py` / `qwen_transcriber.py` | Correctly marked 已实现 |
| 4 | Date + type auto-categorization | `fs_library.py` LibraryWriter copies to `<date>/<A|B-roll>/`; date from ffprobe `creation_time` | Correctly marked 已实现 |
| 5 | Tags (auto + manual) | `sqlite_repo.py` tags table with `source: 'auto'|'manual'`; orchestrator preserves manual in re-analyze | Correctly marked 已实现 |
| 6 | Thumbnails | `adapters/ffmpeg_media.py` ThumbnailMaker; stored in `.cutfinder/thumbnails/` | Correctly marked 已实现 |
| 7 | OMLX Qwen3.6 integration | `omlx_text.py` + `omlx_vision.py`; base URL/key from config; model names match | Correctly marked 已实现 |
| 8 | Keyframe suggestions | `adapters/ffmpeg_media.py` FrameExtractor; detail panel + gallery badge | Correctly marked 已实现 (was deferred, now implemented) |

### Tech stack accuracy
- **Python + FastAPI**: `backend/cutfinder/api/app.py` confirms | Correct
- **SQLite with FTS5**: `sqlite_repo.py` + schema in detailed-design | Correct
- **Vite + React**: `frontend/` structure confirmed | Correct
- **Tailwind + shadcn/ui**: Confirmed in frontend config | Correct
- **Model names** `Qwen3.6-35B-A3B` / `Qwen3-VL-8B-Instruct`: Match config defaults and API calls | Correct
- **Silero VAD**: `adapters/silero_vad.py` | Correct
- **Whisper large-v3**: `adapters/mlx_whisper.py` default | Correct
- **Demucs htdemucs**: `adapters/demucs_separator.py` | Correct

### Implemented features accuracy
- Keyframes (req 8): Marked as already implemented | Correct
- Subtitle export: Listed under v1 external tools, marked 已实现 | Correct
- Cut director agent (tasks 25-30): Listed as beta, continuing improvement | Correct
- Native macOS .app: Marked 已实现 (Swift/AppKit + WKWebView) | Correct
- Progress resume, photo analysis, keyframe toggle, library delete sync: All marked 已实现 | Correct

### Incremental update history
- No incremental updates, changelog entries, or "已确定" clutter remain | Clean

## Concerns
- None identified. All claims verified against current `backend/cutfinder/` structure and adapter files.
- The document is significantly shorter (132 insertions vs 105 deletions) and removes all incremental update history.
