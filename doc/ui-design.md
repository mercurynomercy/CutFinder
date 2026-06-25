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

### 内容类型（A/B-roll / 照片，务必配图标+文字）
| Token | 值 | 含义 | 图标 |
|---|---|---|---|
| `--roll-a` | `#F59E0B` 琥珀 | A-roll（有解说） | 麦克风 |
| `--roll-b` | `#2DD4BF` 青 | B-roll（纯画面） | 胶片/视频 |
| `--roll-photo` | `#F472B6` 玫红 | 照片 | 图片 |

> 浅色主题下加深以保证对比：`--roll-photo` = `#BE185D`。每个 token 均配 `*-soft` 底色变量（如 `--roll-photo-soft`）。

### 语义状态
| Token | 值 | 用途 |
|---|---|---|
| `--success` | `#34D399` | 处理完成 / 成功 |
| `--warning` | `#FBBF24` | 日期来源不确定等提醒 |
| `--danger` | `#F87171` | 错误 / 破坏性操作 |
| `--processing` | `#6366F1` | 处理中（同主色） |

### 浅色主题（Normal / Light，**默认主题**）

浅色为**默认主题**（`:root`），深色为可切换的第二主题。两者均遵循「desaturated 中性、不做简单反色、逐项验对比度」（`color_dark_mode`）。深色实现上挂在 `html[data-theme="dark"]`，仅**覆盖**配色 token；浅色配色直接落在 `:root`，结构 token（间距/圆角/字体）也共用于 `:root`。

> 注：第 2 节开头标「深色为默认」是 v1 早期基线；现已改为**浅色默认 + 可切换深色**，下表与第 8.1 节为准。

**表面（冷中性浅灰，层级感靠明度递减 + 描边）**
| Token | 值 | 用途 |
|---|---|---|
| `--bg-canvas` | `#EEF0F3` | 最底画布（浅灰，非纯白，护眼） |
| `--surface-1` | `#FFFFFF` | 侧栏 / 顶栏 / 面板（白，浮于画布之上） |
| `--surface-2` | `#F6F7F9` | 卡片 / 输入框 |
| `--surface-3` | `#E4E7EC` | hover / 抬起（浅模式下 hover 加深一档） |
| `--border` | `#D8DCE2` | 描边 / 分隔线 |
| `--border-strong` | `#BCC2CB` | 输入聚焦前描边 |

**文字（on `--surface-1` 白底）**
| Token | 值 | 对比度 |
|---|---|---|
| `--text-primary` | `#1A1D21` | ~16:1 ✅ |
| `--text-secondary` | `#4B5563` | ~7.4:1 ✅ |
| `--text-muted` | `#6B7280` | ~4.8:1 ✅ |

**主色（浅底需略加深以保证白字 ≥4.5:1，hover 改为加深）**
| Token | 值 | 用途 |
|---|---|---|
| `--primary` | `#5256E0` | 白字 ~4.7:1 ✅ |
| `--primary-hover` | `#4146C4` | hover（加深） |
| `--primary-press` | `#383DB0` | active |
| `--primary-soft` | `#5256E0`@12% | 选中底色 / 高亮 |

**内容类型 / 状态（务必加深，原深色饱和值在白底对比度不足）**
| Token | 深色值 | 浅色值 | 白底对比 |
|---|---|---|---|
| `--roll-a` | `#F59E0B` | `#B45309` 深琥珀 | ~5.3:1 ✅ |
| `--roll-b` | `#2DD4BF` | `#0F766E` 深青 | ~5.0:1 ✅ |
| `--success` | `#22C55E` | `#15803D` | ~4.7:1 ✅ |
| `--warning` | `#F59E0B` | `#B45309` | ~5.3:1 ✅ |
| `--error` | `#EF4444` | `#DC2626` | ~4.5:1 ✅ |

> A/B「soft」底色在浅色下用同色 ~12% 低透明度淡彩；徽标始终**色 + 图标 + 文字**三重表达，切主题不破坏可访问性。

**切换交互**：顶栏 ghost 图标按钮（深色态显「太阳」点亮浅色，浅色态显「月亮」切深色），写入 `localStorage`（key `cutfinder-theme`），**默认 `light`**。`index.html` 内联早执行脚本在首帧前设 `data-theme`，避免深色用户的浅色闪烁（FOUC）。`color-scheme` 随主题切换以适配原生滚动条/表单控件。

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
  （凭全局配置自动连接，此处只显示状态）
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
  人声分离    [ ] A-roll 转写前分离人声（去 BGM，较慢）
                                   [保存]
```
- 表单：可见标签（非 placeholder-only）、错误就近显示、blur 时校验。
- OMLX 显「已连接 / 未连接」状态点（调 `check-omlx` 同款探测）。
- **人声分离开关**（`vocal_separation`，默认关）：开启后**之后** scan 的新 A-roll 先用 Demucs 去 BGM 再转写；副文案点明仅影响新片、较慢。字幕导出强制分离，不在此开关范围。
- **初剪逐次生成参数不在此页**：`cut_director_mode`（生成模式）、`cut_max_tool_rounds`（最大工具轮数）、`cut_critic_enabled`（审片复检）、`cut_vision_budget`（视觉确认次数）、`cut_lean_token_budget` / `cut_staged_token_budget`（单日素材目录 token 上限，agent / staged 两档）属于初剪导演的逐次生成参数，放在**初剪页**的「初剪设置」弹窗（与导演 Prompt 同处），不在全局设置里（`tasks/28`）。
- **统一配置视图**（`tasks/29`）：machine-global 键（OMLX 端点/密钥、文本/视觉模型名）与库级 prefs 在 `GET /api/settings` 合并为同一 `prefs` 视图返回（密钥 mask），不再有历史的 `"env"` 分组——前端按一个视图读写。

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
:root {            /* 浅色 = 默认（无 data-theme 时）；结构 token 也在此 */
  color-scheme: light;
  --bg-canvas:#EEF0F3; --surface-1:#FFFFFF; --surface-2:#F6F7F9;
  --surface-3:#E4E7EC; --border:#D8DCE2; --border-strong:#BCC2CB;
  --text-primary:#1A1D21; --text-secondary:#4B5563; --text-muted:#6B7280;
  --primary:#5256E0; --primary-hover:#4146C4; --primary-press:#383DB0; --primary-fg:#fff;
  --roll-a:#B45309; --roll-b:#0F766E;
  --success:#15803D; --warning:#B45309; --error:#DC2626;
  --radius-sm:6px; --radius-md:8px; --radius-lg:10px;
  --font-ui:"Inter","PingFang SC",-apple-system,system-ui,sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,"SF Mono",monospace;
}

[data-theme="dark"] {    /* 深色 = 仅覆盖配色 token，结构 token 复用 */
  color-scheme: dark;
  --bg-canvas:#0E0F11; --surface-1:#16181B; --surface-2:#1E2125;
  --surface-3:#282C31; --border:#2E333A; --border-strong:#3A4048;
  --text-primary:#F2F4F7; --text-secondary:#A4ACB9; --text-muted:#6B7280;
  --primary:#6366F1; --primary-hover:#7077F2; --primary-press:#525AE0;
  --roll-a:#F59E0B; --roll-b:#2DD4BF;
  --success:#22C55E; --warning:#F59E0B; --error:#EF4444;
}
```

**主题切换落地**：
- `index.html` `<head>` 内联早执行脚本读 `localStorage['cutfinder-theme']`，首帧前给 `<html>` 设 `data-theme`，避免 FOUC。
- `src/theme.ts` 暴露 `getStoredTheme()` / `applyTheme(theme)`（写 `data-theme` + `localStorage`）。
- 顶栏 ghost 图标按钮调 `applyTheme` 切换并更新本地 state（太阳/月亮图标互换）。

### 8.2 Tailwind / shadcn
- 把上面的 token 映射到 `tailwind.config` 的 `theme.extend.colors` 与 `fontFamily`，shadcn/ui 主题变量指向同一套 CSS 变量，确保所有组件统一。
- 字体：Inter / JetBrains Mono 用 `@fontsource` 本地引入（离线，`font-display: swap`）；中文走系统 PingFang SC 不额外下载。

### 8.3 与任务衔接
- `14-frontend` 各 feature 复用本系统：gallery=缩略图卡片、filters=侧栏、detail=右抽屉、settings=设置表单、jobs=进度条/任务面板。
- 建议先建 `frontend/src/styles/tokens.css` + 一个 Storybook/示例页固化按钮/Chip/卡片三件套，再铺页面。

---

## 9. 原生 macOS App 外壳（窗口 / 安装 / 菜单）

> 配合 detailed-design §11「原生 macOS .app 外壳」。原生 Swift/AppKit 包装器把现有 web UI 用 **WKWebView 内嵌**为一个真正的 Mac App：无浏览器、无标签页，点 Dock 重开窗口。原生层只新增三类画面——**安装中**、**运行中（即 web UI 本身）**、**错误/引导**——以及一套**标准应用菜单**。配色一律复用第 2 节 token（**浅色默认**，跟随系统/应用主题）。

### 9.1 窗口与三态

单窗口，按服务状态切换内容：

| 态 | 内容 | 配色 |
|---|---|---|
| 安装中 | 原生 `SetupView`：步骤清单 + 进度条 + 可折叠日志 | `--bg-canvas` 底、`--surface-1` 卡片、`--primary` 进度 |
| 运行中 | `WKWebView` 加载 `http://127.0.0.1:PORT/`（即现有缩略图墙 UI） | web 自身主题 |
| 错误/引导 | 原生 `ErrorView`：标题 + 说明 + 操作按钮 | `--warning`/`--error` 配图标+文字 |

- 窗口默认尺寸 ≈ 1100×720（容得下 4 列缩略图），最小 ≈ 900×600；记忆上次尺寸/位置。
- 标题栏可放一个**服务状态点**（accessory）：`● 运行中`(--success) / `● 已停止`(--text-muted) / `◐ 启动中`(--primary, 旋转) / `● 错误`(--error)——色 + 文字双表达。

### 9.2 首次安装视图（SetupView）

启动即自动跑，逐步点亮。每行 = 状态图标 + 名称 + 副文案；底部整体进度条 + 折叠日志。

```
┌─ CutFinder ─────────────────────────────  ● 安装中 ─┐
│                                                     │
│        ◧  正在准备 CutFinder（首次启动）              │
│        首次需要联网安装运行环境与模型，约几分钟         │
│                                                     │
│   ✓  应用文件            已就绪                       │
│   ✓  uv（Python 工具链）  已安装                      │
│   ⟳  ffmpeg             安装中…                      │
│   ·  Python 运行环境     等待                         │
│   ·  AI 模型(whisper/demucs) 等待 · 约 3GB           │
│   ·  OMLX 模型服务        待探测                       │
│                                                     │
│   ▮▮▮▮▮▮▯▯▯▯  45%                                   │
│   ▸ 查看安装日志                                      │
└─────────────────────────────────────────────────────┘
```

- 状态图标：`✓`完成(--success) / `⟳`进行中(--primary, 旋转) / `·`等待(--text-muted) / `⚠`失败(--warning/--error)。
- 仅状态色不达意——一律**图标 + 文字**（沿用 `color-not-only`）。
- 失败行就地展开「重试 / 查看日志 / 引导」，不打断其余步骤。
- 进度与日志数据来自 Provisioner 回调；日志默认折叠（`blur`/disclosure），点开滚动显示底层命令输出。

### 9.3 错误 / 引导视图（ErrorView）

用于「可继续但功能受限」或「需用户动手」的情形，最典型是 **OMLX 未就绪**：

```
┌─ CutFinder ─────────────────────────────────────────┐
│                                                     │
│   ⚠  未检测到 OMLX 模型服务                            │
│   CutFinder 的「A-roll 简介 / B-roll 画面打标」需要    │
│   本机的 OMLX（独立 App，负责文本/视觉模型）。          │
│   扫描、转写、缩略图不受影响，可先继续使用。            │
│                                                     │
│   [ 打开 OMLX 下载页 ]  [ 重试探测 ]  [ 仍然继续 ]     │
│   ▸ 详情 / 日志                                       │
└─────────────────────────────────────────────────────┘
```

- 主操作（下载页/重试）用 Primary，「仍然继续」用 Secondary，三者分离避免误触。
- 外部链接走系统浏览器（`NSWorkspace`），不在内嵌 webview 打开。
- 同款式覆盖：ffmpeg 缺失且无 Homebrew、`uv sync` 失败、端口被占等——文案点明下一步与日志位置。

### 9.4 应用菜单（标准 + 服务菜单）

```
 CutFinder  文件  编辑  显示  服务  窗口  帮助
 ─────────
 CutFinder ▸ 关于 CutFinder · 偏好设置(端口/开机自启)… · 隐藏 · 退出 CutFinder(⌘Q)
 显示     ▸ 重新加载(⌘R) · 实际大小 · 进入全屏
 服务     ▸ 开启服务 · 停止服务 · 重启服务 · ─── · 在浏览器中打开 · 打开素材库文件夹 · 打开日志 · 重新运行安装
 帮助     ▸ CutFinder 文档 · 检查 OMLX 状态
```

- 「服务」菜单项随 `ServerController` 状态启用/禁用（运行中禁「开启」、停止时禁「停止/重启」）。
- ⌘Q 先停服务再退（无孤儿进程）；关闭窗口不退、Dock 点击重开（detailed-design §11.3）。
- 「在浏览器中打开」给偏好用系统浏览器的用户保留旧路径（打开同一 `127.0.0.1:PORT`）。

### 9.5 与 web 主题的关系 / 可访问性

- 原生画面（Setup/Error）**复用第 2 节配色 token 的等价取值**（浅色默认，深色可同步），与内嵌的 web UI 视觉连续。
- 焦点环、键盘可达、`prefers-reduced-motion`（旋转图标降级为静态）与第 7 节一致。
- 安装/错误文案默认中文（与全局一致），关键名词（ffmpeg/uv/OMLX）保留英文。

---

*本设计系统为 v1 基线，配色（尤其主色与 A/B 类型色）可按你的偏好调整。*
