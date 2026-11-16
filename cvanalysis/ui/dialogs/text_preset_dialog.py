# -*- coding: utf-8 -*-
"""Editor for configurable in-plot text presets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.plotting.texts import (
    DEFAULT_TEXTS,
    DEFAULT_TEXT_PRESET_NAME,
    TEXT_CATEGORIES,
    TextField,
    category_fields,
    preview_text_template,
    validate_text_template,
)
from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.layout import fit_dialog
from cvanalysis.ui.theme import apply_button_role, apply_theme_role
from cvanalysis.ui.widgets.formatted_text_preview import FormattedTextPreview


_CATEGORY_LABELS = {
    "axis": "轴标签",
    "title": "标题",
    "annotation": "注释",
    "legend": "图例固定文字",
}


class TextPresetEditorDialog(QDialog):
    def __init__(
        self,
        settings: SettingsService,
        preset_name: str,
        *,
        new_preset: bool = False,
        source_name: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.preset_name = preset_name
        self.new_preset = new_preset
        self.source_name = source_name or preset_name
        self.edits: dict[str, QLineEdit] = {}
        self.saved_name = preset_name
        self.setWindowTitle("新建文本预设" if new_preset else "编辑文本预设")
        fit_dialog(self, 760, 780, min_width=520, min_height=460)
        self._build_ui()

    def _initial_values(self) -> dict[str, str]:
        if self.new_preset:
            return self.settings.resolve_text_preset(self.source_name)
        return self.settings.resolve_text_preset(self.preset_name)

    def _initial_label(self) -> str:
        entry = self.settings.text_presets.get(self.preset_name)
        if isinstance(entry, dict):
            return str(entry.get("label", self.preset_name))
        if self.new_preset:
            return self.preset_name
        return self.preset_name

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            "文本预设用于所有图的默认图内文字。留空表示使用内置默认；"
            "输入空格表示空文字。数值可使用 {value:.2f}、{value:.4g}；末尾零会保留。"
            "支持 f/e/g 格式，精度最多 12 位，不支持运算表达式。"
            "支持 Matplotlib mathtext，如 $v^{-1/2}$。"
            r" 公式外可输入 \n 换行；数学分组包含变量时可写 $I_{value:.2f}$。"
        )
        info.setWordWrap(True)
        apply_theme_role(info, "muted")
        layout.addWidget(info)
        self.format_preview = FormattedTextPreview()
        self.format_preview.show_preview("编辑变量模板时显示格式示例。")
        apply_theme_role(self.format_preview, "hint")
        layout.addWidget(self.format_preview)

        top = QFormLayout()
        self.name_edit = QLineEdit(self.preset_name)
        self.name_edit.setReadOnly(not self.new_preset)
        top.addRow("预设名称:", self.name_edit)
        self.label_edit = QLineEdit(self._initial_label())
        top.addRow("显示名称:", self.label_edit)
        self.activate_cb = QCheckBox("保存后设为当前文本预设")
        self.activate_cb.setChecked(self.new_preset)
        top.addRow(self.activate_cb)
        layout.addLayout(top)

        values = self._initial_values()
        self.tabs = QTabWidget()
        for category in TEXT_CATEGORIES:
            self.tabs.addTab(
                self._build_category_page(category, values),
                _CATEGORY_LABELS.get(category, category),
            )
        layout.addWidget(self.tabs, 1)

        if self.preset_name == DEFAULT_TEXT_PRESET_NAME and not self.new_preset:
            reset_btn = QPushButton("恢复内置默认文字")
            reset_btn.setProperty("secondary", True)
            reset_btn.clicked.connect(self._reset_defaults)
            layout.addWidget(reset_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setText("确定")
            ok_button.setDefault(True)
            apply_button_role(ok_button, "primary", pill=True)
        if cancel_button is not None:
            cancel_button.setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_category_page(self, category: str, values: dict[str, str]) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(8)
        groups: dict[str, list[TextField]] = {}
        for field in category_fields(category):
            groups.setdefault(field.group, []).append(field)
        for group_name, fields in groups.items():
            group = QGroupBox(group_name)
            form = QFormLayout(group)
            form.setContentsMargins(9, 24, 9, 9)
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(7)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            for field in fields:
                edit = QLineEdit(values.get(field.key, ""))
                if not edit.text() and field.default:
                    edit.setPlaceholderText(field.default)
                if field.placeholders:
                    placeholders = ", ".join("{" + name + "}" for name in field.placeholders)
                    edit.setToolTip(f"可用占位符: {placeholders}\n留空使用内置默认文字。")
                else:
                    edit.setToolTip("留空使用内置默认文字；输入空格表示空文字。")
                self.edits[field.key] = edit
                if field.placeholders:
                    edit.textChanged.connect(lambda text, key=field.key: self._preview_format(key, text))
                form.addRow(field.label + ":", edit)
            page_layout.addWidget(group)
        page_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _preview_format(self, key: str, text: str) -> None:
        try:
            preview = preview_text_template(key, text)
        except ValueError as exc:
            apply_theme_role(self.format_preview, "error")
            self.format_preview.show_preview(f"格式无效：{exc}")
            return
        apply_theme_role(self.format_preview, "hint")
        self.format_preview.show_preview("格式示例：" + preview if preview else "留空使用内置默认文字。")

    def _reset_defaults(self) -> None:
        for key, edit in self.edits.items():
            edit.setText(DEFAULT_TEXTS.get(key, ""))

    def _accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "名称无效", "文本预设名称不能为空。")
            return
        if self.new_preset and name == DEFAULT_TEXT_PRESET_NAME:
            QMessageBox.warning(self, "名称无效", "default 是内置文本预设的保留名称。")
            return
        if self.new_preset and name in self.settings.text_presets:
            answer = QMessageBox.question(
                self,
                "确认覆盖",
                f"文本预设“{name}”已存在，是否覆盖？",
            )
            if answer != QMessageBox.Yes:
                return
        values = {key: edit.text() for key, edit in self.edits.items()}
        for key, value in values.items():
            valid, message = validate_text_template(key, value)
            if not valid:
                QMessageBox.warning(
                    self,
                    "文本格式无效",
                    f"{key} 的格式无效：{message}\n\n请检查数字格式或花括号。",
                )
                return
        label = self.label_edit.text().strip() or name
        self.settings.save_text_preset(name, values, label)
        if self.activate_cb.isChecked():
            self.settings.set_active_text_preset(name)
        self.saved_name = name
        self.accept()
