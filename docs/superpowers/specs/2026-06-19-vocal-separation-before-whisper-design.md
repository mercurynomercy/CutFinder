# 设计：Whisper 转写前置人声分离（去 BGM）

> 日期：2026-06-19 ｜ 状态：已确认设计，待写实现计划
> 背景：当前 `MlxWhisperTranscriber` 用 ffmpeg 抽 PCM 直接喂 whisper，中间无降噪/分离，
> 后期混入的背景音乐（BGM）会被 whisper 一并"转"成文字或诱发幻觉，transcript 不准。

## 目标

在 whisper 转写前增加**本地人声分离**步骤，抽出干声、扔掉伴奏，提升 transcript 准确度。

- **Task 17 字幕导出（成片）**：**强制**先分离再转写（成片通常混了 BGM），无开关。
- **A-roll 入库流水线（原始素材）**：UI Settings 提供开关，**默认关闭**；开启后，**之后** scan 的
  新 A-roll 会先分离再转写。重扫幂等语义不变（只处理新文件，不回头重转已入库片）。

## 硬约束（继承 proposal）

- **全本地离线**：分离走本地 Demucs（torch/MPS），不联网。模型一次性预下载。
- **源视频只读**：分离只在内存对抽取出的音频做处理，绝不修改/重命名源文件。

## 已确认决策

| 维度 | 决策 |
|---|---|
| 分离方案 | **Demucs**，取 `vocals` 干声（唯一真正"去音乐"的本地方案；torch 已是依赖） |
| 模型 | 固定 `htdemucs`（Hybrid Transformer Demucs v4，约 80MB，质量/速度最均衡），不暴露选型 |
| 字幕导出 | **强制**分离 |
| A-roll 流水线 | 开关 `vocal_separation`，**默认 False** |
| 分离失败 | **记日志 + 回落原始音频**（保证转写不中断，仅退化为未去 BGM），不报错 |
| Whisper 调参 | 两条路径都加防幻觉 kwargs（零成本，落地时验证 mlx-whisper 支持） |

## 架构（沿用现有 ports/adapters 模式）

### 新增 port — `ports/speech.py`

```python
class VocalSeparator(Protocol):
    def isolate(self, path: Path) -> np.ndarray:
        """返回 whisper 就绪的 16k 单声道 float32 干声（已去伴奏）。"""
```

### 新增 adapter — `adapters/demucs_separator.py` → `DemucsSeparator`

1. ffmpeg 抽 **44.1kHz 立体声 f32**（Demucs 原生采样率——不能用 16k，否则分离质量退化）。
2. `demucs.api.Separator(model="htdemucs", device=<mps|cpu>)` → 分离，取 `separated["vocals"]`。
3. 下混单声道 + 重采样到 **16kHz** → 返回 `np.float32`（与现有 whisper 输入格式一致，drop-in）。
4. 模型**懒加载**并缓存到实例；device 自动选 MPS，回落 CPU。
5. 任意环节异常 → 抛出，由调用方（transcriber）捕获并回落原始音频。

### 改 `adapters/mlx_whisper.py` — `MlxWhisperTranscriber`

- 构造新增 `separator: VocalSeparator | None = None`。
- `transcribe()`：
  - 若 `separator` 不为 `None`：`try: audio = separator.isolate(path)` —— 失败则记日志并回落现有 16k 抽取路径。
  - 否则：走现有 16k 抽取路径（行为不变）。
- 两条路径都补 whisper 防幻觉 kwargs（如 `condition_on_previous_text=False` 等；以 mlx-whisper 实际支持为准）。
- **`Transcriber.transcribe()` 端口签名不变**——分离决策在构造时确定，不污染共享端口。

### 接线 — `api/app.py`（开关落点）

- 构造**一个**共享 `DemucsSeparator()`（懒加载，模型只载一次）。
- **Subtitle exporter 的 transcriber：恒传 separator**（task 17 强制）。
- **Orchestrator 的 transcriber：仅当 `prefs.vocal_separation` 为真才传**，否则 `None`。

### 配置 — `config.py`

- `Prefs` 新增 `vocal_separation: bool = False`。

### 前端 — Settings

- 新增开关「A-roll 转写前分离人声（去 BGM，较慢）」，默认关；走现有 prefs 保存机制。
- i18n EN/ZH 文案。
- 说明文案点明：仅影响**之后** scan 的新片。

### 依赖 + 工具

- `backend/pyproject.toml` 新增 `demucs`（带入 torchaudio）。
- 新增 `scripts/download_demucs.py`：联网预拉 `htdemucs`（一次性，~80MB），之后全程离线。
  与现有 `scripts/download_whisper.py` 同套路。

## 测试

- `DemucsSeparator`：集成测试（真模型，marker 同 `test_integration_mlx_whisper`）——
  对一段含 BGM 的样本断言能产出 16k 单声道、长度合理的干声。
- `MlxWhisperTranscriber`：单测用**假 separator** + mock `mlx_whisper`，断言：
  - 有 separator 时 `isolate()` 的输出进入 whisper；
  - separator 抛异常时回落到原始音频抽取、转写仍成功。
- `config`：`vocal_separation` 默认 `False`、可往返。
- 前端：Settings 开关渲染/切换/保存测试。

## 完成标准

1. 字幕导出（task 17）**强制**先分离再转写；对含 BGM 的成片，transcript 明显更干净。
2. A-roll 流水线默认**不**分离；在 Settings 打开开关后，**之后** scan 的新 A-roll 先分离再转写。
3. Demucs 失败时回落原始音频、转写不中断（日志可见）。
4. 全程离线（模型已预下载）；源视频未被修改。
5. `mypy` / `ruff` / `tsc` 干净；新增单测全绿；集成测试在真机/真模型下通过。
