"""Integration test for LLM subtitle segmentation against a real OpenAI-compatible server.

Marked ``@pytest.mark.integration``; run with ``-m integration``. Skipped when
the server is not configured or unreachable.
"""

from __future__ import annotations

import pytest

openai = pytest.importorskip("openai")

_TEXT = (
    "大家好，今天我们来到了云南大理，这里的天气特别好，蓝天白云，洱海就在眼前。"
    "我们先去古城里面逛了一圈，买了很多好吃的小吃，还拍了不少照片留作纪念。"
    "下午我们租了一辆电动车沿着洱海骑行，风吹在脸上特别舒服，路边的风景也非常美丽。"
    "晚上我们回到客栈，和朋友们一起聊天喝茶，度过了愉快的一天。"
)


def _load_config():
    from cutfinder.config import AppConfig, Prefs, resolve_env

    env = resolve_env()
    if not (env.OPENAI_BASE_URL and env.OPENAI_API_KEY):
        pytest.skip("OpenAI-compatible server not configured (set it in the Settings UI or via env vars)")
    return AppConfig(env=env, prefs=Prefs())


@pytest.mark.integration
def test_llm_assemble_cues_real_server_preserves_text_and_width():
    from cutfinder.adapters.llm_cues import llm_assemble_cues
    from cutfinder.adapters.llm_segmenter import OpenAICueSegmenter
    from cutfinder.adapters.qwen_transcriber import _display_width
    from cutfinder.ports.speech import SegmenterUnavailable

    config = _load_config()
    segmenter = OpenAICueSegmenter(config)
    tokens = [(c, 0.2 * i, 0.2 * i + 0.2) for i, c in enumerate(_TEXT)]

    try:
        probe = segmenter.split("你好，世界。")
    except SegmenterUnavailable:
        pytest.skip("OpenAI-compatible server configured but unreachable")
    del probe

    cues = llm_assemble_cues(
        [tokens],
        segmenter,
        max_chars=18,
        max_dur=6.0,
        gap_s=0.7,
        merge_gap_s=1.5,
        merge_short_max=4,
        merge_short_dur=1.0,
    )

    assert cues
    joined = "".join(c.text for c in cues)
    strip = lambda s: "".join(s.split())
    # Cleaning may drop trailing punctuation, so compare without it.
    punct = "，。！？、；：,.!?;:"
    assert strip(joined).translate({ord(p): None for p in punct}) == strip(_TEXT).translate(
        {ord(p): None for p in punct}
    )
    for c in cues:
        assert _display_width(c.text) <= 24
