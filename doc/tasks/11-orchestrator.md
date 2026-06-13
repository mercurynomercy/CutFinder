# 11 · Orchestrator 流水线编排（核心）

> 对单片段执行流水线，**只依赖接口**。是测试金字塔重点。
> **依赖**：02–09。 **位置**：`pipeline/orchestrator.py`。 **详见** detailed-design §3.11。

## 子任务
- [ ] `process_clip(candidate)`：probe → thumbnail → VAD 判 A/B
  - [ ] A 分支：transcribe → summarize(OMLX 文本)
  - [ ] B 分支：extract 抽帧 → describe(OMLX 视觉)
  - [ ] → `repository.upsert_clip`(+tags +transcript/description) → `library.copy_into`
- [ ] 进度事件回调（供 worker/SSE）
- [ ] 错误隔离：单步失败 → 该片段 `status=error` + 错误信息，**整批继续**
- [ ] 幂等：开始前查指纹，已 `done` 跳过
- [ ] `reanalyze(clip_id)`：强制重跑 AI；**不重复制**、保留 manual 的 A/B 与标签，只刷新 auto + summary/description/transcript

## 完成标准（DoD）—— 注入全部 fakes
- [ ] 单测：A 分支调 transcribe+summarize、不调 vision；B 分支相反
- [ ] 单测：错误注入 → 该片段标 error 且循环继续
- [ ] 单测：已处理片段被幂等跳过
- [ ] 单测：落库内容与复制目标正确
- [ ] 单测：reanalyze 刷新 auto、保留 manual、**未调用 LibraryWriter**
