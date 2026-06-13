# CutFinder UI 设计系统

> 统一的配色 / 字体 / 间距 token + 组件规范 + 关键页面布局。深色优先，专业剪辑工具调性，配合 Final Cut Pro 工作流。
> **对接任务**：[`tasks/14-frontend.md`](./tasks/14-frontend.md)。 **技术栈**：Vite + React + Tailwind + shadcn/ui。

---

## 1. 设计方向

- **近黑面板、内容为王**：界面用低饱和中性深灰，让视频缩略图成为视觉焦点（参考 FCP / DaVinci / Premiere）。
- **一个主色 + 两个内容色**：主交互色 = 靛蓝；A-roll = 琥珀、B-roll = 青。三者色相分离，且 A/B 永远**颜色 + 图标 + 文字**三重表达（可访问性 `color-not-only`）。
- **数据用等宽字**：时间码、时长、分辨率、文件路径用等宽字（`number_tabular`，防跳动）。
- **克制的动效**：150–250ms，仅状态过渡与进度，尊重 `prefers-reduced-motion`。

---

## 2. 颜色 Token（深色为默认主题）

### 表面 / 层级（中性冷灰）
| Token | 值 | 用途 |
|---|---|---|
| `--bg-canvas` | `#0E0F11` | 最底画布 |
| `--surface-1` | `#16181B` | 侧栏 / 顶栏 / 面板 |
| `--surface-2` | `#1E2125` | 卡片 / 输入框 |
| `--surface-3` | `#282C31` | hover / 抬起 |
| `--border` | `#2E333A` | 描边 / 分隔线 |
| `--border-strong` | `#3A4048` | 输入聚焦前描边 |

### 文字
| Token | 值 | 对比度(on surface-1) |
|---|---|---|
| `--text-primary` | `#F2F4F7` | ~15:1 ✅ |
| `--text-secondary` | `#A4ACB9` | ~7:1 ✅ |
| `--text-muted` | `#6B7280` | ~4.6:1 ✅（仅用于次要元信息） |

### 主色（交互 / CTA / 聚焦 / 选中 / 当前导航）
| Token | 值 | 用途 |
|---|---|---|
| `--primary` | `#6366F1` | 按钮填充 / 链接 / 焦点环 |
| `--primary-hover` | `#7077F2` | hover |
| `--primary-press` | `#525AE0` | active |
| `--primary-fg` | `#FFFFFF` | 主色按钮上的文字 |
| `--primary-soft` | `#6366F1`@16% | 选中底色 / 高亮区 |

### 内容类型（A/B-roll，务必配图标+文字）
| Token | 值 | 含义 | 图标 |
|---|---|---|---|
| `--roll-a` | `#F59E0B` 琥珀 | A-roll（有解说） | 麦克风 |
| `--roll-b` | `#2DD4BF` 青 | B-roll（纯画面） | 胶片/视频 |

### 语义状态
| Token | 值 | 用途 |
|---|---|---|
| `--success` | `#34D399` | 处理完成 / 成功 |
| `--warning` | `#FBBF24` | 日期来源不确定等提醒 |
| `--danger` | `#F87171` | 错误 / 破坏性操作 |
| `--processing` | `#6366F1` | 处理中（同主色） |

> **浅色主题**：留作后续。届时用 desaturated 调，不做简单反色，单独验对比度（`color_dark_mode`）。

---

## 3. 字体 Token

- **UI 字体**：`Inter`（拉丁，密集 UI 表现好、可变字重）+ `PingFang SC`（中文，macOS 原生）。
- **等宽字体**：`JetBrains Mono`（时间码 / 时长 / 分辨率 / 路径 / 标签计数）。
- **字体栈**
  ```css
  --font-ui:   "Inter", "PingFang SC", -apple-system, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
  ```
- **字号阶梯**（桌面工具偏密，base=14）
  | Token | px | 用途 | line-height |
  |---|---|---|---|
  | `--text-xs` | 12 | 元信息 / 角标 | 1.4 |
  | `--text-sm` | 13 | 标签 / 次要 | 1.5 |
  | `--text-base` | 14 | UI 正文 | 1.5 |
  | `--text-md` | 15 | **阅读内容**（简介/转写） | 1.6 |
  | `--text-lg` | 16 | 区块标题 | 1.4 |
  | `--text-xl` | 20 | 面板标题 | 1.3 |
  | `--text-2xl` | 24 | 页面标题 | 1.25 |
- **字重**：正文 400 / 标签 500 / 标题 600。
- 阅读型内容（简介、转写全文）用 `--text-md` + line-height 1.6，行宽控制在 60–75 字符。

---

## 4. 间距 / 圆角 / 阴影

- **间距**（4px 基准）：`4 8 12 16 20 24 32 40 48`。布局用 8 的倍数，组件内边距用 12/16。
- **圆角**：`--radius-sm 6`（按钮/输入/chip）、`--radius-md 8`（卡片/缩略图）、`--radius-lg 10`（面板/弹窗）、`--radius-full`（头像/状态点）。
- **阴影**（深色下克制，靠描边+轻抬起）：
  - `--shadow-1`：卡片 `0 1px 2px rgba(0,0,0,.4)`
  - `--shadow-2`：弹层/抽屉 `0 8px 24px rgba(0,0,0,.5)`
  - 弹窗背景用 backdrop blur（`blur_purpose`：表示可点击外部关闭）。

---

## 5. 组件规范

### 按钮
| 变体 | 样式 | 用途 |
|---|---|---|
| Primary | `--primary` 填充 + 白字 | 每屏唯一主操作（扫描 / 保存） |
| Secondary | `--surface-2` + `--border` 描边 | 次要操作 |
| Ghost | 透明 + hover 显 `--surface-3` | 工具栏图标按钮 |
| Danger | `--danger` 描边/填充 | 破坏性（与主操作分离） |

- 高度：`sm 28` / `md 32`（默认）/ `lg 36`；图标按钮 ≥ 32×32，移动端命中区补到 44。
- 状态：hover 提亮一档；active `scale .98`；disabled `opacity .4` + 禁用光标；**焦点 2px `--primary` 环 + 2px offset**（不可移除）。
- 异步操作时按钮内置 spinner 并禁用（`loading-buttons`）。

### 标签 Chip
- 基础：`--surface-2` 底 + `--text-secondary`，圆角 sm。
- **A/B 类型徽标**：`--roll-a`/`--roll-b` 描边 + 同色 12px 图标 + 文字「A-roll / B-roll」。
- **自动 vs 手动标签**：自动 = 前置小圆点（弱）；手动 = 实心底色（强）；可删标签右侧 `×`，命中区 ≥ 16px。

### 缩略图卡片（gallery 核心）
```
┌──────────────────────────┐
│ ⬤A-roll            0:42  │  ← 左上 A/B 徽标(色+图标)，右下时长(mono)
│                          │
│        [16:9 帧]          │
│                          │
│ 旅行清晨的海边…  #海 #日出 │  ← 标题/简介一行截断 + 标签
└──────────────────────────┘
```
- 比例 16:9，圆角 md，`image-dimension` 预留尺寸防 CLS，懒加载。
- hover：轻微 `scale 1.02` + 显示快捷操作（详情/重新分析）。
- 选中：2px `--primary` 环。
- 列表 ≥ 50 项用虚拟滚动（`virtualize-lists`）。

### 输入 / 搜索
- `--surface-2` 底 + `--border`，聚焦换 `--primary` 环。
- 搜索框前置放大镜图标，支持清除按钮；可显示最近/建议查询。

### 进度（SSE）
- 顶部 2px 确定性进度条（主色）。
- 任务面板：每片段一行 = 文件名(mono) + 状态图标（spinner/✓/✕）+ 当前阶段文字（"转写中…"/"识别画面…"）。
- 完成弹 toast（3–5s 自动消失，`aria-live=polite` 不抢焦点）。

---

## 6. 关键页面布局

### 6.1 应用骨架 + 缩略图墙
```
┌─────────────────────────────────────────────────────────────┐
│ CutFinder   🔍[搜索台词/画面…]            [＋扫描]   ⚙设置    │ 顶栏 surface-1
├───────────────┬─────────────────────────────────────────────┤
│ 筛选 (侧栏)    │  全部 1,284 · A-roll 412 · B-roll 872        │
│               │  ┌────┐ ┌────┐ ┌────┐ ┌────┐                 │
│ 日期          │  │card│ │card│ │card│ │card│   缩略图网格     │
│  2026-06 ▸    │  └────┘ └────┘ └────┘ └────┘                 │
│  2026-05 ▸    │  ┌────┐ ┌────┐ ┌────┐ ┌────┐                 │
│               │  │card│ │card│ │card│ │card│                 │
│ 类型          │  └────┘ └────┘ └────┘ └────┘                 │
│  ◉全部 ⬤A ⬤B │                                              │
│               │                                              │
│ 标签          │                                              │
│  #海边 #城市   │                                              │
│  #美食 …      │                                              │
├───────────────┴─────────────────────────────────────────────┤
│ ▸ 处理中 18/40  MVI_5402.MP4 转写中…            ▮▮▮▮▮▯▯ 45%  │ 进度条
└─────────────────────────────────────────────────────────────┘
```
- 大屏（≥1024px）用侧栏导航（`adaptive_navigation`）；当前筛选高亮。
- 网格响应式：列数随宽度 2→3→4→5 自适应。

### 6.2 片段详情（右侧抽屉，从右滑入）
```
┌──────────────────────────────┐
│ MVI_5298.MP4            ✕     │
│ ┌──────────────────────────┐ │
│ │     [视频预览/代表帧]      │ │
│ └──────────────────────────┘ │
│ ⬤A-roll   2026-06-13  0:42   │  类型徽标 + 拍摄日期 + 时长(mono)
│                              │
│ 简介                          │
│ 清晨在海边散步，讲述这次旅行… │  ← --text-md，可编辑
│                              │
│ 标签   #海边 #日出 #旅行 ＋    │  手动可增删
│                              │
│ 转写全文 ▾                    │  折叠，可搜索高亮
│ 「今天我们来到了…」           │
│                              │
│ 元数据  1920×1080·H.264·mono  │  mono
│ 库内路径 …/2026-06-13/A-roll/ │  mono，可复制
│                              │
│ [改为 B-roll]   [↻ 重新分析]  │  次要 + 重新分析按钮
└──────────────────────────────┘
```
- 「重新分析」触发 `POST /clips/{id}/reanalyze`，按钮进入 loading；保留手动纠正。
- 编辑简介/标签即时乐观更新，失败回滚 + toast。

### 6.3 设置
```
连接
  OMLX 接口   [http://localhost:8000/v1]   ● 已连接
  （API Key 来自 .env，此处只显示状态）
模型
  文本模型    [Qwen3.6-35B-A3B        ▾]
  视觉模型    [Qwen3-VL-8B-Instruct   ▾]
  Whisper     [large-v3               ▾]
文件夹
  源文件夹    [/Users/…/Footage] [＋添加]
  素材库      [/Users/…/Library]
扫描
  扩展名      [.mov .mp4 .m4v]
  B-roll 抽帧 [3]    VAD 阈值 [0.15]
                                   [保存]
```
- 表单：可见标签（非 placeholder-only）、错误就近显示、blur 时校验。
- OMLX 显「已连接 / 未连接」状态点（调 `check-omlx` 同款探测）。

---

## 7. 可访问性 / 质量清单

- **对比度**：所有正文 ≥ 4.5:1；A/B 色块附图标+文字，绝不仅靠颜色。
- **焦点可见**：2px `--primary` 焦点环，键盘 Tab 顺序与视觉一致。
- **图标按钮**：均带 `aria-label`（设置、关闭、重新分析、删除标签）。
- **动效**：150–250ms，仅 transform/opacity；尊重 `prefers-reduced-motion`。
- **空态**：无素材时显「还没有素材，点『扫描』开始」+ 按钮（`empty_states`）。
- **破坏性确认**：「改为 B-roll / 重新分析」属可逆，无需确认弹窗；未来若有删除则需确认 + undo toast。
- **等宽对齐**：时长、时间码、元数据用 `--font-mono` + tabular-nums。

---

## 8. 实现落地

### 8.1 CSS 变量（`tokens.css`，挂在 `:root`）
```css
:root {
  color-scheme: dark;
  --bg-canvas:#0E0F11; --surface-1:#16181B; --surface-2:#1E2125;
  --surface-3:#282C31; --border:#2E333A; --border-strong:#3A4048;
  --text-primary:#F2F4F7; --text-secondary:#A4ACB9; --text-muted:#6B7280;
  --primary:#6366F1; --primary-hover:#7077F2; --primary-press:#525AE0; --primary-fg:#fff;
  --roll-a:#F59E0B; --roll-b:#2DD4BF;
  --success:#34D399; --warning:#FBBF24; --danger:#F87171;
  --radius-sm:6px; --radius-md:8px; --radius-lg:10px;
  --font-ui:"Inter","PingFang SC",-apple-system,system-ui,sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,"SF Mono",monospace;
}
```

### 8.2 Tailwind / shadcn
- 把上面的 token 映射到 `tailwind.config` 的 `theme.extend.colors` 与 `fontFamily`，shadcn/ui 主题变量指向同一套 CSS 变量，确保所有组件统一。
- 字体：Inter / JetBrains Mono 用 `@fontsource` 本地引入（离线，`font-display: swap`）；中文走系统 PingFang SC 不额外下载。

### 8.3 与任务衔接
- `14-frontend` 各 feature 复用本系统：gallery=缩略图卡片、filters=侧栏、detail=右抽屉、settings=设置表单、jobs=进度条/任务面板。
- 建议先建 `frontend/src/styles/tokens.css` + 一个 Storybook/示例页固化按钮/Chip/卡片三件套，再铺页面。

---

*本设计系统为 v1 基线，配色（尤其主色与 A/B 类型色）可按你的偏好调整。*
