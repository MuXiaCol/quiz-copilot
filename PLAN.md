# QuizCopilot 技术方案（v2 · 已实现）

> v1 的规划是"OCR + 文本模型"，v2 因为 DeepSeek 的 `deepseek-flash` 支持图片输入而整体改道：
> **截图直接进多模态模型，彻底去掉 OCR**。代码按本文实现，`README.md` 是使用手册。

---

## 1. 需求定稿

你给的 4 条约束，直接决定架构：

| 约束 | 落地方式 |
|---|---|
| 通用，不用管平台作弊检测，但**不能抢焦点** | 只做"屏幕像素 → 答案"，不注入页面、不碰浏览器进程；窗口用 `WS_EX_NOACTIVATE` |
| 自己的 API Key | 设置界面填，存 `%APPDATA%\QuizCopilot\config.json`，任何 OpenAI 兼容端点都能接 |
| 不自动点击 | 程序只显示答案，鼠标键盘一概不模拟 |
| 固定屏幕左下角 | 窗口每次都钉在 `availableGeometry().bottomLeft() + margin` |
| 快捷键 F5 开始识别 | 全局 `RegisterHotKey`，F5 识别 / F6 显隐 / F7 框选 / F8 设置 |

额外确认：**不要 OCR**。因此没有文本解析、没有 OCR 模型、没有本地推理。

---

## 2. 为什么走视觉而不是 OCR

| | OCR + 文本模型 | **视觉直连（采用）** |
|---|---|---|
| 错字 | 有，中文小字/公式/符号经常错 | 无 |
| 带图题、表格题 | 基本没法读 | 能读 |
| 代码量 | 截图 + OCR + 切带 + 行合并 + 正则解析 + 提示词 | 截图 + 切带 + 提示词 |
| 依赖 | onnxruntime + 模型 + opencv（约 400MB） | 无额外依赖 |
| 成本 | 低（token 少） | 每张图最多 1024 token，固定上限 |
| 可维护性 | 每换一个平台可能要调解析规则 | 平台无关 |

代价是每题几毛钱级别的 API 费用，以及需要"模型名必须支持图片输入"。这个交换非常划算。

---

## 3. 架构

```
        F5 / 自动模式
             │
             ▼
   ┌──────────────────────┐
   │ screen.grab(rect)    │  mss，物理像素截图
   └──────────┬───────────┘
              ▼
   ┌──────────────────────┐
   │ imageutil.strip_images│ 按空白行切横带（仅长图），保住小字
   └──────────┬───────────┘
              ▼
   ┌──────────────────────┐
   │ solver.solve          │ PNG→base64→image_url 块（多图一次请求）
   │  ├ 缓存命中？          │ sha256(所有带) → sqlite
   │  ├ 请求模型            │ deepseek-flash，response_format=json_object
   │  ├ JSON 抽取 + 归一化  │ 容错 ```json 围栏、answer 写成字符串/数组
   │  └ 低置信度二次复核    │ conf < 0.70 再问一次，取更有把握的版本
   └──────────┬───────────┘
              ▼
   ┌──────────────────────┐
   │ ui.overlay            │ 左下角、置顶、半透明、永不激活
   └──────────────────────┘
```

**线程模型**：截图和网络请求都在 `SolveWorker(QThread)` 里，UI 只在主线程更新；同一时刻只跑一个 worker，重复触发会排队合并。

**自动模式**：`ChangeWatcher` 用 1.2 秒定时器 + 降采样灰度哈希比对画面，连续两拍稳定且与上次不同才触发，避免闪烁误报。

---

## 4. 关键技术点

### 4.1 不抢焦点（核心）

Win32 里"点不激活"只有 `WS_EX_NOACTIVATE` 管用，Qt 的 `WindowDoesNotAcceptFocus` 只是加了同样的位。三重保险：

```python
super().__init__(None,
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool                      # 不进任务栏 / Alt+Tab
    | Qt.WindowType.WindowDoesNotAcceptFocus) # 不接焦点

self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

# 每次 show 后补一次 Win32 样式
ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
ex |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
user32.SetWindowPos(hwnd, HWND_TOPMOST, 0,0,0,0, SWP_NOACTIVATE | ...)
```

代码里**从不调用** `activateWindow()` / `raise_()`。验证方法：浏览器控制台挂 `blur` 计数器，操作完必须是 0。

### 4.2 智能切带

视觉模型会把每张图等比缩到约 1300×1300 再算 token。一张 2560×1380 的整屏截进去，字会被压小一半。

所以长图先切：扫每行"墨量"，找空白行做切点，尽量不被一道题拦腰截断，

```
strips = [(0, 980), (980, 1950), (1950, 2600)]   # 切点落在空白带
```

每张图独立享受 1024 token 的分辨率预算，等于把可用清晰度翻倍。多张图放在**同一个请求**里，模型按顺序拼读，并被告知相邻图有重叠、同题只答一次。

### 4.3 透明窗里的白块问题

这是个容易踩的坑：`WA_TranslucentBackground` 只对顶层窗口生效，子控件（QScrollArea 的 viewport、QFrame 卡片）仍按调色板填充，默认是浅色 → 深色悬浮窗里冒出白块。

解法是两条一起上：
1. `QApplication.setStyle("Fusion")` + 全局深色 `QPalette`（任何自动填充都是深色）
2. viewport / 容器 / 卡片显式 `background: transparent` + `WA_TranslucentBackground`

### 4.4 高度自适应 + 钉左下角

新插入的卡片要等事件循环跑过一次 polish，`sizeHint()` 才有值，否则第一拍测出来是 0。所以：

```python
def _relayout(self, reschedule=True):
    ... 测量、设尺寸、锚定左下角 ...
    if reschedule:
        QTimer.singleShot(0, lambda: self._relayout(reschedule=False))
```

两次测量在同一个事件循环轮次内完成，用户看不到中间态。高度超过屏幕 72% 时封顶，内部出现滚动条。

### 4.5 提示词约束

- `response_format={"type":"json_object"}`，端点不支持时自动降级重试
- 强制输出 `{no, type, stem, answer, option_text, confidence, reason}`
- 明确要求"只依据图片内容，看不清就降低 confidence，不要编造"
- 明确要求"页面上出现'我的答案/正确答案'回显时不要照抄"——否则模型会直接抄平台的答案
- `option_text` 是关键：它让卡片能同时显示"字母"和"选项原文"，用户一眼能核对

---

## 5. 目录与文件

```
app/
  main.py        装配 + 托盘 + 深色调色板
  config.py      配置（%APPDATA%\QuizCopilot\config.json）
  screen.py      截图 / 虚拟桌面几何 / 画面哈希
  imageutil.py   PNG 编码 + 按空白行切带
  solver.py      提示词、请求、JSON 抽取归一、复核、缓存写入
  cache.py       sqlite
  pipeline.py    SolveWorker(QThread) + ChangeWatcher(QTimer) + Pipeline
  hotkeys.py     RegisterHotKey + nativeEventFilter
  win32util.py   WS_EX_NOACTIVATE / SetWindowPos
  ui/            overlay / card / region_picker / settings_dialog / theme
```

运行期产物都在 `%APPDATA%\QuizCopilot\`：`config.json`、`cache.db`、`quizcopilot.log`。

---

## 6. 验证记录

| 项 | 方法 | 结果 |
|---|---|---|
| 真实窗口能起 | `tests/launch_test.py`（真起窗口 2.8s 后退出） | 通过，430×396 |
| 卡片渲染 | 同上，`win.grab()` 存 PNG 目视检查 | 通过（见 README 图） |
| JSON 容错 | `tests/smoke.py`，故意带 ` ```json ` 围栏、answer 混用字符串/数组 | 通过 |
| 请求体结构 | `tests/mock_api_test.py` 本地 mock 服务抓包 | png base64 data URL、`detail=high`、模型名正确 |
| 长图切带 | 2600px 高图 | 切成 3 张 |
| 缓存 | 同图第二次 | 无网络请求 |
| 打包 | `build.ps1` | 见下 |

---

## 7. 已知取舍

- **不自动点击/提交**：识别有偏差时不会把错答案提交上去；也避免由程序产生的任何操作痕迹。
- **模型自报置信度不可全信**：多选、图表题的实际错率明显高于单选题。低于 65% 标红提示自查。
- **全局热键会抢占浏览器的 F5**：程序运行期间网页不会刷新。介意就改键。
- **框选质量决定准确率**：框进地址栏/侧边目录会浪费 token 并干扰模型，尽量只框题目本体。
- **多屏混 DPI**：区域坐标按虚拟桌面整体比例换算，单个显示器缩放不一致时可能偏几个像素，重框一次即可。
