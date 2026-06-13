# 01 · Config 配置

> 密钥/端点读 `.env`，用户偏好读 JSON，合并成类型安全的 `AppConfig`。
> **依赖**：00。 **详见** detailed-design §3.1、§9。

## 子任务
- [ ] `EnvSettings`（pydantic-settings）读 `.env`：`OMLX_BASE_URL`、`OMLX_API_KEY`
- [ ] `Prefs`（pydantic）读写 `<库>/.cutfinder/config.json`：`source_folders`、`library_path`、`text_model`、`vision_model`、`whisper_model`、`extensions`(默认 `.mov .mp4 .m4v`)、`broll_frame_count`(3)、`vad_threshold`(0.15)
- [ ] `load_config() -> AppConfig`（合并 env + json，填默认值）
- [ ] `save_prefs(Prefs)`
- [ ] `.env` 缺失（无 OMLX_BASE_URL/API_KEY）时抛明确错误

## 完成标准（DoD）
- [ ] 单测：monkeypatch 注入环境变量 + 临时 JSON → 断言合并结果与默认值
- [ ] 单测：缺 `.env` 必填项时报错
- [ ] 单测：`save_prefs` → `load_config` 往返一致
