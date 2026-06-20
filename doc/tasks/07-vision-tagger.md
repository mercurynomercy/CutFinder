# 07 · VisionTagger 画面识别（OMLX）

> 把 B-roll 抽帧（base64）交给 OMLX 视觉模型，生成中文画面描述 + 标签。
> **依赖**：00、01、03。 **接口**：`ports/ai.py:VisionTagger`。 **详见** detailed-design §3.7。

## 子任务
- [x] `adapters/omlx_vision.py:OmlxVisionTagger`：同样用全局配置 / OS env 的 base_url/api_key
- [x] `describe(frame_paths) -> VisionResult`：读帧 → base64 data URI → OpenAI 视觉消息（一次请求带多帧），`model=vision_model`(默认 `Qwen3-VL-8B`)，结构化输出 `{description, tags}`
- [x] 提示词模板（中文画面描述 + 标签）
- [x] `tests/fakes/`：返回固定 `VisionResult`

## 完成标准（DoD）
- [x] 单测：mock 客户端 → 断言 base64 编码、image_url 消息结构、JSON 解析（17 tests pass）
- [x] 集成测 `@integration`：真 OMLX，对 B-roll 抽帧，断言返回非空描述与标签
