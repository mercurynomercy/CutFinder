# 23 · 照片（静态图片）分析入库

> 来源：用户。诉求：Vlog 素材里除了视频还有大量**照片**，希望 CutFinder 也能识别/打标/归档照片，而不只是视频片段。
> 依据：[`07-vision-tagger.md`](./07-vision-tagger.md)、[`02-metadata-probe.md`](./02-metadata-probe.md)、[`08-library-writer.md`](./08-library-writer.md)、[`detailed-design.md`](../detailed-design.md)。

## 目标

把静态照片纳入扫描/分类/归档/检索全流程：自动出**视觉标签 + 中文描述**、缩略图，按拍摄日期归档副本，可在画廊检索。复用既有 B-roll 视觉链路（Qwen3-VL via OMLX）。

## 复用 vs 新增

- **复用**：视觉打标走 `Qwen3-VL-8B-Instruct`（OMLX，base64，标准 OpenAI vision 格式），同 B-roll；归档=按日期建副本；缩略图同款。
- **差异点（照片 vs 视频）**：
  - 无音轨 → **跳过** VAD / whisper / A-B 判定；照片天然归「图片」类（B-roll 之外的新类型，或并入 B-roll，需定）。
  - 帧抽取无意义 → 直接把图片本身（缩放后）喂给视觉模型，无需 ffmpeg keyframe。
  - 拍摄时间：照片走 **EXIF**（非 QuickTime），元数据探针需支持读图片 EXIF 时间；缺失则回退文件创建时间并在 UI 标注（同既有约束）。
  - 关键帧推荐对照片不适用 → 跳过。

## 待办

- [x] 决定**归档分类**：新增 `Photo` 类，还是并入 `B-roll`？库目录形如 `<库>/YYYY-MM-DD/Photo/`（建议独立类，避免和视频混淆）。
- [x] 扫描器：图片扩展名白名单（`.jpg/.jpeg/.png/.heic/...`；HEIC 需确认解码路径）；与视频共用 dedup 指纹。
- [x] 元数据探针：读图片 EXIF 拍摄时间 + 分辨率；时间缺失回退 + UI 标记。
- [x] 缩略图：从图片生成缩略图（无需抽帧）。
- [x] 编排：图片分支 → 直接视觉打标（描述+标签）→ 入库 → 归档副本（源只读）。
- [x] 仓储/检索：图片与视频在同一 catalog，画廊/筛选/搜索可按类型过滤。
- [x] API/前端：画廊展示图片卡片；详情面板适配（无 transcript / 无切点）；类型筛选加「照片」。
- [x] i18n EN/ZH。

## 完成标准

1. 扫描含照片的文件夹 → 照片被识别、出中文描述 + 标签 + 缩略图、按拍摄日期归档副本。
2. 源照片只读、拍摄时间不被改写；EXIF 时间优先、缺失回退并在 UI 标注。
3. 照片可在画廊检索/筛选；详情面板无音频/切点字段时优雅降级。
4. 重扫幂等不重复入库；单测覆盖照片分支（探针/编排/归档/检索）；`mypy`/`ruff`/`tsc` 干净。

## 开放问题

- 照片单独成 `Photo` 类，还是归入 `B-roll`？（建议独立类。）
- HEIC/RAW 是否要支持？（HEIC 在 vlog 里常见，优先；RAW 可后置。）
- 大相册量级下，视觉打标的吞吐/排队策略是否要单独考量？

---

## 已实现（最终决策）

- **分类**：独立 `photo` roll 类型（`RollType.PHOTO`）。归档到 `<库>/<date>/photos/photo-0001.<ext>`（小写 `photos` 目录、`photo-NNNN` 前缀；源只读、`shutil.copy2` 保留时间）。
- **格式**：`.jpg/.jpeg/.png/.heic`（`Prefs.photo_extensions`）；HEIC 经 `pillow-heif`。
- **管线**：`Orchestrator._process_photo` —— `PillowImageProbe`（EXIF 拍摄时间，缺失回落文件时间并标 `date_source=file`）→ `PillowThumbnailMaker` JPEG 预览（兼作缩略图与视觉输入，HEIC 解码）→ `Qwen3-VL` 描述+标签 → 归档 → 入库。**无 VAD/转写**。
- **照片无关键帧、无重分析**（按用户明确要求）：`clip_ids_without_keyframes()` 排除 photo；`POST /clips/{id}/keyframes` 与 `/reanalyze` 对 photo 返回 400；前端详情面板对 photo 隐藏 A/B 切换、关键帧区、重分析按钮，画廊不显示重分析按钮。
- **扫描**：scan 路由合并 `extensions + photo_extensions`。
- **依赖**：`pillow`、`pillow-heif`（已加入 `pyproject.toml`，已真机验证 EXIF/HEIC/预览）。
- **测试**：`test_orchestrator_photo.py`（3）、`test_pillow_image.py`（3）、`test_fs_library.py` 照片命名（1）；前端 `roll_type` 类型放宽 + 照片筛选项 + 详情降级。
