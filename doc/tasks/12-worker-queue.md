# 12 · Worker 队列 + SSE

> 后台单 worker 顺序处理，进度通过 SSE 推送；job 状态持久化。
> **依赖**：09、11。 **位置**：`pipeline/worker.py`。 **详见** detailed-design §3.12。

## 子任务
- [x] `asyncio.Queue` + 后台 task，单 worker 顺序处理（尊重模型显存）
- [x] `enqueue_scan(...)` / `enqueue_reanalyze(clip_id)` 入队
- [x] 进度事件广播机制（供 SSE 多连接订阅）
- [x] Job 状态持久化（total/done/failed），刷新可恢复
- [x] 单片段失败不影响队列后续

## 完成标准（DoD）—— 注入假编排器
- [x] 单测：队列顺序处理
- [x] 单测：进度事件序列正确（start/done/error）
- [x] 单测：job 状态推进（total/done/failed）持久化

## 测试覆盖（20 tests, all passing）
- **Sequential processing**: single clip processed once; multiple clips in enqueue order (3 tests)
- **Progress event sequences**: scan emits job_started → clip_started/clip_done × N; reanalyze emits job_started → reanalyze_started/reanalyze_done (5 tests)
- **Error events**: clip_error on orchestrator exception; reanalyze_error when returns False (2 tests)
- **Job state persistence**: total set on enqueue, done increments per clip, failed increments on error (6 tests)
- **Error isolation**: batch continues after single clip failure; all failed clips marked done (2 tests)
- **Edge cases**: empty candidates list, multiple start() idempotency, stop before start, drain on shutdown (4 tests)
