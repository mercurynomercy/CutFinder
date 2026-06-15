"""Tests for the lenient JSON-object extractor used by the OMLX adapters."""

from __future__ import annotations

from cutfinder.adapters._jsonparse import parse_json_object


class TestParseJsonObject:
    def test_plain_json(self) -> None:
        assert parse_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_fenced_json(self) -> None:
        text = '```json\n{"summary": "hi", "tags": ["t1"]}\n```'
        assert parse_json_object(text) == {"summary": "hi", "tags": ["t1"]}

    def test_fenced_without_lang(self) -> None:
        assert parse_json_object('```\n{"x": 1}\n```') == {"x": 1}

    def test_json_embedded_in_prose(self) -> None:
        text = '好的，结果如下：{"description": "湖", "tags": ["水"]} 希望有帮助。'
        assert parse_json_object(text) == {"description": "湖", "tags": ["水"]}

    def test_none_and_empty(self) -> None:
        assert parse_json_object(None) is None
        assert parse_json_object("") is None
        assert parse_json_object("   ") is None

    def test_non_object_json_returns_none(self) -> None:
        # A bare array / scalar is not a JSON *object*.
        assert parse_json_object("[1, 2, 3]") is None
        assert parse_json_object('"just a string"') is None

    def test_unparseable_returns_none(self) -> None:
        assert parse_json_object("not json at all") is None
        assert parse_json_object("{broken: ") is None
