# 29 · 设置统一到 config.json，去掉 "env" 分组（清理）

> **状态：planned（待执行）。** machine-global 设置（OMLX 端点/密钥、文本/视觉模型名）实际都存在
> `~/.cutfinder/config.json`，已经**没有 OS 环境变量**。但 settings API / 前端仍把这些项分组在一个历史命名的
> `"env"` 键下传递，概念上有歧义。本任务把 "env" 这个分组从 API/UI 去掉，统一成"全在 config.json/prefs"。
>
> **位置**：后端 `api/settings_routes.py`、`config.py`（EnvSettings/`_GLOBAL_KEYS` 命名）；
> 前端 `features/settings/index.tsx`、`api/client.ts`、`test/mocks/handlers.ts`。

---

## 现状

- 存储：`OMLX_BASE_URL` / `OMLX_API_KEY` / `TEXT_MODEL` / `VISION_MODEL`（`config.py` 的 `_GLOBAL_KEYS`）都写在
  `~/.cutfinder/config.json` 顶层；不再读 OS 环境变量。
- 但 `GET /api/settings` 仍返回 `{"env": {OMLX_BASE_URL, OMLX_API_KEY(masked), TEXT_MODEL, VISION_MODEL}, "prefs": {...}}`
  （`settings_routes.py:55-62`），前端 `settings/index.tsx` 读 `data.env.TEXT_MODEL` 等 4 处（`:166-169`）。
- 即 "env" 现在只是个**历史命名的分组标签**，数据源已是 config.json。

## 目标

把 "env" 概念从对外接口/前端去掉，让 machine-global 项和库级 prefs 一样，统一在一个 config 视图里读写——
减少"env vs prefs"的认知负担，避免 mock/测试再因这个分组踩坑（参见本次 settings mock 修复：必须把模型名放进 `env` 才对齐后端）。

**待定的形态**（执行前定）：
- 方案 A：`GET /api/settings` 直接返回扁平的 `config`（machine-global + prefs 合并），密钥仍 mask；前端读 `data.config.TEXT_MODEL`。
- 方案 B：保留 `prefs`，把 machine-global 项也并进 `prefs` 一起返回；删掉 `env` 键。
- 命名：`config.py` 里 `EnvSettings` / `_GLOBAL_KEYS` / `OMLX_*` 是否一并改名（影响面较大，可只改对外 API、内部命名留作后续）。

## 工作分解（执行时细化）

1. 后端 `get_settings` 去掉 `env` 分组，按选定方案返回；`update_settings` 的 `_GLOBAL_KEYS` 写入路径不变（仍落 config.json）。
2. 前端 `settings/index.tsx` 4 处 `data.env.*` 改为新结构；`api/client.ts` 的 settings 响应类型同步。
3. `test/mocks/handlers.ts` 的 `GET /api/settings` mock 同步（不再需要单独的 `env`）。
4. 后端 `test_app_factory` 等断言 settings 契约的测试同步。

## 验收
- [x] 设置页模型名/OMLX 端点正常显示与保存（落 config.json）。采用**方案 B**：machine-global 键并进 `prefs`，删 `env` 分组。
- [x] 前后端测试绿（后端 526、前端 205）；mypy / ruff 干净；tsc 仅余 tsconfig `baseUrl` 历史告警。

## 备注
- 纯清理，无功能变化；与初剪（26/27/28）无关。
- 本次已先修好相关脆测试：gallery 用 `getByTitle` 精确查 clip；settings mock 暂按现状把模型名放进 `env`（本任务落地后这段 mock 会随之改掉）。
