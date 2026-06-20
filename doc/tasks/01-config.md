# 01 · Config 配置

> OMLX 密钥/端点读全局存储（`~/.cutfinder/config.json`）或 OS env vars，用户偏好读 JSON，合并成类型安全的 `AppConfig`。
> **依赖**：00。 **详见** detailed-design §3.1、§9。

## 子任务
- [x] `EnvSettings`（pydantic-settings）读全局存储 / OS env：`OMLX_BASE_URL`、`OMLX_API_KEY`
- [x] `Prefs`（pydantic）读写 `<库>/.cutfinder/config.json`：`source_folders`、`library_path`、`text_model`、`vision_model`、`whisper_model`、`extensions`(默认 `.mov .mp4 .m4v`)、`broll_frame_count`(3)、`vad_threshold`(0.15)
- [x] `resolve_env() -> EnvSettings`（全局配置优先，OS env 覆盖）
- [x] `load_config() -> AppConfig`（合并全局配置/OS env + JSON，填默认值）
- [x] `save_prefs(Prefs)`
- [x] 全局配置缺失（无 OMLX_BASE_URL/API_KEY）时抛明确错误

## 完成标准（DoD）
- [x] 单测：monkeypatch OS env + 临时 JSON → 断言合并结果与默认值
- [x] 单测：缺必填项时报错（全局配置优先，OS env 覆盖）
- [x] 单测：`save_prefs` → `load_config` 往返一致
