# 15 · 环境 / 部署 / 集成测试

> 补全 Makefile 目标、真机集成测试与端到端，验证「换机一键可跑」。
> **依赖**：全部。 **详见** detailed-design §8、§10。

## 子任务
- [ ] Makefile 补全：`dev`、`models`、`check-omlx`、`test-integration`、`e2e`
- [ ] `check-omlx`：解析 OMLX `/v1/models` 校验所需文本/视觉模型是否就绪
- [ ] 集成测 fixtures 指向 `testVideo/`：A=`MVI_5298.MP4`，B=`MVI_5368.MP4`/`DJI_20260515175239_0097_D.MP4`
- [ ] 另补小样本：1 段无内嵌时间（验日期回退）、1 段非白名单扩展名（验跳过）
- [ ] Playwright e2e：扫描 → 缩略图 → 按类型/标签筛选 → 编辑标签/纠正 A/B → 搜索命中（后端用假适配器 + 预置 DB）

## 完成标准（DoD）
- [ ] 单测：`check-omlx` 解析逻辑（假 HTTP 响应）
- [ ] `make test-integration` 在本机（OMLX 开启）跑通
- [ ] `make e2e` 通过
- [ ] 按 README 流程在干净环境实测：`mise install && make setup` → `make check-omlx` → `make dev` 可用
