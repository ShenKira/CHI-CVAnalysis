# -*- coding: utf-8 -*-
"""Preset list with import/export/delete actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cvanalysis.plotting.presets import BUILTIN_PRESETS, preset_label, preset_names
from cvanalysis.services.settings_service import SettingsService


class PresetManagerDialog(QDialog):
    def __init__(self, settings: SettingsService, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("预设管理")
        scale = max(1.0, min(1.6, self.font().pointSizeF() / 11.0))
        self.resize(int(480 * scale), int(420 * scale))
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("内置预设只读；自定义预设可以导出、导入和删除。"))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        row = QHBoxLayout()
        import_btn = QPushButton("导入预设...")
        import_btn.setProperty("secondary", True)
        import_btn.clicked.connect(self._import)
        export_btn = QPushButton("导出选中...")
        export_btn.setProperty("secondary", True)
        export_btn.clicked.connect(self._export)
        delete_btn = QPushButton("删除选中")
        delete_btn.setProperty("secondary", True)
        delete_btn.clicked.connect(self._delete)
        row.addWidget(import_btn)
        row.addWidget(export_btn)
        row.addWidget(delete_btn)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh(self) -> None:
        self.list_widget.clear()
        user_presets = self.settings.user_presets
        for name in preset_names(user_presets):
            if name in user_presets and name in BUILTIN_PRESETS:
                suffix = "（用户覆盖）"
            elif name in BUILTIN_PRESETS:
                suffix = "（内置）"
            else:
                suffix = "（自定义）"
            self.list_widget.addItem(f"{preset_label(name, user_presets)} {suffix}::{name}")

    def _selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.text().split("::", 1)[-1]

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入预设", "", "JSON (*.json)")
        if not path:
            return
        try:
            name = self.settings.import_preset(path)
            self._refresh()
            QMessageBox.information(self, "导入成功", f"预设已导入: {name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(exc))

    def _export(self) -> None:
        name = self._selected_name()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出预设", f"{name}.json", "JSON (*.json)")
        if not path:
            return
        try:
            self.settings.export_preset(name, path)
            QMessageBox.information(self, "导出成功", path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        user_presets = self.settings.user_presets
        if name in BUILTIN_PRESETS and name not in user_presets:
            QMessageBox.information(self, "提示", "内置预设不能删除；如果存在同名用户覆盖，可先删除覆盖。")
            return
        if QMessageBox.question(self, "确认", f"删除预设 {name}？") == QMessageBox.Yes:
            self.settings.delete_preset(name)
            self._refresh()
