# 02 · MetadataProbe 元数据探测

> 用 ffprobe 读拍摄时间/时长/分辨率/编码/有无音轨。
> **依赖**：00。 **接口**：`ports/probe.py:MetadataProbe`。 **详见** detailed-design §3.2。

## 子任务
- [ ] `adapters/ffmpeg_probe.py:FfmpegProbe`：调 `ffprobe -show_format -show_streams -print_format json`
- [ ] 解析 → `VideoMetadata`：`capture_time`（`format.tags.creation_time`）、`duration_s`、`width/height`、`fps`、`codec`、`has_audio`
- [ ] 无内嵌时间 → 回退 `st_birthtime`，`date_source="file"`；有则 `"embedded"`
- [ ] `tests/fakes/fake_probe.py`：返回固定 `VideoMetadata`

## 完成标准（DoD）
- [ ] 单测：喂样例 ffprobe JSON（dict）→ 断言解析正确、时间回退逻辑（不跑真 ffprobe）
- [ ] 集成测 `@pytest.mark.integration`：对 `testVideo/MVI_5298.MP4` 真解析，断言字段非空
