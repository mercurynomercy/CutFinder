# 14 · Frontend 前端（React）

> 缩略图墙 + 筛选/搜索 + 详情编辑 + 设置 + SSE 进度。只通过 `api/` 与后端通信。
> **依赖**：13。 **位置**：`frontend/src/`。 **详见** detailed-design §7。

## 子任务
- [ ] `api/`：唯一 HTTP 封装（REST + SSE 订阅）
- [ ] `features/gallery`：缩略图墙（分页/虚拟滚动、空态）
- [ ] `features/filters`：日期 / 类型 / 标签筛选
- [ ] `features/search`：全文搜索框 + 结果
- [ ] `features/detail`：简介、可编辑标签、改 A/B、**重新分析按钮**、转写全文
- [ ] `features/settings`：源/库文件夹、模型名等表单
- [ ] `features/jobs`：SSE 进度条、逐个完成提示

## 完成标准（DoD）—— Vitest + RTL + MSW
- [ ] 每个 feature 组件测试：mock API/SSE，断言渲染与交互
- [ ] detail：编辑触发 PATCH/PUT、重分析触发 POST reanalyze、乐观更新
- [ ] filters：断言触发正确请求参数
- [ ] jobs：mock SSE 事件流断言进度更新
