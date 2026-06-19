# 18 Whisper 转写前置人声分离（去 BGM）

> 依据：设计 spec [`docs/superpowers/specs/2026-06-19-vocal-separation-before-whisper-design.md`](../../docs/superpowers/specs/2026-06-19-vocal-separation-before-whisper-design.md)、[`detailed-design.md`](../detailed-design.md) §3.5 / §3.13 / §3.14 / §9、[`proposal.md`](../proposal.md) §3 / §6。
> 现状问题：`MlxWhisperTranscriber` 用 ffmpeg 抽 PCM 直接喂 whisper，中间无降噪/分离；后期混入的 BGM 被一并转成文字或诱发幻觉，transcript 不准。

## 目标

在 whisper 转写前增加**本地人声分离**（Demucs 抽干声、扔伴奏），提升 transcript 准确度。

- **字幕导出（task 17，成片）**：**强制**先分离再转写，无开关。
- **A-roll 入库流水线（原始素材）**：UI Settings 开关 `vocal_separation`，**默认关闭**；开启后**之后** scan 的新 A-roll 先分离再转写。幂等重扫语义不变（只处理新文件，不回头重转已入库片）。

### 已确认决策（来自用户）

| 维度 | 决策 |
|---|---|
| 方案 | **Demucs** 取 `vocals` 干声（唯一真正去音乐的本地方案；`torch` 已是依赖） |
| 模型 | 固定 `htdemucs`（约 80MB），不暴露选型 |
| 字幕导出 | **强制**分离 |
| A-roll 流水线 | 开关默认 **False** |
| 分离失败 | **记日志 + 回落原始音频**（转写不中断，仅退化为未去 BGM），不报错 |
| Whisper 调参 | 两条路径都加防幻觉 kwargs（落地时验证 mlx-whisper 支持） |

### 硬约束（继承 proposal）

- **全本地离线**：分离走本地 Demucs（torch/MPS），不联网；模型一次性预下载。
- **源视频只读**：分离只在内存对抽取出的音频做处理，绝不碰源文件。

---

## 设计要点

- **新增 port** `VocalSeparator`（`ports/speech.py`）：`isolate(path) -> np.ndarray`（whisper 就绪的 16k 单声道 float32 干声）。
- **新增 adapter** `adapters/demucs_separator.py` → `DemucsSeparator`：ffmpeg 抽 44.1k 立体声 f32 → `demucs.api.Separator("htdemucs", device=mps|cpu)` 取 `vocals` → 下混单声道 + 重采样 16k → `np.float32`。模型懒加载并缓存到实例；device 自动选 MPS 回落 CPU；异常抛出由调用方处理。
- **改 `MlxWhisperTranscriber`**：构造加 `separator: VocalSeparator | None=None`；`transcribe()` 里有 separator 则 `try: audio = separator.isolate(path)`，失败记日志回落现有 16k 抽取；否则走现有路径。两条路径都补 whisper 防幻觉 kwargs。**`Transcriber.transcribe()` 端口签名不变**——分离决策在构造时确定。
- **接线**（`api/app.py`，开关落点）：构造**一个**共享 `DemucsSeparator()`（懒加载，模型只载一次）；subtitle exporter 的 transcriber **恒传** separator；orchestrator 的 transcriber **仅当 `prefs.vocal_separation` 为真才传**，否则 `None`。
- **配置**：`Prefs` 加 `vocal_separation: bool = False`。
- **依赖/工具**：`pyproject` 加 `demucs`（带入 torchaudio）；新增 `scripts/download_demucs.py` + 扩展 `make models` 预拉 `htdemucs`（一次性 ~80MB，之后离线）。

---

## 任务清单

### 后端

- [ ] `ports/speech.py`：新增 `VocalSeparator` Protocol（`isolate(path) -> np.ndarray`）；导出到 `ports/__init__.py`。
- [ ] `adapters/demucs_separator.py`：`DemucsSeparator` —— ffmpeg 44.1k 立体声抽取、demucs `htdemucs` 取 vocals、下混+重采样 16k、懒加载+device 选择、失败抛异常。
- [ ] `adapters/mlx_whisper.py`：`MlxWhisperTranscriber.__init__` 加 `separator`；`transcribe()` 接入分离（失败回落）+ whisper 防幻觉 kwargs。
- [ ] `config.py`：`Prefs` 加 `vocal_separation: bool = False`。
- [ ] `api/app.py`：构造共享 `DemucsSeparator`；subtitle exporter 恒传、orchestrator 按 `prefs.vocal_separation` 传/不传。
- [ ] `api/schemas.py` + settings 路由：`vocal_separation` 纳入设置读写（沿用现有 prefs 保存）。
- [ ] `pyproject.toml`：加 `demucs`；`scripts/download_demucs.py`；`Makefile` `models` 目标加预拉 Demucs。

### 前端

- [ ] `features/settings`：扫描区加开关「A-roll 转写前分离人声（去 BGM，较慢）」，默认关；说明仅影响之后 scan 的新片。
- [ ] `api/client.ts` + 类型：settings 读写带上 `vocal_separation`。
- [ ] `i18n`：EN/ZH 文案。

### 测试

- [ ] `DemucsSeparator`：集成测试（真模型，`@pytest.mark.integration`）—— 含 BGM 样本 → 断言产出 16k 单声道、长度合理的干声。
- [ ] `MlxWhisperTranscriber`：单测用**假 separator** + mock `mlx_whisper` —— 断言有 separator 时其输出进 whisper；separator 抛异常时回落原始音频、转写仍成功。
- [ ] `config`：`vocal_separation` 默认 `False`、可往返。
- [ ] 前端：Settings 开关渲染/切换/保存测试。

---

## 完成标准

1. 字幕导出（task 17）**强制**先分离再转写；对含 BGM 的成片，transcript 明显更干净。
2. A-roll 流水线默认**不**分离；Settings 打开开关后，**之后** scan 的新 A-roll 先分离再转写。
3. Demucs 失败回落原始音频、转写不中断（日志可见）。
4. 全程离线（模型已预下载）；源视频未被修改。
5. `mypy` / `ruff` / `tsc` 干净；新增单测全绿；集成测试在真机/真模型下通过。
6. （手动）对一段真实含 BGM 的样本，对比开启前后 transcript，确认音乐被去除、人声转写正确。
