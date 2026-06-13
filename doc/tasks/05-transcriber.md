# 05 · Transcriber 语音转写

> mlx-whisper 把 A-roll 中文解说转成全文 + 分段时间码。**独立进程，不走 OMLX。**
> **依赖**：00。 **接口**：`ports/speech.py:Transcriber`。 **详见** detailed-design §3.5。

## 子任务
- [ ] `adapters/mlx_whisper.py:MlxWhisperTranscriber.transcribe(path) -> Transcript`
- [ ] 映射结果 → `Transcript(full_text, segments=[Segment(start_s,end_s,text)])`
- [ ] 模型档位读配置（默认 `large-v3`）
- [ ] `tests/fakes/`：返回固定 `Transcript`

## 完成标准（DoD）
- [ ] 单测：mock whisper 输出 → 断言映射为 `Transcript`
- [ ] 集成测 `@integration`：`MVI_5298` 真转写，断言 `full_text` 非空且含中文
