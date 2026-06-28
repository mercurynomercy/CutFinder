"""Tests for :mod:`cutfinder.pipeline.subtitle_exporter`."""

from __future__ import annotations

from pathlib import Path

from cutfinder.domain.models import Segment
from cutfinder.pipeline.subtitle_exporter import SubtitleExporter
from tests.fakes import FakeProbe, FakeTranscriber


def _exporter(fps: float = 25.0) -> tuple[SubtitleExporter, FakeTranscriber]:
    transcriber = FakeTranscriber(
        full_text="你好",
        segments=[Segment(start_s=0.0, end_s=1.0, text="你好")],
    )
    exporter = SubtitleExporter(probe=FakeProbe(fps=fps), transcriber=transcriber)
    return exporter, transcriber


def test_language_forwarded_to_transcribe(tmp_path: Path) -> None:
    exporter, transcriber = _exporter()
    exporter.export(tmp_path / "v.mp4", tmp_path, ["srt"], "en")
    assert transcriber.languages == ["en"]


def test_on_progress_forwarded_to_transcribe(tmp_path: Path) -> None:
    exporter, transcriber = _exporter()

    def cb(_f: float) -> None:
        return None

    exporter.export(tmp_path / "v.mp4", tmp_path, ["srt"], "zh", on_progress=cb)
    assert transcriber.progress_callbacks == [cb]


def test_writes_named_files_per_format(tmp_path: Path) -> None:
    exporter, _ = _exporter()
    paths = exporter.export(tmp_path / "myvideo.mp4", tmp_path, ["itt", "srt"], "zh")

    assert [p.name for p in paths] == ["myvideo.zh.itt", "myvideo.zh.srt"]
    assert all(p.exists() for p in paths)
    # iTT content uses dotted timecode + header; SRT uses comma.
    assert "00:00:01.000" in (tmp_path / "myvideo.zh.itt").read_text(encoding="utf-8")
    assert "00:00:01,000" in (tmp_path / "myvideo.zh.srt").read_text(encoding="utf-8")


def test_unknown_format_skipped(tmp_path: Path) -> None:
    exporter, _ = _exporter()
    paths = exporter.export(tmp_path / "v.mp4", tmp_path, ["srt", "vtt"], "zh")
    assert [p.name for p in paths] == ["v.zh.srt"]


def test_non_overwrite_appends_suffix(tmp_path: Path) -> None:
    exporter, _ = _exporter()
    # Pre-create the target name so the exporter must avoid clobbering it.
    (tmp_path / "v.zh.srt").write_text("existing", encoding="utf-8")

    paths = exporter.export(tmp_path / "v.mp4", tmp_path, ["srt"], "zh")
    assert paths[0].name == "v.zh (1).srt"
    assert (tmp_path / "v.zh.srt").read_text(encoding="utf-8") == "existing"
    assert paths[0].exists()

    # A second run bumps the suffix again.
    paths2 = exporter.export(tmp_path / "v.mp4", tmp_path, ["srt"], "zh")
    assert paths2[0].name == "v.zh (2).srt"


def test_returned_paths_exist(tmp_path: Path) -> None:
    exporter, _ = _exporter()
    paths = exporter.export(tmp_path / "v.mp4", tmp_path, ["itt", "srt"], "zh")
    assert paths and all(p.is_file() for p in paths)


def test_min_cue_duration_extends_short_cue(tmp_path: Path) -> None:
    # A 0.3s cue with no following cue is held to the 3s minimum on export.
    transcriber = FakeTranscriber(
        full_text="好", segments=[Segment(start_s=1.0, end_s=1.3, text="好")],
    )
    exporter = SubtitleExporter(probe=FakeProbe(fps=25.0), transcriber=transcriber)
    exporter.export(tmp_path / "v.mp4", tmp_path, ["srt"], "zh", min_cue_s=3.0)
    srt = (tmp_path / "v.zh.srt").read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:04,000" in srt
