"""Pydantic schemas for the API request/response layer.

All domain models are already Pydantic ``BaseModel`` subclasses, so
many request/response types mirror them directly.  This module only
defines schemas that need additional validation constraints (e.g.
``max_length``, ``pattern``) or wrap multiple domain objects together.

"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Scan submission (enqueue) ───────────────────────────────────────

class ClipCandidateIn(BaseModel):
    """A single clip candidate submitted via the API."""

    path: str = Field(..., min_length=1)
    fingerprint: str = Field(..., pattern=r"^[a-fA-F0-9]+$")


# ── Job status response ───────────────────────────────────────────

class JobInfoResponse(BaseModel):
    """Lightweight job status returned by GET /jobs/{id}."""

    id: int
    status: str  # "running" | "done" | "failed"
    total: int = 0
    done: int = 0
    failed: int = 0
    started_at: Optional[str] = None


# ── Clip detail response (full clip + tags/transcript) ───────────

class TagOut(BaseModel):
    name: str
    source: str  # "auto" | "manual"


class SegmentOut(BaseModel):
    start_s: float
    end_s: float
    text: str


class TranscriptOut(BaseModel):
    full_text: str = ""
    segments: list[SegmentOut] = []


class ClipDetailResponse(BaseModel):
    """Full clip detail returned by GET /clips/{id}."""

    id: int
    source_path: str
    library_path: Optional[str] = None
    roll_type: str  # "a" | "b"
    roll_source: str = "auto"
    summary: Optional[str] = None
    description: Optional[str] = None
    duration_s: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: str  # "pending" | "processing" | "done" | "error"
    error: Optional[str] = None
    capture_time: Optional[Any] = None  # ISO datetime or null
    date_source: str = "file"
    tags: list[TagOut] = []
    transcript: Optional[TranscriptOut] = None


# ── Clip list item (lightweight) ─────────────────────────────────

class ClipListItem(BaseModel):
    """Slimmed-down clip entry for list/search responses."""

    id: int
    source_path: str
    library_path: Optional[str] = None
    roll_type: str  # "a" | "b"
    summary: Optional[str] = None
    description: Optional[str] = None
    duration_s: Optional[float] = None
    thumbnail_path: Optional[str] = None
    status: str  # ClipStatus string
    capture_time: Optional[Any] = None
    tags: list[TagOut] = Field(default_factory=list)


# ── Edit requests (PATCH /clips/{id}) ───────────────────────────

class CorrectRollRequest(BaseModel):
    """PATCH roll_type correction."""

    roll: str = Field(..., description="Either 'a' or 'b'.")


class EditClipRequest(BaseModel):
    """PATCH summary / description edit."""

    summary: Optional[str] = None
    description: Optional[str] = None


# ── Tag management (PUT /clips/{id}/tags) ───────────────────────

class SetTagsRequest(BaseModel):
    """Replace all tags on a clip.  Each entry specifies name + source."""

    tags: list[TagOut] = Field(..., min_length=0)


# ── Re-analyze request (POST /clips/{id}/reanalyze) ─────────────

class ReanalyzeRequest(BaseModel):
    """Empty body — just the path parameter carries clip_id."""


class ReanalyzeResponse(BaseModel):
    job_id: int


# ── Search response (GET /search) ───────────────────────────────

class SearchResponse(BaseModel):
    clips: list[ClipListItem]


# ── Settings (GET /settings, PUT /settings) ─────────────────────

class PrefsOut(BaseModel):
    source_folders: list[str] = []
    library_path: Optional[str] = None
    text_model: str = "Qwen3.6-35B-A3B"
    vision_model: str = "Qwen3-VL-8B-Instruct"
    whisper_model: str = "mlx-community/whisper-large-v3-mlx"
    extensions: list[str] = [".mp4", ".mov"]
    broll_frame_count: int = 5
    vad_threshold: float = 0.4
    keyframe_count: int = 3
    keyframe_auto: bool = True


class SettingsOut(BaseModel):
    env: dict[str, str] = {}  # OMLX_BASE_URL etc. (masked)
    prefs: PrefsOut = Field(default_factory=PrefsOut)


class SettingsUpdate(BaseModel):
    """Partial prefs update — only provided keys are changed."""

    source_folders: Optional[list[str]] = None
    library_path: Optional[str] = None
    text_model: Optional[str] = None
    vision_model: Optional[str] = None
    whisper_model: Optional[str] = None
    extensions: Optional[list[str]] = None
    broll_frame_count: Optional[int] = None
    vad_threshold: Optional[float] = None
    keyframe_count: Optional[int] = None
    keyframe_auto: Optional[bool] = None


# ── SSE event types (internal helper schemas) ───────────────────

class JobStartedEvent(BaseModel):
    type: str = "job_started"
    job_id: Optional[int] = None
    total: int = 0


class ClipStartedEvent(BaseModel):
    type: str = "clip_started"
    path: str


class ClipDoneEvent(BaseModel):
    type: str = "clip_done"
    path: str
    clip_id: Optional[int] = None


class ClipErrorEvent(BaseModel):
    type: str = "clip_error"
    path: str
    error: str


class ReanalyzeStartedEvent(BaseModel):
    type: str = "reanalyze_started"
    clip_id: int


class ReanalyzeDoneEvent(BaseModel):
    type: str = "reanalyze_done"
    clip_id: int


class ReanalyzeErrorEvent(BaseModel):
    type: str = "reanalyze_error"
    clip_id: int
    error: Optional[str] = None
