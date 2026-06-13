# 12 · Worker 队列 + SSE

> 后台单 worker 顺序处理，进度通过 SSE 推送；job 状态持久化。
> **依赖**：09、11。 **位置**：`pipeline/worker.py`。 **详见** detailed-design §3.12。

## 子任务
- [ ] `asyncio.Queue` + 后台 task，单 worker 顺序处理（尊重模型显存）
- [ ] `enqueue_scan(...)` / `enqueue_reanalyze(clip_id)` 入队
- [ ] 进度事件广播机制（供 SSE 多连接订阅）
- [ ] Job 状态持久化（total/done/failed），刷新可恢复
- [ ] 单片段失败不影响队列后续

## 完成标准（DoD）—— 注入假编排器
- [ ] 单测：队列顺序处理
- [ ] 单测：进度事件序列正确（start/done/error）
- [ ] 单测：job 状态推进（total/done/failed）持久化
