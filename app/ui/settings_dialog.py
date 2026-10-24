"""设置对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..config import Config
from ..solver import test_connection


class SettingsDialog(QDialog):
    pick_region_requested = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("QuizCopilot 设置")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ---------------- API ----------------
        api_box = QGroupBox("模型接口")
        form = QFormLayout(api_box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.base_url = QLineEdit(str(cfg.get("api.base_url", "")))
        self.base_url.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("接口地址", self.base_url)

        key_row = QHBoxLayout()
        self.api_key = QLineEdit(str(cfg.get("api.api_key", "")))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-...")
        key_row.addWidget(self.api_key, 1)
        self.show_key = QCheckBox("显示")
        self.show_key.toggled.connect(
            lambda on: self.api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.show_key)
        form.addRow("API Key", key_row)

        self.model = QLineEdit(str(cfg.get("api.model", "deepseek-flash")))
        self.model.setPlaceholderText("deepseek-flash（必须支持图片输入）")
        form.addRow("模型", self.model)

        think_row = QHBoxLayout()
        self.thinking = QComboBox()
        for text, value, tip in (
            ("关闭 —— 最快最省，概念题准确率会降", "off", "不产生思维链，temperature 才会生效"),
            ("低 —— 默认，速度与准确率折中", "low", "思维链较短，适合大多数刷题场景"),
            ("高 —— 更准更慢", "high", "服务端默认值，思维链较长"),
            ("最高 —— 最准最慢最贵", "max", "不推荐，这类任务用不上"),
        ):
            self.thinking.addItem(text, value)
            self.thinking.setItemData(self.thinking.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        cur = str(cfg.get("api.thinking", "low") or "low").lower()
        idx = self.thinking.findData(cur)
        self.thinking.setCurrentIndex(idx if idx >= 0 else 1)
        think_row.addWidget(self.thinking, 1)
        form.addRow("思考等级", think_row)
        self.thinking.setToolTip(
            "deepseek-flash 默认是「思考开启 + 高」；这里显式选择避免一直跑最高档。\n"
            "思考模式会忽略 temperature。"
        )

        self.stream = QCheckBox("流式输出：答案边生成边显示")
        self.stream.setChecked(bool(cfg.get("api.stream", True)))
        self.stream.setToolTip(
            "开启后每凑齐一道完整的题就先显示，第 1 题出结果时其余题可能还在生成。\n"
            "个别端点不支持流式会自动降级为整段返回。"
        )
        form.addRow("", self.stream)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._on_test)
        test_row.addWidget(self.test_btn)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        test_row.addWidget(self.test_result, 1)
        form.addRow("", test_row)

        root.addWidget(api_box)

        # ---------------- 采集 ----------------
        cap_box = QGroupBox("识别区域")
        cap_lay = QVBoxLayout(cap_box)
        row = QHBoxLayout()
        self.region_label = QLabel("")
        row.addWidget(self.region_label, 1)
        pick_btn = QPushButton("重新框选…")
        pick_btn.clicked.connect(self._on_pick)
        row.addWidget(pick_btn)
        cap_lay.addLayout(row)
        self._update_region_label()
        root.addWidget(cap_box)

        # ---------------- 外观 ----------------
        ui_box = QGroupBox("悬浮窗")
        ui_form = QFormLayout(ui_box)
        ui_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(300, 800)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(cfg.get("ui.width", 430)))
        ui_form.addRow("宽度", self.width_spin)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.5, 1.0)
        self.opacity_spin.setSingleStep(0.02)
        self.opacity_spin.setDecimals(2)
        self.opacity_spin.setValue(float(cfg.get("ui.opacity", 0.94)))
        ui_form.addRow("不透明度", self.opacity_spin)

        self.show_reason = QCheckBox("显示推理理由")
        self.show_reason.setChecked(bool(cfg.get("ui.show_reason", True)))
        ui_form.addRow("", self.show_reason)

        self.click_through = QCheckBox("鼠标穿透（点不到窗口，只能靠热键操作）")
        self.click_through.setChecked(bool(cfg.get("ui.click_through", False)))
        ui_form.addRow("", self.click_through)

        root.addWidget(ui_box)

        # ---------------- 行为 ----------------
        beh_box = QGroupBox("行为")
        beh_lay = QVBoxLayout(beh_box)

        self.auto_mode = QCheckBox("自动模式：画面静止且变化后自动重新识别")
        self.auto_mode.setChecked(bool(cfg.get("behavior.auto_mode", False)))
        beh_lay.addWidget(self.auto_mode)

        poll_row = QHBoxLayout()
        poll_row.addWidget(QLabel("轮询间隔（毫秒）"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(400, 5000)
        self.poll_spin.setSingleStep(100)
        self.poll_spin.setValue(int(cfg.get("behavior.poll_interval_ms", 800)))
        poll_row.addWidget(self.poll_spin)
        poll_row.addStretch(1)
        beh_lay.addLayout(poll_row)

        self.use_cache = QCheckBox("使用本地答案缓存")
        self.use_cache.setChecked(bool(cfg.get("behavior.use_cache", True)))
        beh_lay.addWidget(self.use_cache)

        self.vote = QCheckBox("低置信度时复算一次，取更可信的结果")
        self.vote.setChecked(bool(cfg.get("behavior.vote_low_confidence", True)))
        beh_lay.addWidget(self.vote)

        root.addWidget(beh_box)

        # ---------------- 快捷键 ----------------
        hk_box = QGroupBox("快捷键（全局生效）")
        hk_form = QFormLayout(hk_box)
        hk_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.hk_capture = QLineEdit(str(cfg.get("hotkeys.capture", "F5")))
        hk_form.addRow("识别当前区域", self.hk_capture)

        self.hk_toggle = QLineEdit(str(cfg.get("hotkeys.toggle", "F6")))
        hk_form.addRow("显示/隐藏悬浮窗", self.hk_toggle)

        self.hk_pick = QLineEdit(str(cfg.get("hotkeys.pick", "F7")))
        hk_form.addRow("重新框选区域", self.hk_pick)

        self.hk_settings = QLineEdit(str(cfg.get("hotkeys.settings", "F8")))
        hk_form.addRow("打开设置", self.hk_settings)

        hk_tip = QLabel("格式：F5、A、Ctrl+Alt+Q；F1~F24 和字母数字都可以。保存后立即生效。")
        hk_tip.setWordWrap(True)
        hk_tip.setStyleSheet("color: #8a92a0;")
        hk_form.addRow("", hk_tip)

        root.addWidget(hk_box)

        # ---------------- 按钮 ----------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    def _update_region_label(self) -> None:
        l, t, w, h = self.cfg.region
        if w <= 0 or h <= 0:
            self.region_label.setText("整屏（未框选）")
        else:
            self.region_label.setText(f"已框选：({l}, {t})  {w} × {h}")

    def _on_pick(self) -> None:
        self.pick_region_requested.emit()

    def refresh_region(self) -> None:
        self._update_region_label()

    def _collect(self) -> None:
        cfg = self.cfg
        cfg.set("api.base_url", self.base_url.text().strip())
        cfg.set("api.api_key", self.api_key.text().strip())
        cfg.set("api.model", self.model.text().strip() or "deepseek-flash")
        cfg.set("api.thinking", str(self.thinking.currentData() or "low"))
        cfg.set("api.stream", bool(self.stream.isChecked()))
        cfg.set("ui.width", int(self.width_spin.value()))
        cfg.set("ui.opacity", float(self.opacity_spin.value()))
        cfg.set("ui.show_reason", bool(self.show_reason.isChecked()))
        cfg.set("ui.click_through", bool(self.click_through.isChecked()))
        cfg.set("behavior.auto_mode", bool(self.auto_mode.isChecked()))
        cfg.set("behavior.poll_interval_ms", int(self.poll_spin.value()))
        cfg.set("behavior.use_cache", bool(self.use_cache.isChecked()))
        cfg.set("behavior.vote_low_confidence", bool(self.vote.isChecked()))
        cfg.set("hotkeys.capture", self.hk_capture.text().strip() or "F5")
        cfg.set("hotkeys.toggle", self.hk_toggle.text().strip() or "F6")
        cfg.set("hotkeys.pick", self.hk_pick.text().strip() or "F7")
        cfg.set("hotkeys.settings", self.hk_settings.text().strip() or "F8")
        cfg.save()

    def _on_save(self) -> None:
        self._collect()
        self.accept()

    def _on_test(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_result.setText("测试中…")
        self.test_result.setStyleSheet("color: #888;")
        try:
            self._collect()
            text = test_connection(self.cfg)
            self.test_result.setText(f"✓ 连接正常：{text}")
            self.test_result.setStyleSheet("color: #2f9e44;")
        except Exception as e:  # noqa: BLE001
            self.test_result.setText(f"✗ {type(e).__name__}: {e}")
            self.test_result.setStyleSheet("color: #d64545;")
        finally:
            self.test_btn.setEnabled(True)
