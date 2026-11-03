# -*- coding: utf-8 -*-
"""Preset list with import/export/delete actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.plotting.presets import BUILTIN_PRESETS, preset_label, preset_names
from cvanalysis.plotting.texts import DEFAULT_TEXT_PRESET_NAME
from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.dialogs.text_preset_dialog import TextPresetEditorDialog


class PresetManagerDialog(QDialog):
    def __init__(self, settings: SettingsService, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("预设管理")
        scale = max(1.0, min(1.6, self.font().pointSizeF() / 11.0))
        self.resize(int(720 * scale), int(560 * scale))
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_style_page(), "绘图预设")
        self.tabs.addTab(self._build_text_page(), "文本预设")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_style_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
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
        return page

    def _build_text_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "文本预设保存所有图的默认轴标签、标题、注释和固定图例文字；"
                "留空使用内置默认，输入空格表示空文字。"
            )
        )
        self.text_list = QListWidget()
        self.text_list.itemDoubleClicked.connect(lambda _item: self._edit_text_preset())
        layout.addWidget(self.text_list, 1)
        actions = QGridLayout()
        new_btn = QPushButton("新建文本预设...")
        new_btn.setProperty("secondary", True)
        new_btn.clicked.connect(self._new_text_preset)
        edit_btn = QPushButton("编辑选中...")
        edit_btn.setProperty("secondary", True)
        edit_btn.clicked.connect(self._edit_text_preset)
        active_btn = QPushButton("设为当前")
        active_btn.setProperty("secondary", True)
        active_btn.clicked.connect(self._set_active_text_preset)
        import_btn = QPushButton("导入...")
        import_btn.setProperty("secondary", True)
        import_btn.clicked.connect(self._import_text)
        export_btn = QPushButton("导出选中...")
        export_btn.setProperty("secondary", True)
        export_btn.clicked.connect(self._export_text)
        delete_btn = QPushButton("删除选中")
        delete_btn.setProperty("secondary", True)
        delete_btn.clicked.connect(self._delete_text)
        for index, button in enumerate(
            (new_btn, edit_btn, active_btn, import_btn, export_btn, delete_btn)
        ):
            actions.addWidget(button, index // 3, index % 3)
        layout.addLayout(actions)
        return page

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
        self._refresh_text_list()

    def _refresh_text_list(self) -> None:
        self.text_list.clear()
        active = self.settings.active_text_preset
        names = list(self.settings.text_presets)
        names.sort(key=lambda name: (name != DEFAULT_TEXT_PRESET_NAME, name))
        for name in names:
            entry = self.settings.text_presets.get(name, {})
            label = entry.get("label", name) if isinstance(entry, dict) else name
            suffix = "（默认）" if name == DEFAULT_TEXT_PRESET_NAME else "（自定义）"
            if name == active:
                suffix += "（当前）"
            item_text = f"{label} {suffix}"
            self.text_list.addItem(item_text)
            item = self.text_list.item(self.text_list.count() - 1)
            item.setData(Qt.UserRole, name)

    def _selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.text().split("::", 1)[-1]

    def _selected_text_name(self) -> str | None:
        item = self.text_list.currentItem()
        if item is None:
            return None
        name = item.data(Qt.UserRole)
        return str(name) if name else None

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

    def _new_text_preset(self) -> None:
        source = self._selected_text_name() or self.settings.active_text_preset
        base_name = f"{source}-copy" if source else "custom-text"
        dialog = TextPresetEditorDialog(
            self.settings,
            base_name,
            new_preset=True,
            source_name=source,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _edit_text_preset(self) -> None:
        name = self._selected_text_name()
        if not name:
            return
        dialog = TextPresetEditorDialog(self.settings, name, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh()

    def _set_active_text_preset(self) -> None:
        name = self._selected_text_name()
        if not name:
            return
        self.settings.set_active_text_preset(name)
        self._refresh()

    def _import_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入文本预设", "", "JSON (*.json)")
        if not path:
            return
        try:
            name = self.settings.import_text_preset(path)
            self._refresh()
            QMessageBox.information(self, "导入成功", f"文本预设已导入: {name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(exc))

    def _export_text(self) -> None:
        name = self._selected_text_name()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出文本预设",
            f"{name}-text.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.settings.export_text_preset(name, path)
            QMessageBox.information(self, "导出成功", path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _delete_text(self) -> None:
        name = self._selected_text_name()
        if not name:
            return
        if name == DEFAULT_TEXT_PRESET_NAME:
            QMessageBox.information(self, "提示", "默认文本预设不能删除，可在编辑器中恢复默认文字。")
            return
        if QMessageBox.question(self, "确认", f"删除文本预设 {name}？") == QMessageBox.Yes:
            self.settings.delete_text_preset(name)
            self._refresh()
