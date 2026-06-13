# 03 · Media 缩略图 / 抽帧

> 用 ffmpeg 生成代表帧缩略图，以及为 B-roll 均匀抽帧。
> **依赖**：00。 **接口**：`ports/media.py:ThumbnailMaker, FrameExtractor`。 **详见** detailed-design §3.3。

## 子任务
- [x] `adapters/ffmpeg_media.py:FfmpegThumbnailMaker.make(path, out_path)`：取偏中部一帧 → 写图片
- [x] `FfmpegFrameExtractor.extract(path, count)`：按时长均匀取 `count` 帧（默认 3）→ 图片路径列表
- [x] `tests/fakes/`：返回预置图片路径的假实现

## 完成标准（DoD）
- [x] 单测：mock subprocess，断言 ffmpeg 命令/时间点构造正确（19 tests, `test_ffmpeg_media.py`）
- [x] 集成测 `@integration`：对真实视频真抽帧，断言产出文件存在、数量=count、尺寸合理（7 tests, `test_integration_ffmpeg_media.py`）
