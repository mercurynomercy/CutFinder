# 13 · API 层（FastAPI）

> 薄路由层：校验、调用编排/仓储、序列化；含 SSE 进度流；装配真实适配器（DI）。
> **依赖**：09、11、12。 **位置**：`api/`。 **详见** detailed-design §6。

## 子任务
- [ ] `api/app.py`：FastAPI 应用 + 依赖注入装配真实适配器
- [ ] pydantic 请求/响应 schema
- [ ] 路由：
  - [ ] `POST /api/scan` → 入队、返回 `job_id`
  - [ ] `GET /api/jobs/{id}`、`GET /api/jobs/{id}/events`（SSE）
  - [ ] `GET /api/clips`（query：date/type/tag/q）、`GET /api/clips/{id}`
  - [ ] `PATCH /api/clips/{id}`（纠正 roll/改 summary）
  - [ ] `PUT /api/clips/{id}/tags`
  - [ ] `POST /api/clips/{id}/reanalyze`
  - [ ] `GET /api/search?q=`、`GET /api/clips/{id}/thumbnail`
  - [ ] `GET /api/settings`、`PUT /api/settings`

## 完成标准（DoD）—— TestClient + 假仓储/假编排
- [ ] 单测：各路由状态码与响应 schema
- [ ] 单测：参数校验（非法输入 422）
- [ ] 单测：SSE 事件流可读到进度事件
