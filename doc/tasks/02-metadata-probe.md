# 02 · MetadataProbe 元数据探测

> 用 ffprobe 读拍摄时间/时长/分辨率/编码/有无音轨。
> **依赖**：00。 **接口**：`ports/probe.py:MetadataProbe`。 **详见** detailed-design §3.2。

## 子任务
- [x] `adapters/ffmpeg_probe.py:FfmpegProbe`：调 `ffprobe -show_format -show_streams -of json`
- [x] 解析 → `VideoMetadata`：`capture_time`（`format.tags.creation_time`）、`duration_s`、`width/height`、`fps`、`codec`、`has_audio`
- [x] 无内嵌时间 → 回退 `st_birthtime`，`date_source="file"`；有则 `"embedded"`
- [x] `tests/fakes/fake_probe.py`：返回固定 `VideoMetadata`

## 完成标准（DoD）
- [x] 单测：喂样例 ffprobe JSON（dict）→ 断言解析正确、时间回退逻辑（不跑真 ffprobe），17 tests pass
- [x] 集成测 `@pytest.mark.integration`：对 `testVideo/` 真实视频文件解析，断言字段非空（6 tests pass, 含错误路径测试）
