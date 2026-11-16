"""Editors for per-plot I-T horizontal reference lines."""
from __future__ import annotations

from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QScrollArea, QWidget,
)

from cvanalysis.plotting.it_references import new_reference_id
from cvanalysis.plotting.axis_limits import _unit_scale, unit_dimension
from cvanalysis.plotting.template_format import TemplateError, format_template
from cvanalysis.ui.layout import fit_dialog
from cvanalysis.ui.theme import apply_button_role, apply_theme_role
from cvanalysis.ui.widgets.inline_color_picker import InlineColorPicker
from cvanalysis.ui.widgets.formatted_text_preview import FormattedTextPreview


class ItReferenceSettingsDialog(QDialog):
    def __init__(self, unit, record=None, parent=None):
        super().__init__(parent)
        self.record = deepcopy(record or {})
        self.current_unit = deepcopy(unit)
        saved_unit = self.record.get("unit")
        self.input_unit = deepcopy(unit if saved_unit is None else saved_unit if isinstance(saved_unit, dict) else None)
        self.setWindowTitle("设置参考线" if record else "添加参考线")
        fit_dialog(self, 550, 520, min_width=440, min_height=380)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.value_edit = QLineEdit()
        if self.record.get("value") is not None:
            self.value_edit.setText(str(self.record["value"]))
        self.value_edit.setPlaceholderText("输入有限数值")
        form.addRow("Y 值", self.value_edit)
        self.unit_label = QLabel()
        self.unit_label.setWordWrap(True)
        form.addRow("输入单位", self.unit_label)
        self.use_current_button = QPushButton("使用当前 Y 轴单位")
        apply_button_role(self.use_current_button, "secondary")
        self.use_current_button.clicked.connect(self._use_current_unit)
        form.addRow(self.use_current_button)
        self.label_visible = QCheckBox("显示图内标签")
        self.label_visible.setChecked(self.record.get("label_visible", True) is not False)
        self.label_visible.setToolTip("关闭后不绘制图内标签；参考线和图例仍可独立显示。")
        form.addRow(self.label_visible)
        self.label_edit = QLineEdit(str(self.record.get("label") or ""))
        self.label_edit.setPlaceholderText("留空使用 I = 数值 单位")
        self.label_edit.setToolTip(r"支持 {value:.2f}、{unit}、$I_{ref}$ 和公式外的 \n 换行。数学花括号内插入变量可写 $I_{value:.2f}$。")
        form.addRow("图内标签", self.label_edit)
        self.label_position_mode = QComboBox()
        self.label_position_mode.addItem("自动排版", "auto")
        self.label_position_mode.addItem("手动指定", "manual")
        self.label_position_mode.setCurrentIndex(max(0, self.label_position_mode.findData(
            self.record.get("label_position_mode", "auto"))))
        form.addRow("标签位置", self.label_position_mode)
        saved_position = self.record.get("label_position", [75., 85.])
        if not isinstance(saved_position, (list, tuple)) or len(saved_position) != 2:
            saved_position = [75., 85.]
        self.label_x = QDoubleSpinBox()
        self.label_y = QDoubleSpinBox()
        for control, coordinate, fallback in zip((self.label_x, self.label_y), saved_position, (75., 85.)):
            control.setRange(0., 100.)
            control.setDecimals(1)
            control.setSuffix(" %")
            try:
                number = float(coordinate)
                control.setValue(number if math.isfinite(number) and 0 <= number <= 100 else fallback)
            except (TypeError, ValueError, OverflowError):
                control.setValue(fallback)
        self.label_x.setToolTip("图内标签中心的水平位置，0% 为左边界，100% 为右边界。")
        self.label_y.setToolTip("图内标签中心的垂直位置，0% 为下边界，100% 为上边界。")
        position_row = QWidget()
        position_layout = QHBoxLayout(position_row)
        position_layout.setContentsMargins(0, 0, 0, 0)
        position_layout.addWidget(QLabel("X"))
        position_layout.addWidget(self.label_x)
        position_layout.addWidget(QLabel("Y"))
        position_layout.addWidget(self.label_y)
        form.addRow("手动坐标", position_row)
        self.legend_mode = QComboBox()
        self.legend_mode.setToolTip("加入图例后，还需开启当前图的“显示图例”。")
        for label, mode in (("不加入图例", "hidden"), ("复用图内标签", "label"), ("自定义图例", "custom")):
            self.legend_mode.addItem(label, mode)
        self.legend_mode.setCurrentIndex(max(0, self.legend_mode.findData(self.record.get("legend_mode", "hidden"))))
        form.addRow("图例", self.legend_mode)
        self.legend_edit = QLineEdit(str(self.record.get("legend_label") or ""))
        self.legend_edit.setPlaceholderText("例如 阈值 {value:.2f} {unit}")
        self.legend_edit.setToolTip(r"支持数学公式 $...$、{value:.2f} 和公式外 \n 换行。")
        form.addRow("自定义图例", self.legend_edit)
        self.legend_mode.currentIndexChanged.connect(self._update_legend_mode)
        self.label_visible.toggled.connect(self._update_label_controls)
        self.label_position_mode.currentIndexChanged.connect(self._update_label_controls)
        self._update_legend_mode()
        self._update_label_controls()
        layout.addLayout(form)
        self.color_button = QPushButton("设置参考线颜色")
        apply_button_role(self.color_button, "secondary")
        self.color_button.setCheckable(True)
        layout.addWidget(self.color_button)
        self.color_picker = InlineColorPicker()
        saved_color = QColor(str(self.record.get("color") or "#666666"))
        self.color_picker.setCurrentColor(saved_color if saved_color.isValid() else QColor("#666666"))
        self.color_picker.currentColorChanged.connect(self._update_color_swatch)
        self._update_color_swatch(self.color_picker.currentColor())
        self.color_picker.hide()
        self.color_button.toggled.connect(self.color_picker.setVisible)
        layout.addWidget(self.color_picker)
        self.preview = FormattedTextPreview()
        apply_theme_role(self.preview, "hint")
        layout.addWidget(self.preview)
        self.error = QLabel()
        self.error.setTextFormat(Qt.PlainText)
        self.error.setWordWrap(True)
        apply_theme_role(self.error, "error")
        layout.addWidget(self.error)
        for edit in (self.value_edit, self.label_edit, self.legend_edit):
            edit.textChanged.connect(self._update_preview)
        self.legend_mode.currentIndexChanged.connect(self._update_preview)
        self.label_visible.toggled.connect(self._update_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        apply_button_role(buttons.button(QDialogButtonBox.Ok), "primary", pill=True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self._update_unit()
        self._update_preview()

    def _update_unit(self):
        label = str((self.input_unit or {}).get("label") or "未知")
        current = str((self.current_unit or {}).get("label") or "未知")
        self.unit_label.setText(f"{label}（当前 Y 轴：{current}）；兼容单位自动换算。")
        self.use_current_button.setEnabled(bool(self.current_unit) and self.current_unit != self.input_unit)

    def _update_color_swatch(self, color):
        swatch = QPixmap(18, 18)
        swatch.fill(color)
        self.color_button.setIcon(QIcon(swatch))
        self.color_button.setToolTip("参考线颜色：" + color.name(QColor.HexRgb))

    def _use_current_unit(self):
        if self.current_unit != self.input_unit:
            previous = self.input_unit or {}
            updated = self.current_unit or {}
            try:
                old_factor = float(previous.get("factor"))
                new_factor = float(updated.get("factor"))
                old_scale = _unit_scale(previous.get("label", ""))
                new_scale = _unit_scale(updated.get("label", ""))
                if (not old_scale or not new_scale or not math.isfinite(old_factor) or not math.isfinite(new_factor)
                        or not math.isclose(old_factor, old_scale, rel_tol=1e-9)
                        or not math.isclose(new_factor, new_scale, rel_tol=1e-9)
                        or previous.get("dimension") != updated.get("dimension")
                        or unit_dimension(previous.get("label", "")) != previous.get("dimension")
                        or unit_dimension(updated.get("label", "")) != updated.get("dimension")):
                    raise ValueError
                converted = float(self.value_edit.text()) * new_factor / old_factor
                if not math.isfinite(converted):
                    raise ValueError
                replacement = f"{converted:.15g}"
            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                replacement = ""
            self.input_unit = deepcopy(self.current_unit)
            self.value_edit.setText(replacement)
            self._update_unit()
            self._update_preview()

    def _update_legend_mode(self):
        self.legend_edit.setEnabled(self.legend_mode.currentData() == "custom")
        self._update_label_controls()

    def _update_label_controls(self, *_args):
        visible = self.label_visible.isChecked()
        self.label_edit.setEnabled(visible or self.legend_mode.currentData() == "label")
        self.label_position_mode.setEnabled(visible)
        manual = visible and self.label_position_mode.currentData() == "manual"
        self.label_x.setEnabled(manual)
        self.label_y.setEnabled(manual)

    def _validated_record(self):
        try:
            value = float(self.value_edit.text().strip())
        except ValueError:
            raise ValueError("请填写有效的 Y 值。") from None
        if not math.isfinite(value):
            raise ValueError("Y 值必须为有限数值。")
        if not self.input_unit or not self.input_unit.get("dimension"):
            raise ValueError("当前 Y 轴单位未知，请先绘制图表。")
        try:
            label = self.input_unit.get("label")
            factor = float(self.input_unit.get("factor"))
            expected = _unit_scale(label) if isinstance(label, str) else None
            if (expected is None or not math.isfinite(factor) or factor <= 0
                    or not math.isclose(factor, expected, rel_tol=1e-9)
                    or unit_dimension(label) != self.input_unit.get("dimension")):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValueError("参考线单位无效，请选择当前 Y 轴单位后重新填写。") from None
        context = {"value": value, "unit": str(self.input_unit.get("label") or "")}
        label = self.label_edit.text()
        legend = self.legend_edit.text()
        try:
            formatted = ""
            if self.label_visible.isChecked() or self.legend_mode.currentData() == "label":
                formatted = format_template(label or "I = {value:.4g} {unit}", context, strict=True)
            if self.legend_mode.currentData() == "custom":
                if not legend.strip():
                    raise ValueError("请填写自定义图例文字。")
                format_template(legend, context, strict=True)
        except TemplateError as exc:
            raise ValueError("图注格式无效：" + str(exc)) from exc
        record = deepcopy(self.record)
        record.update(id=record.get("id") or new_reference_id(), value=value,
                      unit=deepcopy(self.input_unit), label=label,
                      color=self.color_picker.currentColor().name(QColor.HexRgb),
                      legend_mode=self.legend_mode.currentData(), legend_label=legend,
                      label_visible=self.label_visible.isChecked(),
                      label_position_mode=self.label_position_mode.currentData(),
                      label_position=[self.label_x.value(), self.label_y.value()])
        return record, formatted

    def _update_preview(self, *_args):
        try:
            _, formatted = self._validated_record()
        except ValueError:
            self.preview.show_preview("图注可用 {value:.2f} 和 {unit}；默认不加入图例。")
            return
        self.error.clear()
        self.preview.show_preview(("图注预览：" + formatted) if self.label_visible.isChecked()
                             else ("图内标签已关闭；图例可独立显示。"))

    def accept(self):
        try:
            self.record, _ = self._validated_record()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        super().accept()


class ItReferenceManagerDialog(QDialog):
    def __init__(self, records, unit, selected_id=None, parent=None):
        super().__init__(parent)
        self.records = deepcopy(records)
        self.unit = deepcopy(unit)
        self.setWindowTitle("管理 I-T 参考线")
        fit_dialog(self, 780, 480, min_width=560, min_height=360)
        layout = QVBoxLayout(self)
        info = QLabel("双击表格中的参考线可修改；仅在点击确定后应用。")
        info.setWordWrap(True)
        apply_theme_role(info, "hint")
        layout.addWidget(info)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Y 值", "单位", "图内标签", "颜色", "图例"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for title, action in (("添加…", self.add_reference), ("修改…", self.edit_selected), ("删除", self.delete_selected)):
            button = QPushButton(title)
            apply_button_role(button, "secondary")
            button.clicked.connect(action)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        apply_button_role(buttons.button(QDialogButtonBox.Ok), "primary", pill=True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh(selected_id)

    def _refresh(self, selected_id=None):
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            unit = record.get("unit") if isinstance(record.get("unit"), dict) else {}
            mode = {"hidden": "不加入", "label": "复用标签", "custom": "自定义"}.get(record.get("legend_mode"), "不加入")
            label = record.get("label") or "自动图注"
            if record.get("label_visible", True) is False:
                label = "已关闭（" + str(label) + "）"
            for col, value in enumerate((record.get("value", ""), unit.get("label", ""),
                                         label, record.get("color", "#666666"), mode)):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
            if str(record.get("id", "")) == selected_id:
                self.table.selectRow(row)
        if self.records and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def add_reference(self):
        dialog = ItReferenceSettingsDialog(self.unit, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.records.append(dialog.record)
            self._refresh(dialog.record["id"])

    def edit_selected(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
            return
        dialog = ItReferenceSettingsDialog(self.unit, self.records[row], self)
        if dialog.exec() == QDialog.Accepted:
            self.records[row] = dialog.record
            self._refresh(dialog.record["id"])

    def delete_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            del self.records[row]
            self._refresh()
