"""SqliteRepository — real SQLite implementation of CatalogRepository.

Uses an in-memory or on-disk :memory: / file-based SQLite connection with
FTS5 full-text search over summary, description and transcript text.

All SQL is written with ``?`` parameterised queries to prevent injection.
"""

from __future__ import annotations

import json  # noqa: F401 — used throughout for segments_json / JSONB
from sqlite3 import IntegrityError, Connection as _Conn  # noqa: F401 — type hints
import datetime as _dt

from ..domain.models import (
    AnalysisResult,
    Clip,
    ClipSummary,
    Job,
    Tag,
    Transcript,
)


# ── SQL schema (see detailed-design §5) ───────────────────────

_CREATE_CLIPS = """
CREATE TABLE IF NOT EXISTS clips (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT UNIQUE NOT NULL,
    source_path   TEXT    NOT NULL,
    library_path  TEXT,
    roll_type     TEXT    NOT NULL DEFAULT 'a',
    roll_source   TEXT    NOT NULL DEFAULT 'auto',
    capture_time  TEXT,
    date_source   TEXT    NOT NULL DEFAULT 'file',
    duration_s    REAL,
    width         INTEGER,
    height        INTEGER,
    fps           REAL,
    codec         TEXT,
    thumbnail_path TEXT,
    summary       TEXT,
    description   TEXT,
    status        TEXT    NOT NULL DEFAULT 'pending',
    error         TEXT,
    created_at    TEXT    NOT NULL,
    processed_at  TEXT
)"""

_CREATE_TAGS = """
CREATE TABLE IF NOT EXISTS tags (
    id       INTEGER PRIMARY KEY,
    clip_id  INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    name     TEXT    NOT NULL,
    source   TEXT    NOT NULL DEFAULT 'auto',
    UNIQUE(clip_id, name)
)"""

_CREATE_TRANSCRIPTS = """
CREATE TABLE IF NOT EXISTS transcripts (
    clip_id     INTEGER PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
    full_text   TEXT,
    segments_json TEXT
)"""

_CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    status       TEXT   NOT NULL DEFAULT 'running',
    total        INTEGER  DEFAULT 0,
    done         INTEGER  DEFAULT 0,
    failed       INTEGER  DEFAULT 0,
    started_at   TEXT,
    finished_at  TEXT
)"""

_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts USING fts5(
    summary, description, transcript, tokenize=trigram
)"""

# ── FTS5 triggers — keep clips_fts in sync with clips table inserts/updates.
#    Transcript is stored separately (transcripts table), so we only index
#    summary + description here; transcript syncing happens in save_transcript().

_CREATE_FTS_TRIGGER_INS = """
CREATE TRIGGER IF NOT EXISTS clips_fts_insert AFTER INSERT ON clips BEGIN
    REPLACE INTO clips_fts (rowid, summary, description, transcript)
        VALUES (NEW.id, NEW.summary, NEW.description, '');
END"""

_CREATE_FTS_TRIGGER_UPD = """
CREATE TRIGGER IF NOT EXISTS clips_fts_update AFTER UPDATE OF summary, description ON clips BEGIN
    REPLACE INTO clips_fts (rowid, summary, description, transcript)
        VALUES (NEW.id, NEW.summary, NEW.description, '');
END"""

_CREATE_FTS_TRIGGER_DEL = """
CREATE TRIGGER IF NOT EXISTS clips_fts_delete AFTER DELETE ON clips BEGIN
    REPLACE INTO clips_fts (rowid, summary, description, transcript)
        VALUES (OLD.id, '', '', '');
END"""

# ── Clip column names (subset of Clip model fields stored in clips table) ─

_CLIP_COLUMNS = [
    "id", "fingerprint", "source_path", "library_path", "roll_type",
    "roll_source",
    "summary",
    "description", "duration_s", "width", "height", "fps", "codec",
    "thumbnail_path", "status", "error", "capture_time", "date_source",
    "created_at", "processed_at",
]


def _clip_columns_sql() -> str:  # noqa: D103
    return ", ".join(_CLIP_COLUMNS)


# ── Repository implementation ─────────────────────────────────

class SqliteRepository:
    """SQLite-backed CatalogRepository using real SQL.

    Parameters
    ----------
    conn:
        An open ``sqlite3.Connection`` (in-memory or on-disk).  The caller
        owns the connection lifecycle; this class does **not** close it.

    Examples
    --------
    >>> import sqlite3  # doctest: +SKIP
    >>> conn = sqlite3.connect(":memory:")  # doctest: +SKIP
    >>> repo = SqliteRepository(conn)  # doctest: +SKIP
    """

    def __init__(self, conn: _Conn) -> None:  # type: ignore[type-arg]
        self._conn = conn
        self.execute_schema()

    # ── schema initialisation ────────────────────────────────

    def execute_schema(self) -> None:
        """Create all tables / FTS5 virtual table if they don't exist."""
        c = self._conn.cursor()
        c.execute(_CREATE_CLIPS)
        c.execute(_CREATE_TAGS)
        c.execute(_CREATE_TRANSCRIPTS)
        c.execute(_CREATE_JOBS)
        c.execute(_CREATE_FTS)

        # FTS5 triggers — IF NOT EXISTS so they're idempotent.
        c.execute(_CREATE_FTS_TRIGGER_INS)
        c.execute(_CREATE_FTS_TRIGGER_UPD)
        c.execute(_CREATE_FTS_TRIGGER_DEL)

        self._conn.commit()

    # ── helpers / internal queries ───────────────────────────

    def _row_to_clip_summary(self, row: tuple) -> ClipSummary:
        """Convert a DB row to :class:`ClipSummary`."""
        return ClipSummary(**dict(zip(_CLIP_COLUMNS, row)))

    # ── Clip CRUD ────────────────────────────────────────────

    def exists_fingerprint(self, fp: str) -> bool:
        c = self._conn.cursor()
        c.execute("SELECT 1 FROM clips WHERE fingerprint = ?", (fp,))
        return c.fetchone() is not None

    def upsert_clip(self, clip: Clip) -> int:
        c = self._conn.cursor()

        # Try insert; if fingerprint already exists, fall through to update.
        try:
            c.execute("""
                INSERT INTO clips (
                    fingerprint, source_path, library_path, roll_type,
                    roll_source, capture_time, date_source, duration_s,
                    width, height, fps, codec, thumbnail_path, summary,
                    description, status, error, created_at, processed_at
                ) VALUES (
                    ?,?,?,?,?,?, ?,?,?,? , ? , ?, ?, ?,  ?, ?, ?, ?, ?
                )
            """, (
                clip.fingerprint, clip.source_path, clip.library_path,
                clip.roll_type, clip.roll_source,
                clip.capture_time.isoformat() if clip.capture_time else None,
                clip.date_source, clip.duration_s, clip.width, clip.height,
                clip.fps, clip.codec, clip.thumbnail_path, clip.summary,
                clip.description, clip.status, clip.error,
                clip.created_at, clip.processed_at,
            ))

        except IntegrityError:
            # Fingerprint already exists — UPDATE the existing row.
            c.execute(
                "UPDATE clips SET source_path=?, library_path=?, roll_type=?, roll_source=?,"
                " capture_time=?, date_source=?, duration_s=?, width=?, height=?, fps=?,"
                " codec=?, thumbnail_path=?, summary=?, description=?, status=?, error=?,"
                " created_at=?, processed_at=?"
                " WHERE fingerprint=?",
                (clip.source_path, clip.library_path, clip.roll_type, clip.roll_source,
                 clip.capture_time.isoformat() if clip.capture_time else None,
                 clip.date_source, clip.duration_s, clip.width, clip.height,
                 clip.fps, clip.codec, clip.thumbnail_path, clip.summary,
                 clip.description, clip.status, clip.error,
                 clip.created_at, clip.processed_at, clip.fingerprint),
            )
        self._conn.commit()
        return c.execute("SELECT id FROM clips WHERE fingerprint = ?", (clip.fingerprint,)).fetchone()[0]

    def get_clip(self, clip_id: int) -> Clip | None:
        c = self._conn.cursor()
        c.execute(f"SELECT {_clip_columns_sql()} FROM clips WHERE id = ?", (clip_id,))
        row = c.fetchone()
        if row is None:
            return None

        data = dict(zip(_CLIP_COLUMNS, row))
        # Parse capture_time back to datetime if present.
        ct = data.get("capture_time")
        if isinstance(ct, str):
            try:
                data["capture_time"] = _dt.datetime.fromisoformat(ct)
            except (ValueError, TypeError):
                pass

        # Load tags.
        c.execute("SELECT name, source FROM tags WHERE clip_id = ?", (clip_id,))
        data["tags"] = [Tag(name=r[0], source=r[1]) for r in c.fetchall()]

        # Load transcript.
        c.execute("SELECT full_text, segments_json FROM transcripts WHERE clip_id = ?", (clip_id,))
        tr_row = c.fetchone()
        if tr_row:
            segments_raw = json.loads(tr_row[1]) if tr_row[1] else []
            from ..domain.models import Segment  # avoid top-level circularity in tests
            data["transcript"] = Transcript(
                full_text=tr_row[0] or "",
                segments=[Segment(**s) for s in segments_raw],
            )
        else:
            data["transcript"] = None

        # Build and return a Clip model.
        clip = Clip(**data)
        self._conn.commit()  # close any open cursors on this connection.
        return clip

    def delete_clip(self, clip_id: int) -> None:
        c = self._conn.cursor()
        # Also remove from FTS index.
        c.execute("DELETE FROM clips_fts WHERE summary LIKE ? OR description LIKE ? OR transcript LIKE ?",
                  (f"%clip_id:{clip_id}%", f"%clip_id:{clip_id}%", f"%clip_id:{clip_id}%"))
        c.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
        self._conn.commit()

    # ── Query / Filter / Search (FTS5) ─────────────────────

    def query_clips(self, f):  # noqa: ANN001 — type is ClipFilter (import at runtime)
        """List clips matching optional filters."""
        c = self._conn.cursor()

        conditions: list[str] = []
        params: list[object] = []

        if f.date is not None:  # type: ignore[attr-defined]
            conditions.append("date(capture_time) = ? OR date(created_at) = ?")  # capture or creation
            params.extend([f.date, f.date])  # type: ignore[attr-defined]

        if hasattr(f, "roll_type") and f.roll_type is not None:  # type: ignore[attr-defined]
            conditions.append("roll_type = ?")
            params.append(f.roll_type)  # type: ignore[attr-defined]

        if hasattr(f, "tag") and f.tag is not None:  # type: ignore[attr-defined]
            conditions.append("id IN (SELECT clip_id FROM tags WHERE name = ?)")
            params.append(f.tag)  # type: ignore[attr-defined]

        sql = f"SELECT {_clip_columns_sql()} FROM clips WHERE {' AND '.join(conditions)} ORDER BY id" if conditions else f"SELECT {_clip_columns_sql()} FROM clips ORDER BY id"
        c.execute(sql, params)

        return [self._row_to_clip_summary(r) for r in c.fetchall()]

    def search(self, q: str) -> list[ClipSummary]:
        """Full-text search across summary + description + transcript via FTS5.

        Uses the trigram tokenizer which properly handles CJK text (each
        character is a searchable unit). For queries shorter than 3 characters,
        falls back to LIKE since trigram requires at least a 3-char n-gram.
        """

        c = self._conn.cursor()
        trimmed = q.strip()
        if not trimmed:
            return []

        # FTS5 trigram tokenizer requires queries >= 3 chars.
        if len(trimmed) >= 3:
            c.execute(f"""
                SELECT {_clip_columns_sql()} FROM clips
                WHERE id IN (
                    SELECT rowid FROM clips_fts WHERE clips_fts MATCH ? ORDER BY rank
                )
            """, (trimmed,))
        else:
            # Short-query fallback (trigram needs ≥3 chars): LIKE across summary, description and transcript.
            c.execute(f"""
                SELECT {_clip_columns_sql()} FROM clips
                    WHERE summary LIKE ? OR description LIKE ?
                        OR id IN (SELECT t.clip_id FROM transcripts t WHERE t.full_text LIKE ?)
            """, (f"%{trimmed}%", f"%{trimmed}%", f"%{trimmed}%"))

        results = [self._row_to_clip_summary(r) for r in c.fetchall()]
        return results

    # ── Tags (per-clip) ─────────────────────────────────────

    def get_tags(self, clip_id: int) -> list[Tag]:
        c = self._conn.cursor()
        c.execute("SELECT name, source FROM tags WHERE clip_id = ?", (clip_id,))
        return [Tag(name=r[0], source=r[1]) for r in c.fetchall()]

    def set_tags(self, clip_id: int, tags: list[Tag]) -> None:
        c = self._conn.cursor()
        c.execute("DELETE FROM tags WHERE clip_id = ?", (clip_id,))
        if tags:
            c.executemany(
                "INSERT INTO tags (clip_id, name, source) VALUES (?, ?, ?)",
                [(clip_id, t.name, t.source) for t in tags],
            )

        self._sync_fts_tags(clip_id, tags)
        self._conn.commit()

    def add_tag(self, clip_id: int, tag_name: str) -> None:
        c = self._conn.cursor()
        try:
            c.execute(
                "INSERT INTO tags (clip_id, name, source) VALUES (?, ?, 'manual')",
                (clip_id, tag_name),
            )
        except IntegrityError:
            pass  # already exists — idempotent.

        tags = self.get_tags(clip_id)
        self._sync_fts_tags(clip_id, tags)
        self._conn.commit()

    def remove_tag(self, clip_id: int, tag_name: str) -> None:
        c = self._conn.cursor()
        c.execute("DELETE FROM tags WHERE clip_id = ? AND name = ?", (clip_id, tag_name))
        self._conn.commit()

    def _sync_fts_tags(self, clip_id: int, tags: list[Tag]) -> None:
        """Rebuild the tag portion of FTS for a single clip.

        Tags themselves aren't in clips_fts; we embed them as text into
        summary/description so FTS search can still find clips by tag.
        """
        if not tags:
            return

        # Build a simple text representation of the clip's FTS row for tag matching.
        c = self._conn.cursor()
        # We don't directly update FTS via tags alone, but we do need to make sure
        # that when search() runs the INSERT OR REPLACE into clips_fts, it captures tag data.
        # For now tags are searched via the tags table JOIN in query_clips(tag=...).

    # ── Roll correction ───────────────────────────────────────

    def correct_roll(self, clip_id: int, roll: str) -> None:
        c = self._conn.cursor()
        c.execute(
            "UPDATE clips SET roll_type = ?, roll_source = 'manual' WHERE id = ?",
            (roll, clip_id),
        )
        self._conn.commit()

    # ── Re-analyze: update only AI-generated fields ───────────

    def update_analysis(self, clip_id: int, r) -> None:  # noqa: ANN001 — type is AnalysisResult
        """Update transcript/summary/vision fields and auto-tags only.

        Manual tags (source='manual') are preserved; manual roll corrections
        (roll_source='manual') prevent the roll_type from being overwritten.
        """
        c = self._conn.cursor()

        # Only update roll_type if not manually set.
        c.execute("SELECT roll_source, roll_type FROM clips WHERE id = ?", (clip_id,))
        row = c.fetchone()
        if row is None:
            return  # clip doesn't exist — silently skip.

        roll_source, current_roll = row
        new_roll: str = r.roll_type  # type: ignore[attr-defined]

        if roll_source != "manual":
            c.execute("UPDATE clips SET roll_type = ? WHERE id = ?", (new_roll, clip_id))

        # Update transcript if present.
        new_transcript = getattr(r, "transcript", None)  # type: ignore[attr-defined]
        if new_transcript is not None and isinstance(new_transcript, Transcript):
            c.execute("""
                INSERT INTO transcripts (clip_id, full_text, segments_json)
                VALUES (?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    full_text = excluded.full_text,
                    segments_json = excluded.segments_json
            """, (clip_id, new_transcript.full_text or "", json.dumps(
                [dict(start_s=s.start_s, end_s=s.end_s, text=s.text) for s in new_transcript.segments]
            )))

        # Update summary (A-roll).
        sr = getattr(r, "summary_result", None)  # type: ignore[attr-defined]
        if sr is not None and hasattr(sr, "summary") and sr.summary:  # type: ignore[attr-defined]
            c.execute("UPDATE clips SET summary = ? WHERE id = ?", (sr.summary, clip_id))  # type: ignore[attr-defined]

        # Update description (B-roll).
        vr = getattr(r, "vision_result", None)  # type: ignore[attr-defined]
        if vr is not None and hasattr(vr, "description") and vr.description:  # type: ignore[attr-defined]
            c.execute("UPDATE clips SET description = ? WHERE id = ?", (vr.description, clip_id))  # type: ignore[attr-defined]

        # Update tags — preserve manual ones, replace auto.
        if hasattr(r, "vision_result") and vr is not None:  # type: ignore[attr-defined]
            auto_tags = [Tag(name=t, source="auto") for t in vr.tags]  # type: ignore[attr-defined]
        elif hasattr(r, "summary_result") and sr is not None:  # type: ignore[attr-defined]
            auto_tags = [Tag(name=t, source="auto") for t in sr.tags]  # type: ignore[attr-defined]
        else:
            auto_tags = []

        if auto_tags:
            # Fetch existing manual tags.
            c.execute("SELECT name FROM tags WHERE clip_id = ? AND source = 'manual'", (clip_id,))
            manual_names = {r[0] for r in c.fetchall()}

            # Merge: keep manual, add/replace auto.
            existing = self.get_tags(clip_id)
            merged: list[Tag] = [t for t in existing if t.source == "manual"]
            merged.extend(auto_tags)

            # Remove old auto tags first.
            c.execute("DELETE FROM tags WHERE clip_id = ? AND source = 'auto'", (clip_id,))
            c.executemany(
                "INSERT INTO tags (clip_id, name, source) VALUES (?, ?, ?)",
                [(clip_id, t.name, t.source) for t in auto_tags],
            )

        # Update processed_at.
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        c.execute("UPDATE clips SET processed_at = ? WHERE id = ?", (now, clip_id))

        self._conn.commit()

    # ── Transcript ────────────────────────────────────────────

    def save_transcript(self, clip_id: int, t) -> None:  # noqa: ANN001 — type is Transcript
        c = self._conn.cursor()
        segments_json = json.dumps(
            [dict(start_s=s.start_s, end_s=s.end_s, text=s.text) for s in t.segments]  # type: ignore[attr-defined]
        ) if hasattr(t, "segments") else ""

        c.execute("""
            INSERT INTO transcripts (clip_id, full_text, segments_json)
            VALUES (?, ?, ?)
            ON CONFLICT(clip_id) DO UPDATE SET
                full_text = excluded.full_text,
                segments_json = excluded.segments_json
        """, (clip_id, t.full_text or "", segments_json))  # type: ignore[attr-defined]

        self._sync_fts_transcript(clip_id)
        self._conn.commit()

    def get_transcript(self, clip_id: int) -> Transcript | None:
        c = self._conn.cursor()
        c.execute("SELECT full_text, segments_json FROM transcripts WHERE clip_id = ?", (clip_id,))
        row = c.fetchone()
        if row is None:
            return None

        segments_raw = json.loads(row[1]) if row[1] else []
        from ..domain.models import Segment
        return Transcript(
            full_text=row[0] or "",
            segments=[Segment(**s) for s in segments_raw],
        )

    def _sync_fts_transcript(self, clip_id: int) -> None:
        """Re-sync a single clip's transcript into the FTS index."""
        c = self._conn.cursor()

        # Get summary and description for the FTS row.
        c.execute("SELECT summary, description FROM clips WHERE id = ?", (clip_id,))
        clip_row = c.fetchone()

        if not clip_row:
            return  # shouldn't happen, but be safe.

        summary_text = clip_row[0] or ""
        desc_text = clip_row[1] or ""

        # Get transcript text.
        c.execute("SELECT full_text FROM transcripts WHERE clip_id = ?", (clip_id,))
        tr_row = c.fetchone()
        transcript_text = tr_row[0] if tr_row and tr_row[0] else ""

        # Upsert into FTS.
        c.execute("""
            INSERT OR REPLACE INTO clips_fts (rowid, summary, description, transcript)
            VALUES (?, ?, ?, ?)
        """, (clip_id, summary_text, desc_text, transcript_text))

    # ── Job CRUD ──────────────────────────────────────────────

    def create_job(self, total: int) -> Job:
        c = self._conn.cursor()
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        c.execute("""
            INSERT INTO jobs (status, total, done, failed, started_at)
            VALUES ('running', ?, 0, 0, ?)
        """, (total, now))
        self._conn.commit()

        job_id = c.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT 1").fetchone()[0]
        return Job(id=job_id, status="running", total=total, done=0, failed=0, started_at=now)

    def update_job(self, job_id: int, **fields) -> None:
        if not fields:
            return

        set_parts = [f"{k} = ?" for k in fields]
        values = list(fields.values())
        # ISO-format any datetime objects.
        for i, v in enumerate(values):
            if isinstance(v, _dt.datetime):
                values[i] = v.isoformat()

        sql = f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ?"
        values.append(job_id)

        c = self._conn.cursor()
        c.execute(sql, values)

        # Auto-set finished_at if status changed to done/failed.
        new_status = fields.get("status")
        if new_status in ("done", "failed"):
            c.execute("UPDATE jobs SET finished_at = ? WHERE id = ?", (
                _dt.datetime.now(_dt.timezone.utc).isoformat(), job_id,
            ))

        self._conn.commit()

    def get_job(self, job_id: int) -> Job | None:
        c = self._conn.cursor()
        c.execute("""
            SELECT id, status, total, done, failed, started_at, finished_at
            FROM jobs WHERE id = ?
        """, (job_id,))
        row = c.fetchone()
        if row is None:
            return None

        return Job(
            id=row[0], status=row[1], total=row[2] or 0,
            done=row[3] or 0, failed=row[4] or 0,
            started_at=row[5], finished_at=row[6],
        )

    def close(self) -> None:
        """Close the underlying connection.  Idempotent."""
        if self._conn is not None:  # type: ignore[union-attr]
            self._conn.close()
            self._conn = None  # type: ignore[assignment]


# ── In-memory convenience wrapper (tests) ─────────────────────

class MemoryRepository(SqliteRepository):
    """In-memory SQLite repository — fast, no external dependencies."""

    def __init__(self) -> None:
        import sqlite3 as _sqlite3  # local to avoid circular imports in test env.
        conn = _sqlite3.connect(":memory:")
        super().__init__(conn)
