# 05 · Transcriber 语音转写

> mlx-whisper 把 A-roll 中文解说转成全文 + 分段时间码。**独立进程，不走 OMLX。**
> **依赖**：00。 **接口**：`ports/speech.py:Transcriber`。 **详见** detailed-design §3.5。

## 子任务
- [x] `adapters/mlx_whisper.py:MlxWhisperTranscriber.transcribe(path) -> Transcript`
- [x] 映射结果 → `Transcript(full_text, segments=[Segment(start_s,end_s,text)])`
- [x] 模型档位读配置（默认 `large-v3`）— 构造函数支持 `model`/`language` 参数
- [x] `tests/fakes/`：返回固定 `Transcript`

## 完成标准（DoD）
- [x] 单测：mock whisper 输出 → 断言映射为 `Transcript`（15 tests, all pass）
- [x] 集成测 `@integration`：`MVI_5298` 真转写，断言 `full_text` 非空且含中文（代码已写好，mlx-whisper 未安装时自动 skip）
