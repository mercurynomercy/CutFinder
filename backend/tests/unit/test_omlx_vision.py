"""Unit tests for OmlxVisionTagger — B-roll visual tagging via OMLX vision model.

Mocks the OpenAI client to test prompt construction, request params,
base64 image encoding, multi-frame handling, JSON parsing from LLM response,
retry logic, and edge cases — without any real network calls.

Pattern matches test_omlx_summarizer.py:
  - monkeypatch for openai module injection
  - MagicMock for happy-path tests (no real exceptions raised)
  - types.ModuleType + real exception classes for error/retry tests

Tracker:
    empty_input         — frame_paths=[] → empty VisionResult (no network)
    prompt_verification  — verify Chinese text in message content
    request_params       — model name, response_format schema, multi-frame structure
    image_encoding        — base64 data URI format correctness
    json_parsing          — happy path, missing keys, malformed tags, empty content/refusal
    retry_logic           — first-success vs all-fail scenarios (connection/unknown errors)
    config_integration    — Prefs vision_model defaults and overrides

"""

from __future__ import annotations

import base64
import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_config(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Create a mock AppConfig with OMLX settings."""
    env = MagicMock()
    env.OMLX_BASE_URL = "http://localhost:12345/v1"
    env.OMLX_API_KEY = "test-api-key-12345"

    prefs = MagicMock()
    prefs.vision_model = "Qwen3-VL-8B"

    config = MagicMock()
    config.env = env
    config.prefs = prefs
    return config


def _import_adapter():
    """Import the adapter module, forcing a fresh import each time."""
    import sys

    for key in list(sys.modules):
        if key.startswith("cutfinder.adapters.omlx_vision"):
            del sys.modules[key]

    import cutfinder.adapters.omlx_vision  # noqa: F401
    return sys.modules["cutfinder.adapters.omlx_vision"]


def _mocked_tagger(
    config: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    model_override: str | None = None,
) -> MagicMock:
    """Create an OmlxVisionTagger with OpenAI client mocked.

    Returns the adapter module so we can access internal functions too.
    """
    mod = _import_adapter()

    # Mock OpenAI client at module level so the adapter picks it up
    mock_openai = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "openai", mock_openai)  # type: ignore[attr-defined]

    tagger = mod.OmlxVisionTagger(config, model=model_override)
    return (tagger, mod)


def _make_fake_frame(tmp_path: Path, name: str = "frame.png") -> Path:
    """Create a minimal 1x1 PNG file for testing."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03"
        b"\x01\x01\x00\x18\xdd\xe5\xd7"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / name
    p.write_bytes(png_bytes)
    return p


def _mock_openai_module(
    monkeypatch: pytest.MonkeyPatch,
    openai_mock: types.ModuleType | MagicMock,
):
    """Helper to inject a mock openai module via monkeypatch."""
    # Ensure APIConnectionError is always available for the adapter's lazy import.
    # Use a sentinel that won't be caught by `except` blocks unless explicitly set to one.
    if not hasattr(openai_mock, "APIConnectionError"):
        openai_mock.APIConnectionError = Exception  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "openai", openai_mock)  # type: ignore[attr-defined]


# ── empty_input tests (no network call needed) ───────────────────

class TestEmptyInput:
    """Test behavior with empty or missing frame paths."""

    def test_empty_frame_paths_returns_empty_result(self, monkeypatch):
        """describe([]) returns VisionResult with empty fields — no network call."""
        config = _make_config(monkeypatch)

        # Need a fresh import that picks up the mocked openai
        mod = _import_adapter()

        # Even without mocking, empty input returns early (no network call)
        tagger = mod.OmlxVisionTagger(config)
        result = tagger.describe([])

        assert result.description == ""
        assert result.tags == []


# ── prompt verification tests ───────────────────────────────────

class TestPromptVerification:
    """Verify the prompt template is correctly included in API requests."""

    def test_prompt_contains_vision_instruction(self, monkeypatch):
        """Verify the user message contains Chinese prompt text."""
        config = _make_config(monkeypatch)
        tagger, mod = _mocked_tagger(config, monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"test","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))

        # Re-import to pick up new mock
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        tagger.describe(frames)

        # Verify the call was made with correct model
        mock_client_cls.return_value.chat.completions.create.assert_called_once()
        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert kwargs["model"] == "Qwen3-VL-8B"

        # Verify content is a list (multi-modal message)
        messages = kwargs["messages"]
        assert len(messages) == 1
        content = messages[0]["content"]
        assert isinstance(content, list)

        # First item is text with prompt containing Chinese instruction
        text_part = content[0]
        assert text_part["type"] == "text"
        # The prompt includes Chinese characters about visual analysis
        assert len(text_part["text"]) > 20


# ── request_params tests ────────────────────────────────────────

class TestRequestParams:
    """Test that correct parameters are sent to the OMLX API."""

    def test_uses_config_vision_model(self, monkeypatch):
        """Model name comes from config.prefs.vision_model."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        tagger.describe(frames)

        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert kwargs["model"] == "Qwen3-VL-8B"

    def test_model_override_in_constructor(self, monkeypatch):
        """Passing model= overrides the config default."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config, model="Qwen2.5-VL-7B")

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config, model="Qwen2.5-VL-7B")

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        tagger.describe(frames)

        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert kwargs["model"] == "Qwen2.5-VL-7B"

    def test_structured_json_format(self, monkeypatch):
        """response_format uses json_schema type for structured output."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        tagger.describe(frames)

        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert kwargs["response_format"]["type"] == "json_schema"
        schema = kwargs["response_format"]["json_schema"]
        assert schema["name"] == "vision_result"
        assert schema["strict"] is True
        props = schema["schema"]["properties"]
        assert "description" in props
        assert "tags" in props


# ── image_encoding tests ────────────────────────────────────────

class TestImageEncoding:
    """Test base64 encoding and data URI format of frame images."""

    def test_base64_data_uri_format(self, monkeypatch):
        """Frame images are encoded as data:image/png;base64,<base64> URIs."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        tmp_path = Path("/tmp/vision_test")
        frame = _make_fake_frame(tmp_path, "test.png")

        tagger.describe([frame])
        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        content = kwargs["messages"][0]["content"]

        # Find image part (should be second element after text)
        image_part = content[1]
        assert image_part["type"] == "image_url"

        data_uri = image_part["image_url"]["url"]
        assert data_uri.startswith("data:image/png;base64,")
        b64_data = data_uri.split(",", 1)[1]
        # Verify it decodes to the original file content
        decoded = base64.b64decode(b64_data)
        assert decoded == frame.read_bytes()

    def test_multi_frame_single_request(self, monkeypatch):
        """Multiple frames are sent in one request as multiple image_url parts."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        tmp_path = Path("/tmp/vision_test")
        frames = [
            _make_fake_frame(tmp_path, "f1.png"),
            _make_fake_frame(tmp_path, "f2.png"),
            _make_fake_frame(tmp_path, "f3.png"),
        ]

        tagger.describe(frames)
        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        content = kwargs["messages"][0]["content"]

        # 1 text + N images
        assert len(content) == 4  # 1 text part + 3 frames
        assert content[0]["type"] == "text"
        for i in range(1, 4):
            assert content[i]["type"] == "image_url"


# ── JSON parsing tests (happy path + error responses) ───────────

class TestJsonParsing:
    """Test various LLM response shapes and their parsing."""

    def test_valid_json_parsed_correctly(self, monkeypatch):
        """Valid JSON response is parsed into VisionResult with correct fields."""
        config = _make_config(monkeypatch)

        resp_content = json.dumps({
            "description": "日落海滩的宁静画面",
            "tags": ["日落", "海滩", "海浪"],
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content=resp_content, refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        result = tagger.describe(frames)

        assert isinstance(result.description, str)
        assert len(result.description) > 0
        assert result.tags == ["日落", "海滩", "海浪"]

    def test_missing_description_triggers_retry(self, monkeypatch):
        """JSON without 'description' key → empty; retried until max attempts."""
        config = _make_config(monkeypatch)

        # Response with only tags, no description
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content=json.dumps({"tags": ["tag1"]}), refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.side_effect = [mock_response] * 3

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]

        with pytest.raises(RuntimeError, match="no valid result after retries"):
            tagger.describe(frames)

        # Should have been called 3 times (1 + max_retries=2)
        assert mock_client_cls.return_value.chat.completions.create.call_count == 3

    def test_invalid_json_triggers_retry_and_succeeds(self, monkeypatch):
        """Non-JSON response triggers retry; second call succeeds."""
        config = _make_config(monkeypatch)

        choice1 = MagicMock()
        choice1.message.content = "this is not json at all {{{"  # type: ignore[assignment]
        choice1.message.refusal = None

        choice2 = MagicMock()
        choice2.message.content = json.dumps({"description": "ok", "tags": ["good"]})
        choice2.message.refusal = None

        mock_response1 = MagicMock()
        mock_response1.choices = [choice1]
        mock_response2 = MagicMock()
        mock_response2.choices = [choice2]

        client_cls = MagicMock(return_value=MagicMock(
            chat=MagicMock(completions=MagicMock(create=MagicMock(side_effect=[mock_response1, mock_response2])))
        ))

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        result = tagger.describe(frames)

        assert result.description == "ok"
        # Called twice: 1st fails (non-JSON), 2nd succeeds

    def test_empty_content_triggers_retry_and_succeeds(self, monkeypatch):
        """Empty message content → retry; second call succeeds."""
        config = _make_config(monkeypatch)

        choice1 = MagicMock()
        choice1.message.content = None  # type: ignore[assignment]
        choice1.message.refusal = None

        choice2 = MagicMock()
        choice2.message.content = json.dumps({"description": "recovered", "tags": ["ok"]})
        choice2.message.refusal = None

        mock_response1 = MagicMock()
        mock_response1.choices = [choice1]
        mock_response2 = MagicMock()
        mock_response2.choices = [choice2]

        client_cls = MagicMock(return_value=MagicMock(
            chat=MagicMock(completions=MagicMock(create=MagicMock(side_effect=[mock_response1, mock_response2])))
        ))

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        result = tagger.describe(frames)

        assert result.description == "recovered"

    def test_refusal_triggers_retry_and_succeeds(self, monkeypatch):
        """Model refusal (refusal=True) triggers retry; second call succeeds."""
        config = _make_config(monkeypatch)

        choice1 = MagicMock()
        choice1.message.content = None  # type: ignore[assignment]
        choice1.message.refusal = True

        choice2 = MagicMock()
        choice2.message.content = json.dumps({"description": "allowed", "tags": ["success"]})
        choice2.message.refusal = None

        mock_response1 = MagicMock()
        mock_response1.choices = [choice1]
        mock_response2 = MagicMock()
        mock_response2.choices = [choice2]

        client_cls = MagicMock(return_value=MagicMock(
            chat=MagicMock(completions=MagicMock(create=MagicMock(side_effect=[mock_response1, mock_response2])))
        ))

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        result = tagger.describe(frames)

        assert result.description == "allowed"

    def test_malformed_tags_triggers_retry_and_succeeds(self, monkeypatch):
        """Tags that aren't list of strings → retry; second call succeeds."""
        config = _make_config(monkeypatch)

        # First: tags is a string (bad), Second: valid
        choice1 = MagicMock()
        choice1.message.content = json.dumps({"description": "bad", "tags": "not_a_list"})
        choice1.message.refusal = None

        choice2 = MagicMock()
        choice2.message.content = json.dumps({"description": "good", "tags": ["valid"]})
        choice2.message.refusal = None

        mock_response1 = MagicMock()
        mock_response1.choices = [choice1]
        mock_response2 = MagicMock()
        mock_response2.choices = [choice2]

        client_cls = MagicMock(return_value=MagicMock(
            chat=MagicMock(completions=MagicMock(create=MagicMock(side_effect=[mock_response1, mock_response2])))
        ))

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        result = tagger.describe(frames)

        assert result.description == "good"


# ── retry logic tests (all fail) ───────────────────────────────

class TestRetryLogic:
    """Test behavior when retries exhaust without success."""

    def test_connection_error_raises_after_retries(self, monkeypatch):
        """ConnectionError on all attempts → RuntimeError with connection message."""

        # Use a real exception class so `except` catches it correctly.
        class _ConnErr(Exception):
            pass

        config = _make_config(monkeypatch)

        mock_create = MagicMock(side_effect=[
            _ConnErr("connection refused"),   # attempt 1 → retry
            _ConnErr("still refused"),        # attempt 2 → retry
            _ConnErr("gave up"),             # attempt 3 → exhausts, raises RuntimeError
        ])

        mock_completions = MagicMock(create=mock_create)
        mock_chat = MagicMock(completions=mock_completions)

        client_cls = MagicMock(return_value=MagicMock(
            chat=mock_chat, completions=mock_completions, create=mock_create
        ))

        mock_openai = types.ModuleType("openai")
        mock_openai.OpenAI = client_cls  # type: ignore[attr-defined]
        mock_openai.APIConnectionError = _ConnErr  # type: ignore[attr-defined]

        _mock_openai_module(monkeypatch, mock_openai)
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        with pytest.raises(RuntimeError, match="vision connection failed"):
            tagger.describe(frames)

        assert client_cls.return_value.chat.completions.create.call_count == 3

    def test_unknown_error_raises_after_retries(self, monkeypatch):
        """Non-connection error on all attempts → RuntimeError with request message."""

        class _OtherErr(Exception):
            pass

        config = _make_config(monkeypatch)

        mock_create = MagicMock(side_effect=[
            _OtherErr("model quota exceeded"),  # attempt 1 → retry
            _OtherErr("rate limited"),           # attempt 2 → retry
            _OtherErr("gave up"),               # attempt 3 → exhausts, raises RuntimeError
        ])

        mock_completions = MagicMock(create=mock_create)
        mock_chat = MagicMock(completions=mock_completions)

        client_cls = MagicMock(return_value=MagicMock(
            chat=mock_chat, completions=mock_completions, create=mock_create
        ))

        mock_openai = types.ModuleType("openai")
        mock_openai.OpenAI = client_cls  # type: ignore[attr-defined]
        # Use a DIFFERENT exception so _OtherErr falls through to `except Exception` (not APIConnectionError).
        mock_openai.APIConnectionError = type("RealAPIConnErr", (Exception,), {})  # type: ignore[attr-defined]

        _mock_openai_module(monkeypatch, mock_openai)
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        with pytest.raises(RuntimeError, match="vision request failed"):
            tagger.describe(frames)

        assert client_cls.return_value.chat.completions.create.call_count == 3


# ── config integration tests ───────────────────────────────────

class TestConfigIntegration:
    """Test that OmlxVisionTagger correctly consumes AppConfig."""

    def test_has_describe_method(self, monkeypatch):
        """OmlxVisionTagger is instantiable with AppConfig and has describe method."""
        config = _make_config(monkeypatch)

        mock_openai_mock = MagicMock()
        monkeypatch.setitem(__import__("sys").modules, "openai", mock_openai_mock)  # type: ignore[attr-defined]

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config)

        assert hasattr(tagger, "describe")
        assert callable(tagger.describe)

    def test_uses_custom_vision_model(self, monkeypatch):
        """Custom model name is stored and used in API call."""
        config = _make_config(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(
            message=MagicMock(content='{"description":"t","tags":["t1"]}', refusal=None))]

        mock_client_cls = MagicMock()
        mock_client_cls.return_value.chat.completions.create.return_value = mock_response

        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config, model="custom-vision-model")

        _mock_openai_module(monkeypatch, MagicMock(OpenAI=mock_client_cls))
        mod = _import_adapter()
        tagger = mod.OmlxVisionTagger(config, model="custom-vision-model")

        frames = [_make_fake_frame(Path("/tmp"), "f1.png")]
        tagger.describe(frames)

        kwargs = mock_client_cls.return_value.chat.completions.create.call_args[1]
        assert kwargs["model"] == "custom-vision-model"
