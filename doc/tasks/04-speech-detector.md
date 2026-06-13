# 04 · SpeechDetector 人声检测（A/B 判定信号）

> Silero VAD 算出人声占比，供编排层按阈值判 A/B。
> **依赖**：00。 **接口**：`ports/speech.py:SpeechDetector`。 **详见** detailed-design §3.4。

## 子任务
- [ ] `adapters/silero_vad.py:SileroSpeechDetector.speech_ratio(path) -> float`（0..1）
- [ ] 抽音轨（ffmpeg）→ Silero VAD → 计算有人声时长占比
- [ ] `tests/fakes/`：返回设定比例的假实现

## 完成标准（DoD）
- [ ] 单测：mock VAD 输出片段 → 断言占比计算正确
- [ ] 集成测 `@integration`：`MVI_5298`(A) 占比 ≥ 阈值；`MVI_5368`/`DJI_…`(B) < 阈值
