"""Prompt templates for :class:`~cutfinder.adapters.openai_text.OpenAITextSummarizer`.

Kept out of ``openai_text.py`` so that module stays request/response
plumbing only — the bilingual prompt文案 lives here.
"""

from __future__ import annotations

SUMMARIZE_PROMPT_ZH = """\
你是一个专业的视频内容整理助手。请根据以下A-roll（有解说）视频的转写文本，完成两件事：

1. **简介**：用中文撰写一段简洁的概述（30-80字），概括视频的核心内容和主题。
2. **标签**：提取5-10个关键词/短语作为标签，涵盖视频的主题、场景、情感等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"summary": "你的简介", "tags": ["标签1", "标签2", ...]}}

转写文本：
{transcript_text}
"""

SUMMARIZE_PROMPT_EN = """\
You are a professional video content organization assistant. Based on the \
transcript of the following A-roll (narrated) video, do two things:

1. **Summary**: Write a concise overview in English (30-80 words) capturing the \
core content and theme.
2. **Tags**: Extract 5-10 keywords/phrases as tags covering theme, scene, \
emotion, etc.

Reply ONLY in the following JSON format (no extra content):
{{"summary": "your summary", "tags": ["tag1", "tag2", ...]}}

Transcript:
{transcript_text}
"""

SUMMARIZE_PROMPTS = {"zh": SUMMARIZE_PROMPT_ZH, "en": SUMMARIZE_PROMPT_EN}

CUTS_PROMPT_ZH = """\
你是专业的视频剪辑助手。下面是一段 A-roll（有解说）视频的转写，已按句子编号并标注时间。\
请挑出最值得保留、最精彩或信息量最大的最多 {n} 段，按精彩程度从高到低排序。

要求：
- 每段用**起始句子编号**和**结束句子编号**表示（可只含一句，即 start == end）。
- 只能使用下面列出的句子编号，不要编造时间。
- 每段给一句话理由。

请仅以如下 JSON 回复（不要其他内容）：
{{"cuts": [{{"start": 起始编号, "end": 结束编号, "reason": "理由"}}, ...]}}

句子列表：
{segments}
"""

CUTS_PROMPT_EN = """\
You are a professional video editing assistant. Below is the transcript of an \
A-roll (narrated) video, numbered by sentence with timestamps. Pick up to {n} \
best stretches to keep — the most compelling or information-rich — ranked best first.

Rules:
- Express each stretch by its **start sentence index** and **end sentence index** \
(a single sentence is fine: start == end).
- Use only the sentence indices listed below; do not invent timecodes.
- Give a one-line reason for each.

Reply ONLY as the following JSON (no extra content):
{{"cuts": [{{"start": start_index, "end": end_index, "reason": "reason"}}, ...]}}

Sentences:
{segments}
"""

CUTS_PROMPTS = {"zh": CUTS_PROMPT_ZH, "en": CUTS_PROMPT_EN}
