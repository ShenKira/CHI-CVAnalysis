# -*- coding: utf-8 -*-
"""Compact plot-style editor for user presets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from cvanalysis.plotting.style import CANVAS_HEIGHT_IN, PlotStyle


class StyleEditorDialog(QDialog):
    def __init__(self, style: PlotStyle, parent=None):
        super().__init__(parent)
        self.style = style
        self.setWindowTitle("编辑当前绘图样式")
        scale = max(1.0, min(1.6, self.font().pointSizeF() / 11.0))
        self.resize(int(520 * scale), int(700 * scale))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        group = QGroupBox("版式与字体")
        form = QFormLayout(group)
        canvas_size = QLabel(
            f"统一高度 {CANVAS_HEIGHT_IN:g} in；宽度按画布比例计算"
        )
        form.addRow("导出画布:", canvas_size)
        self.save_dpi_spin = QSpinBox()
        self.save_dpi_spin.setRange(72, 1200)
        self.save_dpi_spin.setSingleStep(50)
        self.save_dpi_spin.setValue(self.style.save_dpi)
        self.save_dpi_spin.setToolTip("作为 PNG/TIFF 默认 DPI；PDF/SVG 中只影响栅格化图层")
        form.addRow("默认 PNG/TIFF DPI:", self.save_dpi_spin)
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(4.0, 48.0)
        self.font_size_spin.setDecimals(1)
        self.font_size_spin.setValue(self.style.font_size)
        form.addRow("基础字号:", self.font_size_spin)
        self.label_size_spin = QDoubleSpinBox()
        self.label_size_spin.setRange(4.0, 48.0)
        self.label_size_spin.setDecimals(1)
        self.label_size_spin.setValue(self.style.label_size)
        form.addRow("轴标签字号:", self.label_size_spin)
        self.tick_size_spin = QDoubleSpinBox()
        self.tick_size_spin.setRange(4.0, 48.0)
        self.tick_size_spin.setDecimals(1)
        self.tick_size_spin.setValue(self.style.tick_size)
        form.addRow("刻度字号:", self.tick_size_spin)
        self.legend_size_spin = QDoubleSpinBox()
        self.legend_size_spin.setRange(4.0, 48.0)
        self.legend_size_spin.setDecimals(1)
        self.legend_size_spin.setValue(self.style.legend_size)
        form.addRow("图例字号:", self.legend_size_spin)
        self.font_family_edit = QLineEdit(", ".join(self.style.font_family))
        form.addRow("字体族（逗号分隔）:", self.font_family_edit)
        layout.addWidget(group)

        lines = QGroupBox("线条与坐标轴")
        line_form = QFormLayout(lines)
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(0.2, 10.0)
        self.line_width_spin.setSingleStep(0.1)
        self.line_width_spin.setDecimals(2)
        self.line_width_spin.setValue(self.style.line_width)
        line_form.addRow("曲线线宽:", self.line_width_spin)
        self.axes_width_spin = QDoubleSpinBox()
        self.axes_width_spin.setRange(0.2, 10.0)
        self.axes_width_spin.setSingleStep(0.1)
        self.axes_width_spin.setDecimals(2)
        self.axes_width_spin.setValue(self.style.axes_linewidth)
        line_form.addRow("坐标轴线宽:", self.axes_width_spin)
        self.grid_cb = QCheckBox("显示网格")
        self.grid_cb.setChecked(self.style.grid)
        line_form.addRow(self.grid_cb)
        self.minor_cb = QCheckBox("显示次要刻度")
        self.minor_cb.setChecked(self.style.minor_ticks)
        line_form.addRow(self.minor_cb)
        self.top_right_cb = QCheckBox("显示上/右边框")
        self.top_right_cb.setChecked(self.style.spines_top and self.style.spines_right)
        line_form.addRow(self.top_right_cb)
        self.ticks_top_cb = QCheckBox("上边框刻度")
        self.ticks_top_cb.setChecked(self.style.ticks_top)
        self.ticks_top_cb.setToolTip("上边框可见时，是否显示顶部刻度线；不影响刻度文字")
        line_form.addRow(self.ticks_top_cb)
        self.ticks_right_cb = QCheckBox("右边框刻度")
        self.ticks_right_cb.setChecked(self.style.ticks_right)
        self.ticks_right_cb.setToolTip("右边框可见时，是否显示右侧刻度线；不影响刻度文字")
        line_form.addRow(self.ticks_right_cb)
        self.top_right_cb.toggled.connect(self.ticks_top_cb.setEnabled)
        self.top_right_cb.toggled.connect(self.ticks_right_cb.setEnabled)
        self.ticks_top_cb.setEnabled(self.top_right_cb.isChecked())
        self.ticks_right_cb.setEnabled(self.top_right_cb.isChecked())
        self.legend_frame_cb = QCheckBox("图例边框")
        self.legend_frame_cb.setChecked(self.style.legend_frame)
        line_form.addRow(self.legend_frame_cb)
        self.annotation_cb = QCheckBox("显示统计注释")
        self.annotation_cb.setChecked(self.style.annotation)
        line_form.addRow(self.annotation_cb)
        layout.addWidget(lines)

        colors = QGroupBox("颜色序列")
        color_form = QFormLayout(colors)
        self.colors_edit = QLineEdit(", ".join(self.style.color_cycle))
        color_form.addRow("逗号分隔的十六进制颜色:", self.colors_edit)
        layout.addWidget(colors)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def edited_style(self) -> PlotStyle:
        from matplotlib.colors import is_color_like

        colors = tuple(
            color.strip()
            for color in self.colors_edit.text().split(",")
            if color.strip() and is_color_like(color.strip())
        )
        font_family = tuple(font.strip() for font in self.font_family_edit.text().split(",") if font.strip())
        overrides = {
            "save_dpi": self.save_dpi_spin.value(),
            "font_size": self.font_size_spin.value(),
            "label_size": self.label_size_spin.value(),
            "tick_size": self.tick_size_spin.value(),
            "legend_size": self.legend_size_spin.value(),
            "line_width": self.line_width_spin.value(),
            "axes_linewidth": self.axes_width_spin.value(),
            "grid": self.grid_cb.isChecked(),
            "minor_ticks": self.minor_cb.isChecked(),
            "spines_top": self.top_right_cb.isChecked(),
            "spines_right": self.top_right_cb.isChecked(),
            "ticks_top": self.ticks_top_cb.isChecked(),
            "ticks_right": self.ticks_right_cb.isChecked(),
            "legend_frame": self.legend_frame_cb.isChecked(),
            "annotation": self.annotation_cb.isChecked(),
            "color_cycle": colors or self.style.color_cycle,
            "font_family": font_family or self.style.font_family,
        }
        return self.style.with_overrides(overrides)
