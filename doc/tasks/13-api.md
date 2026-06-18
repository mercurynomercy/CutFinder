# 13 · API 层（FastAPI）

> 薄路由层：校验、调用编排/仓储、序列化；含 SSE 进度流；装配真实适配器（DI）。
> **依赖**：09、11、12。 **位置**：`api/`。 **详见** detailed-design §6。

## 子任务
- [x] `api/app.py`：FastAPI 应用 + 依赖注入装配真实适配器
- [x] pydantic 请求/响应 schema
- [x] 路由：
  - [x] `POST /api/scan` → 入队、返回 `job_id`
  - [x] `GET /api/jobs/{id}`、`GET /api/jobs/{id}/events`（SSE）
  - [x] `GET /api/clips`（query：date/type/tag/q）、`GET /api/clips/{id}`
  - [x] `PATCH /api/clips/{id}`（纠正 roll/改 summary）
  - [x] `PUT /api/clips/{id}/tags`
  - [x] `POST /api/clips/{id}/reanalyze`
  - [x] `GET /api/search?q=`、`GET /api/clips/{id}/thumbnail`
  - [x] `GET /api/settings`、`PUT /api/settings`

## 完成标准（DoD）—— TestClient + 假仓储/假编排
- [x] 单测：各路由状态码与响应 schema（27/27 passing）
- [x] 单测：参数校验（非法输入 422）— JSON decode error, roll pattern, tag list validation
- [x] 单测：SSE 事件流可读到进度事件（`TestJobEventsEndpoint`）

## 完成记录
- **路由实现**: `api/routes.py` — `_build_router()` 封装所有端点，依赖注入通过参数传入
- **关键修复**: `Request` 必须模块级导入才能让 FastAPI DI 正确解析；`Query(regex=)` → `Query(pattern=)`
- **分析结果编辑**: 需携带 `roll_type`（AnalysisResult 必填字段）
- **JSON body 解析**: `_json.loads()` 需捕获 `JSONDecodeError` → 422
- **测试文件**: `tests/unit/test_api.py` — 覆盖全部端点、参数校验、边界情况
- **回归**: API 测试全通过；8 个其他文件失败为 pre-existing（orchestrator/fingerprint pattern、integration/real video）
