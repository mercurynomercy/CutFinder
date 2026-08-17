"""Prompt templates for :class:`~cutfinder.adapters.openai_vision.OpenAIVisionTagger`.

Kept out of ``openai_vision.py`` so that module stays request/response
plumbing only — the bilingual prompt文案 lives here.
"""

from __future__ import annotations

VISION_PROMPT_ZH = """\
你是一个专业的视频画面分析助手。请仔细观察以下多张从视频中提取的画面帧，完成两件事：

1. **画面描述**：用中文撰写一段简洁的描述（30-80字），概括这些帧中看到的视觉内容、场景、人物动作等。
2. **标签**：提取5-10个关键词/短语作为视觉标签，涵盖场景、物体、色彩、氛围等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"description": "你的画面描述", "tags": ["标签1", "标签2", ...]}}

以下是多帧画面（按时间顺序排列）：
"""

VISION_PROMPT_EN = """\
You are a professional video frame analysis assistant. Carefully examine the \
following frames extracted from a video and do two things:

1. **Description**: Write a concise description in English (30-80 words) \
summarizing the visual content, scenes, and actions seen in these frames.
2. **Tags**: Extract 5-10 keywords/phrases as visual tags covering scene, \
objects, color, mood, etc.

Reply ONLY in the following JSON format (no extra content):
{{"description": "your description", "tags": ["tag1", "tag2", ...]}}

The frames below are in chronological order:
"""

VISION_PROMPTS = {"zh": VISION_PROMPT_ZH, "en": VISION_PROMPT_EN}

KEYFRAMES_PROMPT_ZH = """\
你是专业的视频剪辑助手。下面按时间顺序给出从一段 B-roll（无解说）视频采样的若干帧，\
每帧标注了编号和时间戳。请挑出画面最好、最适合做封面或剪辑代表的最多 {n} 帧，按好坏排序。

只能使用下面列出的帧编号。请仅以如下 JSON 回复（不要其他内容）：
{{"keyframes": [{{"index": 帧编号, "reason": "一句话理由"}}, ...]}}

帧清单（编号 / 时间）：
{frames}
"""

KEYFRAMES_PROMPT_EN = """\
You are a professional video editing assistant. Below are frames sampled in \
chronological order from a B-roll (no narration) video, each labeled with an \
index and timestamp. Pick up to {n} best frames — most striking / best as a \
cover or edit representative — ranked best first.

Use only the frame indices listed below. Reply ONLY as the following JSON \
(no extra content):
{{"keyframes": [{{"index": frame_index, "reason": "one-line reason"}}, ...]}}

Frames (index / time):
{frames}
"""

KEYFRAMES_PROMPTS = {"zh": KEYFRAMES_PROMPT_ZH, "en": KEYFRAMES_PROMPT_EN}
