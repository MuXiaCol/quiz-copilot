# 贡献指南

## 跑起来

```powershell
pwsh -File .\setup.ps1
pwsh -File .\start.ps1
```

## 改完要跑测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe tests\smoke.py
.\.venv\Scripts\python.exe tests\mock_api_test.py
```

`tests\launch_test.py` 会真的在桌面左下角弹一个窗口、并短暂注册 F5~F8，跑完自动退出，
适合验证窗口样式和"不抢焦点"的行为。

**不要**在仓库里提交真实 API Key 或带个人信息的截图。Key 只存在
`%APPDATA%\QuizCopilot\config.json`，永远不会进仓库。

## 提交前

- 代码风格：`ruff check .`（没强制，但尽量保持现有风格：4 空格、行宽 100、类型注解）
- 提交信息：`feat: ...` / `fix: ...` / `docs: ...`
- 新增功能请顺手在 `README.md` 的"常见问题"里补一条，如果是行为变化

## 适合上手的改动

- 支持更多模型供应商（现在只按 OpenAI 兼容协议写，加个 `anthropic` 适配层就能扩）
- 答案卡片主题（浅色 / 跟随系统）
- 快捷键冲突的自动避让（`RegisterHotKey` 失败时自动换备用组合）
- 把框选区域持久化到多套预设（不同网站不同布局）

## 方向性说明

这个项目**只做两件事**：看屏幕、显示答案。

不做的：自动点击选项、自动提交、注入页面脚本、绕过平台检测。
这类 PR 不会合并——不是价值判断，是因为它们会让整个方案的边界变得不可控，
而且一旦把"答案"和"提交"绑死，识别错了就会直接变成错答案。
