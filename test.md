# ASR 引擎选型测试记录

**目标**：为 CutFinder A-roll 找到一个本地、离线的中文/中英 ASR 方案，同时满足三个硬需求：
1. 稳定的中英文字幕（**带逐句时间戳**）
2. SRT + iTT 导出
3. A-roll 摘要 / 标签分析

**测试日期**：2026-06-21
**测试文件**：`/Users/jianhengpan/TEST/MVI_5394.MP4`（33.4s，含中文口语 + 中英混说 + 笑声）
**参考另一文件**：`/Users/jianhengpan/VlogFinal/2026-04-11.m4v`（前 90s，初步验证）

参考真值（人工大致）：「现在是在视频的，哈哈…我还以为拍照呢，太好笑了。我们现在再休息一会，听说是半个小时就到**光明顶**，但我现在觉得它远在天边…我们 like…一眨的距离…只有这么远，我马上就到啦！」

---

## 结论速览

| 引擎 | 运行方式 | 中文准确度 | 时间戳 | 速度(33s) |
|---|---|---|---|---|
| **Qwen3-ASR-1.7B** | OMLX `/audio/transcriptions` | 优（光明顶✓、带标点、语气词） | ❌ 无（整段一块） | ~1s |
| **mlx-whisper large-v3** | 本地独立进程 | 中（光明岭✗、无标点） | ✅ 逐句 17 段 | 3.3s |
| **Fun-ASR-Nano-2512** | mlx-audio-plus 本地 | 优（光明顶✓） | ❌ 无（源码写死 segments=None） | 3.1s |

**规律**：所有 "LLM-based" 生成式 ASR（Qwen3-ASR、Fun-ASR）本地都**只吐文本、不吐时间戳**；只有解码对齐式的 whisper 提供逐句时间戳。

**最终方案**：**混合** — whisper 当"对时器"出时间轴，Qwen3-ASR(OMLX) 出准确文本，字符对齐后合并 → 同时满足字幕(时间戳) + A-roll 文本分析。原型已验证（见 Test 5）。

---

## Test 1 — Qwen3-ASR via OMLX（`/v1/audio/transcriptions`）

端点：`POST http://localhost:1235/v1/audio/transcriptions`，`model=Qwen3-ASR-1.7B`

- `response_format=srt` → **被忽略**，仍返回 JSON，单段 `[0.0 - 33.37]`
- `response_format=verbose_json` + `timestamp_granularities[]=segment` → `segments: 1`
- `timestamp_granularities[]=word` → `words: 0`

**输出文本（质量优）**：
> 现在是在视频的，哈哈哈哈哈！我还以为拍照呢，太好笑了。我们现在再休息一会，听说是半个小时就到**光明顶**，但我现在觉得它远在天边。给大家看它到底在哪？不是近在眼前吗？在，在那里。我们 like 对啊，哦，一眨的距离。对，一眨眼就到了。没错，只有一眨的距离，只有这么远。我马上就到啦！哈哈哈哈哈。

**判定**：中文最准（光明顶✓、标点、语气词），但**无任何时间戳**（segment/word/srt 全试过）。`duration` 字段也不可信。

## Test 2 — mlx-whisper large-v3（本地，raw 音频，无人声分离）

通过项目 `MlxWhisperTranscriber(language="zh")`，耗时 3.3s，**17 段逐句时间戳**：

```
[  0.00 -   4.32] 现在是在视频呢
[  4.32 -   6.58] 我还以为拍照呢
[  6.58 -   7.94] 太好笑了是不是
[  7.94 -  10.16] 我们现在在休息一会
[ 10.16 -  13.64] 听说是半个小时就到光明岭   ← 错（应为 光明顶）
[ 13.64 -  15.96] 但我现在觉得它远在天边
[ 15.96 -  17.50] 给大家看它到底在哪
[ 17.50 -  19.82] 不是近在眼前吗
[ 19.82 -  21.20] 在那里
[ 21.20 -  23.10] like
... 共 17 段
```

**判定**：时间戳干净可靠✅；但中文略差（光明岭✗、无标点、个别多字）。

## Test 3 — 厂商文档核实（Qwen3-ASR 是否本应有时间戳）

阿里云实时识别文档明确：
- `qwen3-asr-flash-realtime` **does NOT currently return timestamps**
- 要时间戳须用 **Fun-ASR (`fun-asr-realtime`)** 或 **Paraformer (`paraformer-realtime-8k-v2`)**

→ 即 **Qwen3-ASR 无时间戳是模型/服务本身特性，不是 OMLX 的问题**（本地 OMLX 行为与阿里云一致）。

## Test 4 — Fun-ASR-Nano-2512-fp16 via mlx-audio-plus（本地）

HF：`mlx-community/Fun-ASR-Nano-2512-fp16`（1.97GB），运行器 `mlx_audio.stt.models.funasr`（**不走 OMLX**）。
load 57.8s（一次性）+ generate 3.1s。

**输出**（中文优，但带 `[breath]`/`/sil` 噪声 token）：
> [breath]现在是在视频的[breath]哈哈哈哦我还以为拍照呢[breath]太好笑了是不是[breath]我们现在在休息一会儿[breath]听说是半个小时就到**光明顶**但我现在觉得它远在天边…[breath] like /sil like /sil对啊…只有这么远，[breath]我马上就到啦[breath]

**`.segments = None`** — 无时间戳。源码注释直接说明：
```python
segments=None,  # LLM-based model doesn't produce word-level timestamps
```
`generate()` 签名无任何 timestamp/segment 参数。

**判定**：虽然 Fun-ASR 家族在云端有时间戳，但这个 **LLM 版 mlx 移植设计上就不产时间戳**。中文质量与 Qwen3-ASR 相当，但多了 `[breath]`/`/sil` 需清洗，且需新依赖 mlx-audio-plus。无增量价值。

## Test 5 — 混合方案原型（whisper 时间 + Qwen3-ASR 文本，字符对齐）✅

做法：whisper 给逐句时间段 → Qwen3-ASR 给准确全文 → `difflib.SequenceMatcher` 字符级把 Qwen3 文本铺到 whisper 各时间段。生成 SRT：

```
1   00:00:00,000 --> 00:00:04,320   现在是在视频的，哈哈哈哈哈！
2   00:00:04,320 --> 00:00:06,580   我还以为拍照呢，
3   00:00:06,580 --> 00:00:07,940   太好笑了。
4   00:00:07,940 --> 00:00:10,160   我们现在再休息一会，
5   00:00:10,160 --> 00:00:13,640   听说是半个小时就到光明顶，   ← 准 + 有时间戳
6   00:00:13,640 --> 00:00:15,960   但我现在觉得它远在天边。
...
17  00:00:29,880 --> 00:00:33,340   只有这么远。我马上就到啦！哈哈哈哈哈。
```

**判定**：同时拿到 whisper 的精确时间轴 + Qwen3 的准确文本。仅个别段在标点处断句有小瑕疵（可用"标点吸附"优化）。**满足全部三个硬需求。**

---

## 推荐架构（A-roll 路径）

```
A-roll → Demucs 人声分离(可选)
       ├─ mlx-whisper      → 逐句时间轴（只取时间）
       └─ Qwen3-ASR(OMLX)  → 准确中文/中英文本
       → 字符对齐：Qwen3 文本铺到 whisper 时间段
       → Transcript(segments)
          ├─ ① subtitle_exporter → SRT / iTT
          └─ ② 全文 → Qwen3.6 → 摘要 + 标签
```

代价：每个 A-roll 两遍 ASR（都快）。whisper 留作"对时器"，不再当文本引擎。

---

## ⚠️ 依赖副作用（待处理）

为测 Fun-ASR 执行了 `uv pip install mlx-audio-plus`，引入 transformers 等大量包，并**降级**了项目原有依赖：
- `starlette` 1.3.1 → 0.52.1
- `websockets` 16.0 → 15.0.1

若不采用 Fun-ASR，应回滚（`uv sync` 还原 lock 版本），以免影响 FastAPI app。
