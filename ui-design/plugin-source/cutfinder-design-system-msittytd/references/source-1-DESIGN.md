# CutFinder Design System

> AI 驱动的短视频素材管理与初剪工具 — 完整 UI 页面清单与设计规范

---

## Pages

| # | Page | File | Route | Description |
|---|------|------|-------|-------------|
| 0 | **Launcher** | `index.html` | `/` | 启动页 — 4 张入口卡片 |
| 1 | **素材库** | `home.html` | `/home` | 网格画廊 — 按日期分组，左侧筛选面板 |
| 2 | **设置** | `settings.html` | `/settings` | 双栏设置页 — OMLX、语音引擎、处理选项 |
| 3 | **任务队列** | `tasks.html` | `/tasks` | 任务表格 — 扫描/关键帧/初剪状态 |
| 4 | **初剪** | `rough-cut.html` | `/rough-cut` | 三栏布局 — 对话侧栏 + 聊天 + 分镜表 |
| 5 | **片段详情** | `clip-detail.html` | `/clip-detail` | 右抽屉 — 标签、建议剪辑、转录、元数据 |
| 6 | **初剪设置** | `rough-cut-settings.html` | `/rough-cut-settings` | 生成选项 + 导演提示词编辑器 |

---

## Navigation Map

```
index.html (Launcher)
  ├── home.html (素材库)
  │     └── clip-detail.html (片段详情) ← 点击任意视频卡片打开
  ├── settings.html (设置)
  ├── tasks.html (任务队列)
  └── rough-cut.html (初剪)
        └── rough-cut-settings.html (初剪设置) ← 点击"初剪设置"按钮打开
```

---

## Design Tokens

### Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--bg-canvas` | `#EEF0F3` | `#0E0F11` | 页面背景 |
| `--surface-1` | `#FFFFFF` | `#16181B` | 卡片/面板背景 |
| `--surface-2` | `#F6F7F9` | `#1E2125` | 输入框/次级背景 |
| `--surface-3` | `#E4E7EC` | `#282C31` | 悬停态背景 |
| `--border` | `#D8DCE2` | `#2E333A` | 边框 |
| `--border-strong` | `#BCC2CB` | `#3A4048` | 强边框 |
| `--text-primary` | `#1A1D21` | `#F2F4F7` | 主文本 |
| `--text-secondary` | `#4B5563` | `#A4ACB9` | 次级文本 |
| `--text-muted` | `#6B7280` | `#6B7280` | 弱化文本 |
| `--primary` | `#5256E0` | `#6366F1` | 主色（按钮/高亮） |
| `--primary-hover` | `#4146C4` | `#7077F2` | 主色悬停 |
| `--primary-soft` | `rgba(82,86,224,0.12)` | `rgba(99,102,241,0.15)` | 主色柔光背景 |
| `--roll-a` | `#B45309` | `#F59E0B` | A-roll 标识 |
| `--roll-b` | `#0F766E` | `#2DD4BF` | B-roll 标识 |
| `--roll-photo` | `#BE185D` | `#F472B6` | 照片标识 |
| `--success` | `#15803D` | `#22C55E` | 成功/完成 |
| `--warning` | `#B45309` | `#F59E0B` | 警告 |
| `--error` | `#DC2626` | `#EF4444` | 错误 |
| `--processing` | `#5256E0` | `#6366F1` | 处理中 |

### Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--font-ui` | `"Inter", "PingFang SC", -apple-system, system-ui, sans-serif` | 界面文本 |
| `--font-mono` | `"JetBrains Mono", ui-monospace, "SF Mono", monospace` | 代码/时间戳/文件大小 |
| `--text-xs` | `12px` | 标签、辅助文本 |
| `--text-sm` | `13px` | 按钮、输入框、列表项 |
| `--text-base` | `14px` | 正文 |
| `--text-md` | `15px` | 小标题 |
| `--text-lg` | `16px` | 页面标题 |
| `--text-xl` | `20px` | 大标题 |
| `--text-2xl` | `24px` | 页面主标题 |
| `--text-3xl` | `32px` | Launcher 标题 |

### Spacing & Radius

| Token | Value |
|-------|-------|
| `--radius-sm` | `6px` |
| `--radius-md` | `8px` (10px on launcher) |
| `--radius-lg` | `10px` (14px on launcher) |
| `--shadow-1` | `0 1px 2px rgba(0,0,0,0.06)` |
| `--shadow-2` | `0 4px 12px rgba(0,0,0,0.08)` |

---

## Page Details

### 0. Launcher (`index.html`)

**Layout:** 居中卡片网格，2×2

**Components:**
- Logo + 标题 "CutFinder"
- 副标题 "AI 驱动的短视频素材管理与初剪工具"
- 4 张入口卡片（素材库 / 设置 / 任务队列 / 初剪）
- 右上角主题切换按钮

**Card structure:**
- 图标（带背景色）
- 标题
- 描述
- "打开 →" 链接

---

### 1. 素材库 (`home.html`)

**Layout:** 顶部栏 + 左侧筛选面板 + 右侧画廊

**Top Bar:**
- Logo + "CutFinder"
- 搜索框 "搜索片段…"
- 导航：任务 / 初剪
- 分隔线
- 设置图标 / 主题切换
- "扫描" 主按钮

**Sidebar (240px):**
- 标题 "筛选" + 收起按钮
- 搜索框 "搜索片段…"
- **类型筛选:** 全部 / A-roll / B-roll / 照片（tab 切换）
- **日期筛选:** 可展开的日期列表，显示片段数
- **标签筛选:** 标签芯片网格 + "显示全部 290"

**Gallery:**
- 工具栏：展开按钮 / "45 个片段" / 排序下拉
- 按日期分组（`2016/08/31 · 45 个片段`）
- 视频卡片网格（`auto-fill, minmax(220px, 1fr)`）

**Video Card:**
- 缩略图（16:9，渐变占位符）
- 类型徽章（A-roll / B-roll / 照片，毛玻璃背景）
- 时长徽章（右下角，黑色半透明）
- 文件名
- 描述（单行截断）
- 标签芯片 + "+N" 更多
- **可点击 → 打开 clip-detail.html**

**Status Bar (底部固定):**
- 处理进度 "▸ 处理中 18/40"
- 当前文件名（等宽字体）
- 状态 "转写中…"
- 进度条 + 百分比

---

### 2. 设置 (`settings.html`)

**Layout:** 顶部栏 + 双栏设置页 + 底部固定保存栏

**Two Columns:**

**Left Column:**
- **界面语言:** 下拉选择（中文 / English）
- **素材文件夹:** 路径输入 + 移除按钮 + "添加文件夹"
- **素材库路径:** 路径输入 + "选择…" 文件夹按钮
- **OMLX 连接:**
  - 连接状态指示（绿色圆点 "已连接"）
  - Base URL（等宽输入）
  - API 密钥（密码输入，显示"已配置"）
  - 文本模型（等宽输入，默认 Qwen3.6-35B-A3B）
  - 视觉模型（等宽输入，默认 Qwen3-VL-8B）
- **语音引擎:**
  - 引擎选择（Whisper / Qwen3-ASR + ForcedAligner）
  - Qwen ASR 模型（等宽输入）
  - ForcedAligner 模型（等宽输入）
  - 分段最大秒数（数字输入，默认 120）

**Right Column:**
- **处理选项:**
  - 视频扩展名芯片（.mov / .mp4 / .m4v）+ 添加
  - 照片扩展名芯片（.jpg / .jpeg / .png / .heic）+ 添加
- **B-roll 帧数:** 数字输入（默认 5）
- **VAD 阈值 (0–1):** 数字输入（默认 0.35）
- **A-roll 转写前分离人声:** Toggle（默认开启）
- **AI 输出语言:** 下拉选择（中文 / English）
- **每段关键帧建议数:** 数字输入（默认 3，范围 1–10）
- **扫描后自动推荐关键帧:** Toggle（默认开启）

**Save Bar (底部固定):**
- "保存设置" 按钮（右对齐）

---

### 3. 任务队列 (`tasks.html`)

**Layout:** 顶部栏 + 表格页面

**Top Bar Actions:**
- "暂停" 按钮（带暂停图标）
- 关闭按钮

**Table:**
| 列 | 宽度 | 内容 |
|---|------|------|
| ID | 60px | `#7` 等宽字体 |
| 类型 | 80px | 徽章：扫描（蓝色）/ 关键帧（橙色）/ 初剪（青色） |
| 状态 | 100px | 已完成（绿色）/ 处理中（蓝色）/ 等待中（灰色）/ 失败（红色） |
| 进度 | 140px+ | 进度条 + `1/1` 等宽标签 |
| 开始时间 | 160px | `2026-08-02 15:24:08` 等宽字体 |
| 操作 | 80px | "删除" 按钮（红色边框） |

---

### 4. 初剪 (`rough-cut.html`)

**Layout:** 顶部栏 + 三栏布局

**Column 1: 对话侧栏 (220px)**
- "新建对话" 按钮
- 收起按钮
- 对话列表（活动高亮 / 未命名灰色斜体）

**Column 2: 聊天面板 (420px)**
- 消息列表（用户消息右对齐蓝色 / 系统消息左对齐白色边框）
- 聊天输入区：
  - 自适应高度文本框
  - "初剪设置" 按钮 → 打开 `rough-cut-settings.html`
  - "发送" 按钮（禁用态/启用态）

**Column 3: 分镜表（弹性宽度）**
- 标题 "分镜表" + 展开按钮 + "复制为 Markdown"
- 按日期分组
- 分镜条目卡片：
  - 序号 + A/B-roll 类型圆点
  - 缩略图（120×68）+ 文件名
  - 时间戳 `[A-roll] 描述`
  - 笔记
  - 文件名

---

### 5. 片段详情 (`clip-detail.html`)

**Layout:** 顶部栏 + 左预览 + 右抽屉 + 底部栏

**Left: Video Preview**
- 视频预览区（黑色背景，渐变占位符）
- 文件名（等宽）
- 描述
- 标签芯片
- 日期（右对齐）

**Right: Detail Drawer (480px)**
- **Tags:**
  - 标签芯片网格（带 × 移除按钮）
  - "Add tag..." 输入框 + "Add" 按钮
- **Suggested Cuts:**
  - "Suggest keyframes" 按钮
  - 建议剪辑卡片（缩略图 + 时间 + 描述）
- **Transcript** (可折叠):
  - 完整转录文本
  - 时间轴分段（`1.2s` / `5.1s` ...）
- **Source File** (可折叠):
  - 文件路径（等宽字体）
- **Metadata** (可折叠):
  - Duration / Resolution / Frame rate / Codec 网格

**Bottom Bar:**
- A-roll / B-roll 切换按钮组
- "Re-analyze" 按钮

---

### 6. 初剪设置 (`rough-cut-settings.html`)

**Layout:** 顶部栏 + 居中设置卡片 + 底部操作栏

**Card Header:**
- "Rough-cut settings" 标题
- "Custom prompt in use" 链接

**Generation Options:**
- **Generation mode:** 下拉（Agent (deeper) / Fast）
  - 说明文本
- **Max tool rounds (agent):** 数字输入（默认 24）
  - 说明文本
- **Per-day catalog size (agent, tokens):** 数字输入（默认 50000）
  - 说明文本
- **Critic review pass:** Checkbox
  - 说明文本
- **Vision look-ups per generation:** 数字输入（默认 6）
  - 说明文本
- **Per-day catalog size (fast, tokens):** 数字输入（默认 40000）
  - 说明文本

**Director Prompt:**
- 说明文本（占位符说明）
- 多行文本编辑器（默认中文导演提示词）

**Footer:**
- "Reset to default" 按钮
- "Cancel" 按钮
- "Save" 按钮（主色）

---

## Component Library

### Buttons

| Type | Style | Usage |
|------|-------|-------|
| Primary | `background: var(--primary); color: white` | 主要操作（扫描、保存、发送） |
| Secondary | `border: 1px solid var(--border); background: var(--surface-2)` | 次要操作 |
| Destructive | `border: 1px solid var(--error); color: var(--error)` | 删除操作 |
| Icon-only | `width: 32px; height: 32px` | 主题切换、关闭 |

### Inputs

| Type | Style |
|------|-------|
| Text | `height: 32px; background: var(--surface-2); border: 1px solid var(--border)` |
| Mono | `font-family: var(--font-mono); font-size: var(--text-xs)` |
| Select | Custom arrow, `padding-right: 28px` |
| Number | `width: 100px; text-align: center` |
| Password | `type="password"` |
| Textarea | `min-height: 180px; resize: vertical` |

### Badges / Chips

| Type | Background | Text |
|------|-----------|------|
| Primary | `var(--primary-soft)` | `var(--primary)` |
| Roll A | `var(--roll-a)` | `white` |
| Roll B | `var(--roll-b)` | `white` |
| Photo | `var(--roll-photo)` | `white` |
| Warning | `rgba(180,83,9,0.1)` | `var(--warning)` |
| Tag | `var(--surface-2); border: 1px solid var(--border)` | `var(--text-primary)` |

### Toggles

- Track: `40×22px`, rounded 11px
- Thumb: `16×16px`, white with shadow
- Active: `background: var(--primary)`

---

## Responsive Breakpoints

| Breakpoint | Behavior |
|-----------|----------|
| `≥ 900px` | 设置页双栏 |
| `< 900px` | 设置页单栏 |
| `≥ 1024px` | 素材库侧栏 240px |
| `< 1024px` | 素材库侧栏 200px |
| `< 768px` | 素材库侧栏绝对定位覆盖 |
| `< 500px` | Launcher 卡片单列 |

---

## Interactive Behaviors

### Theme Toggle
- Persisted to `localStorage('cutfinder-theme')`
- Values: `'light'` / `'dark'`
- Sun icon shown in dark mode, moon icon in light mode

### Collapsible Sections
- Used in clip-detail.html: Transcript, Source File, Metadata
- Chevron rotates 90° when open
- Body toggled via `.hidden` class

### Tag Management
- Add: input + Enter key or "Add" button
- Remove: × button on each chip
- Dynamic re-binding of remove handlers for new tags

### Settings Persistence
- `rough-cut-settings.html` saves to `localStorage('cutfinder-settings')`
- JSON structure: `{ mode, maxRounds, agentCatalog, criticReview, visionLookups, fastCatalog, directorPrompt }`
- Reset clears localStorage and reloads

---

## File Sizes

| File | Size | Lines |
|------|------|-------|
| `index.html` | 10 KB | 307 |
| `home.html` | 39 KB | 989 |
| `settings.html` | 24 KB | 619 |
| `tasks.html` | 15 KB | 447 |
| `rough-cut.html` | 28 KB | 767 |
| `clip-detail.html` | 27 KB | 783 |
| `rough-cut-settings.html` | 20 KB | 570 |
| **Total** | **163 KB** | **4,482** |
