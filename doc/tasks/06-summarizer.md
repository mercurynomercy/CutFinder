# 06 · Summarizer 文本总结（OMLX）

> 把 A-roll 转写文本交给 OMLX 文本模型，生成中文简介 + 标签。
> **依赖**：00、01。 **接口**：`ports/ai.py:Summarizer`。 **详见** detailed-design §3.6。

## 子任务
- [x] `adapters/omlx_text.py:OmlxSummarizer`：OpenAI 客户端 `base_url=OMLX_BASE_URL`、`api_key=OMLX_API_KEY`（来自全局配置 / OS env）
- [x] `summarize(transcript_text) -> SummaryResult`：`model=text_model`(默认 `Qwen3.6-35B-A3B`)，结构化输出 `{summary, tags}`
- [x] 提示词模板（中文简介 + 标签）
- [x] `tests/fakes/`：返回固定 `SummaryResult`

## 完成标准（DoD）
- [x] 单测：mock OpenAI 客户端 → 断言请求参数（model/messages）与 JSON 解析
- [x] 集成测 `@integration`：真 OMLX，喂一段中文文本，断言返回非空简介与标签
