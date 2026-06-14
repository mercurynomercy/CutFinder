# 11 · Orchestrator 流水线编排（核心）

> 对单片段执行流水线，**只依赖接口**。是测试金字塔重点。
> **依赖**：02–09。 **位置**：`pipeline/orchestrator.py`。 **详见** detailed-design §3.11。

## 子任务
- [x] `process_clip(candidate)`：probe → thumbnail → VAD 判 A/B
  - [x] A 分支：transcribe → summarize(OMLX 文本)
  - [x] B 分支：extract 抽帧 → describe(OMLX 视觉)
  - [x] → `repository.upsert_clip`(+tags +transcript/description) → `library.copy_into`
- [x] 进度事件回调（供 worker/SSE）
- [x] 错误隔离：单步失败 → 该片段 `status=error` + 错误信息，**整批继续**
- [x] 幂等：开始前查指纹，已 `done` 跳过
- [x] `reanalyze(clip_id)`：强制重跑 AI；**不重复制**、保留 manual 的 A/B 与标签，只刷新 auto + summary/description/transcript

## 完成标准（DoD）—— 注入全部 fakes
- [x] 单测：A 分支调 transcribe+summarize、不调 vision；B 分支相反
- [x] 单测：错误注入 → 该片段标 error 且循环继续
- [x] 单测：已处理片段被幂等跳过
- [x] 单测：落库内容与复制目标正确
- [x] 单测：reanalyze 刷新 auto、保留 manual、**未调用 LibraryWriter**

## 测试覆盖（23 tests, all passing）
- **A/B branch assertions**: A-roll calls transcribe+summarize, B-roll calls extract+vision_tagger (4 tests)
- **Progress events**: A-roll and B-roll emit correct step sequence (probe, thumbnail, vad, analysis, persist) — 6 tests
- **Error isolation**: probe/vad/analysis failure marks clip status=error, batch continues — 4 tests
- **Idempotent skip**: pre-existing fingerprint returns existing ID, no upsert/library call — 3 tests
- **Database correctness**: upsert writes roll_type/summary/description/thumbnail, tags set correctly — 4 tests
- **Library copy**: copy_into called with correct date/roll_type, handles B-roll args — 2 tests
- **Reanalyze**: preserves manual roll + tags, refreshes auto fields, no library_writer call — 5 tests
