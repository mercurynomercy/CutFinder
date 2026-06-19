# 19 字幕导出进度条与后端转写进度同步（分离 + 转写两阶段）

> 依据：[`detailed-design.md`](../detailed-design.md) §3.13 / §3.14、[`ui-design.md`](../ui-design.md) §6、task 17/18。
> 现状问题：字幕导出 job 用 `create_job(total=1)`，UI 进度条只有 0%→100% 一跳；而 mlx-whisper / Demucs 的真实进度（逐帧 `X/116191 frames`）只打在后端 stderr 的 tqdm 里，没引到前端。

## 目标

让 task 17 字幕导出的 **UI 进度条与后端真实转写进度同步**，覆盖 **Demucs 分离 + Whisper 转写两阶段**，像后端日志里那个逐帧进度条一样平滑推进。

### 已确认决策（来自用户）

| 维度 | 决策 |
|---|---|
| 应用范围 | **仅 task 17 字幕导出**（A-roll 入库不做逐帧子进度） |
| 覆盖阶段 | **分离 + 转写两阶段**（分离 [0, W]，转写 [W, 1]） |
| 进度来源 | 拦截 Demucs(`apply_model(progress=True)`) 与 mlx-whisper 各自内部的 **tqdm**（两者都无回调参数） |

### 硬约束

- 不改转写/分离逻辑、不影响输出质量；进度纯旁路。
- `worker_concurrency=1`（顺序处理），故全局 tqdm monkeypatch 在单次调用内安全（`finally` 还原）。

---

## 设计要点

### 进度引出：tqdm 拦截（两阶段同一机制）

- mlx-whisper `transcribe.py`：模块级 `import tqdm`，用 `tqdm.tqdm(total=content_frames)`。
- demucs `apply.py`：模块级 `import tqdm`，`progress=True` 时 `tqdm.tqdm(futures, ...)`。
- 新增 util（如 `adapters/_progress.py`）：上下文管理器 `patch_tqdm(module, on_fraction)` —— 把目标模块的 `tqdm` 属性临时换成一个 shim，其 `.tqdm(...)` 返回真实 tqdm 的薄子类，在 `update()` / 迭代时调用 `on_fraction(n/total)`；`finally` 还原。依赖标准 tqdm 的 `.n`/`.total`（稳定 API）。

### 两阶段加权放在 transcriber 内部（关键）

分离发生在 `MlxWhisperTranscriber.transcribe()` 内部（separator 注入在 transcriber 里），故由它统一对外暴露**单一 0..1**：

```python
def transcribe(self, path, *, language=None, progress: Callable[[float], None] | None = None):
    if self._separator is not None:
        # 分离阶段 → 整体 [0, W]
        audio = self._separator.isolate(path, progress=lambda f: progress and progress(f * W))
        # 转写阶段 → 整体 [W, 1]（patch_tqdm 包住 mlx_whisper.transcribe 调用）
    else:
        # 仅转写 → [0, 1]
```

- 端口扩展（向后兼容，默认 `None`）：
  - `VocalSeparator.isolate(path, *, progress=None)`（DemucsSeparator 用 `apply_model(progress=True)` + `patch_tqdm`）。
  - `Transcriber.transcribe(path, *, language=None, progress=None)`。
- `W`（分离权重，常量，约 `0.4`）放 mlx_whisper 适配器；A-roll 流水线调用不传 `progress`（行为不变）。

### Worker / SSE

- `enqueue_subtitle`：job 改 `create_job(total=100)`（百分比刻度），`job_started` 同步 total=100。
- `_process_subtitle`：把 `on_progress(frac)` 传给 `SubtitleExporter.export(..., on_progress=...)` → 透传给 `transcribe(progress=...)`。
- 节流：tqdm 每秒触发数千次，限制为**每 ≥1% 或每 ~300ms** 才 `update_job(done=int(frac*100))` + `_emit` 一次 `job_progress` SSE，避免刷爆 DB/SSE。

### 前端（subtitles 页）

- `waitForJob`/轮询读 `job.done`/`job.total` → 百分比；渲染**真实进度条**（替换/补充现有不定量「处理中」+ elapsed 计时器）。
- 阶段标签：按权重阈值 `W` 推断「分离中… / 转写中…」（前端镜像常量），保留 elapsed 计时器。

---

## 任务清单

### 后端

- [x] `adapters/_progress.py`：`patch_tqdm(module, on_fraction)` 上下文管理器（薄 tqdm 子类，update/迭代上报 `n/total`，finally 还原）。
- [x] `ports/speech.py`：`VocalSeparator.isolate` 与 `Transcriber.transcribe` 各加可选 `progress: Callable[[float], None] | None = None`。
- [x] `adapters/demucs_separator.py`：`isolate(progress=...)` —— `apply_model(progress=True)` 外套 `patch_tqdm`，上报分离 0..1。**真库验证拦截生效**。
- [x] `adapters/mlx_whisper.py`：`transcribe(progress=...)` —— 有 separator 时分离[0,W]+转写[W,1] 合成单一进度；whisper 调用外套 `patch_tqdm`。常量 `W=0.4`。**真库验证（含子模块遮蔽坑）生效**。
- [x] `pipeline/subtitle_exporter.py`：`export(..., on_progress=None)` 透传给 `transcribe(progress=...)`。
- [x] `pipeline/worker.py`：subtitle job `total=100`；`_process_subtitle` 注入节流后的 `on_progress` → `update_job(done=...)` + `job_progress` SSE。

### 前端

- [x] `features/subtitles`：轮询读 `done/total`，渲染真实进度条 + 阶段标签（按 `W` 阈值），保留 elapsed。
- [x] `i18n`：阶段文案（分离中 / 转写中）EN/ZH。

### 测试

- [x] `patch_tqdm`：单测用假 tqdm 驱动 update/迭代，断言 `on_fraction` 收到正确 0..1 且结束后模块属性已还原。
- [x] `MlxWhisperTranscriber`：单测断言两阶段加权（分离段映射 [0,W]、转写段映射 [W,1]）经 mock 透传到 `progress`。
- [x] `SubtitleExporter` / worker：断言 `on_progress` 透传、job `total=100`、节流后 `update_job`/SSE 被调用。
- [x] 前端：进度条按 `done/total` 渲染、阶段标签随阈值切换的组件测试。

---

## 完成标准

1. 字幕导出时 UI 进度条**平滑推进**，与后端 tqdm 实际进度同步（不再 0→100 一跳）。
2. 进度覆盖两阶段：先「分离中」推进至 ~W，再「转写中」推进至 100%。
3. 不改转写/分离结果；A-roll 入库行为不变（不传 progress）。
4. SSE/DB 不被高频刷爆（节流生效）。
5. `mypy` / `ruff` / `tsc` 干净；新增单测全绿。
6. （手动）真机导出一段成片，肉眼确认进度条与终端 tqdm 同步推进。
