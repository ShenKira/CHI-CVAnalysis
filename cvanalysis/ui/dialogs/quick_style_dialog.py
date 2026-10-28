# -*- coding: utf-8 -*-
"""Compact per-plot style editor shown after selecting a non-default preset."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from cvanalysis.plotting.style import PlotStyle, canvas_size_for_ratio


ASPECT_RATIOS = {
    "auto": 0.0,
    "1:1": 1.0,
    "4:3": 4.0 / 3.0,
    "16:9": 16.0 / 9.0,
}


class QuickStyleDialog(QDialog):
    """Quick editor with explicit apply and save actions.

    ``apply_requested`` changes the current plot only. ``save_requested`` is
    handled by MainWindow, which asks whether to overwrite or save a new preset.
    """

    apply_requested = Signal(dict)
    save_requested = Signal(dict)

    def __init__(self, style: PlotStyle, preset_name: str, parent=None):
        super().__init__(parent)
        self.style = style
        self.setWindowTitle(f"快速绘图参数 — {preset_name}")
        self.resize(520, 680)
        self._syncing = False
        self._build_ui()
        self._load_style(style)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "“应用”只修改当前图；“保存到配置”会先应用，再询问覆盖当前预设或另存为新预设。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #546e7a;")
        layout.addWidget(hint)

        ratio_group = QGroupBox("版式与比例")
        ratio_form = QFormLayout(ratio_group)
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("自动（跟随预设）", "auto")
        self.aspect_combo.addItem("1:1", "1:1")
        self.aspect_combo.addItem("4:3", "4:3")
        self.aspect_combo.addItem("16:9", "16:9")
        ratio_form.addRow("坐标区比例:", self.aspect_combo)
        self.sync_export_cb = QCheckBox("同步导出画布比例（统一高度，按比例计算宽度）")
        self.sync_export_cb.setChecked(False)
        ratio_form.addRow(self.sync_export_cb)
        layout.addWidget(ratio_group)

        font_group = QGroupBox("字体")
        font_form = QFormLayout(font_group)
        self.font_family_edit = QLineEdit()
        font_form.addRow("字体族（逗号分隔）:", self.font_family_edit)

        self.sync_xy_cb = QCheckBox("X/Y 轴标签使用相同字号")
        self.sync_xy_cb.setChecked(True)
        self.sync_xy_cb.stateChanged.connect(self._on_sync_xy_changed)
        font_form.addRow(self.sync_xy_cb)

        self.xlabel_size_spin = self._spin(4.0, 48.0, 12.0)
        self.xlabel_size_spin.valueChanged.connect(self._on_xlabel_size_changed)
        font_form.addRow("X 轴标签字号:", self.xlabel_size_spin)
        self.ylabel_size_spin = self._spin(4.0, 48.0, 12.0)
        font_form.addRow("Y 轴标签字号:", self.ylabel_size_spin)

        self.xlabel_bold_cb = QCheckBox("X 轴标签加粗")
        self.ylabel_bold_cb = QCheckBox("Y 轴标签加粗")
        bold_row = QHBoxLayout()
        bold_row.addWidget(self.xlabel_bold_cb)
        bold_row.addWidget(self.ylabel_bold_cb)
        bold_row.addStretch()
        font_form.addRow("轴标签字重:", bold_row)

        self.title_size_spin = self._spin(4.0, 48.0, 12.0)
        font_form.addRow("标题字号:", self.title_size_spin)
        self.tick_size_spin = self._spin(4.0, 48.0, 12.0)
        font_form.addRow("刻度字号:", self.tick_size_spin)
        self.legend_size_spin = self._spin(4.0, 48.0, 12.0)
        font_form.addRow("图例字号:", self.legend_size_spin)
        self.annotation_size_spin = self._spin(4.0, 48.0, 12.0)
        font_form.addRow("注释字号:", self.annotation_size_spin)

        unify_btn = QPushButton("一键统一字号为 X 轴标签字号")
        unify_btn.setProperty("secondary", True)
        unify_btn.clicked.connect(self._unify_font_sizes)
        font_form.addRow(unify_btn)
        layout.addWidget(font_group)

        line_group = QGroupBox("线条与显示")
        line_form = QFormLayout(line_group)
        self.line_width_spin = self._spin(0.2, 10.0, 2.0, step=0.1, decimals=2)
        line_form.addRow("曲线线宽:", self.line_width_spin)
        self.axes_width_spin = self._spin(0.2, 10.0, 1.0, step=0.1, decimals=2)
        line_form.addRow("坐标轴线宽:", self.axes_width_spin)
        self.tick_width_spin = self._spin(0.2, 10.0, 1.0, step=0.1, decimals=2)
        line_form.addRow("刻度线宽:", self.tick_width_spin)

        self.legend_cb = QCheckBox("显示图例")
        line_form.addRow(self.legend_cb)
        self.annotation_cb = QCheckBox("显示统计注释")
        line_form.addRow(self.annotation_cb)
        self.grid_cb = QCheckBox("显示网格")
        line_form.addRow(self.grid_cb)
        self.minor_cb = QCheckBox("显示次要刻度")
        line_form.addRow(self.minor_cb)
        self.spines_cb = QCheckBox("显示上/右边框")
        line_form.addRow(self.spines_cb)
        self.ticks_top_cb = QCheckBox("上边框刻度")
        self.ticks_top_cb.setToolTip("上边框可见时，是否显示顶部刻度线；不影响刻度文字")
        line_form.addRow(self.ticks_top_cb)
        self.ticks_right_cb = QCheckBox("右边框刻度")
        self.ticks_right_cb.setToolTip("右边框可见时，是否显示右侧刻度线；不影响刻度文字")
        line_form.addRow(self.ticks_right_cb)
        self.spines_cb.stateChanged.connect(self._update_tick_enabled)
        self.legend_frame_cb = QCheckBox("图例边框")
        line_form.addRow(self.legend_frame_cb)
        layout.addWidget(line_group)

        buttons = QHBoxLayout()
        reset_btn = QPushButton("还原当前预设")
        reset_btn.setProperty("secondary", True)
        reset_btn.clicked.connect(self._reset_to_base)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        apply_btn = QPushButton("应用（当前图）")
        apply_btn.clicked.connect(lambda: self.apply_requested.emit(self.overrides()))
        buttons.addWidget(apply_btn)
        save_btn = QPushButton("保存到配置...")
        save_btn.clicked.connect(lambda: self.save_requested.emit(self.overrides()))
        buttons.addWidget(save_btn)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("secondary", True)
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, *, step: float = 1.0, decimals: int = 1) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setValue(value)
        return spin

    def set_plot_flags(self, show_legend: bool, show_annotations: bool) -> None:
        self.legend_cb.setChecked(bool(show_legend) and self.style.legend)
        self.annotation_cb.setChecked(bool(show_annotations) and self.style.annotation)

    def _load_style(self, style: PlotStyle) -> None:
        self._syncing = True
        try:
            self.font_family_edit.setText(", ".join(style.font_family))
            self.aspect_combo.setCurrentIndex(max(0, self.aspect_combo.findData(style.axes_aspect)))
            self.sync_export_cb.setChecked(False)
            same_xy = (
                abs(style.effective_xlabel_size() - style.effective_ylabel_size()) < 1e-9
                and style.effective_xlabel_bold() == style.effective_ylabel_bold()
            )
            self.sync_xy_cb.setChecked(same_xy)
            self.xlabel_size_spin.setValue(style.effective_xlabel_size())
            self.ylabel_size_spin.setValue(style.effective_ylabel_size())
            self.xlabel_bold_cb.setChecked(style.effective_xlabel_bold())
            self.ylabel_bold_cb.setChecked(style.effective_ylabel_bold())
            self.title_size_spin.setValue(style.title_size)
            self.tick_size_spin.setValue(style.tick_size)
            self.legend_size_spin.setValue(style.legend_size)
            self.annotation_size_spin.setValue(style.annotation_size)
            self.line_width_spin.setValue(style.line_width)
            self.axes_width_spin.setValue(style.axes_linewidth)
            self.tick_width_spin.setValue(style.tick_width)
            self.legend_cb.setChecked(style.legend)
            self.annotation_cb.setChecked(style.annotation)
            self.grid_cb.setChecked(style.grid)
            self.minor_cb.setChecked(style.minor_ticks)
            self.spines_cb.setChecked(style.spines_top and style.spines_right)
            self.ticks_top_cb.setChecked(style.ticks_top)
            self.ticks_right_cb.setChecked(style.ticks_right)
            self.legend_frame_cb.setChecked(style.legend_frame)
        finally:
            self._syncing = False
        self._update_xy_enabled()
        self._update_tick_enabled()

    def _on_sync_xy_changed(self, *args) -> None:
        if self.sync_xy_cb.isChecked():
            self._syncing = True
            try:
                self.ylabel_size_spin.setValue(self.xlabel_size_spin.value())
                self.ylabel_bold_cb.setChecked(self.xlabel_bold_cb.isChecked())
            finally:
                self._syncing = False
        self._update_xy_enabled()

    def _update_xy_enabled(self) -> None:
        synced = self.sync_xy_cb.isChecked()
        self.ylabel_size_spin.setEnabled(not synced)
        self.ylabel_bold_cb.setEnabled(not synced)

    def _update_tick_enabled(self, *args) -> None:
        enabled = self.spines_cb.isChecked()
        self.ticks_top_cb.setEnabled(enabled)
        self.ticks_right_cb.setEnabled(enabled)

    def _on_xlabel_size_changed(self, value: float) -> None:
        if self._syncing or not self.sync_xy_cb.isChecked():
            return
        self._syncing = True
        try:
            self.ylabel_size_spin.setValue(value)
        finally:
            self._syncing = False

    def _unify_font_sizes(self) -> None:
        value = self.xlabel_size_spin.value()
        self._syncing = True
        try:
            self.ylabel_size_spin.setValue(value)
            self.title_size_spin.setValue(value)
            self.tick_size_spin.setValue(value)
            self.legend_size_spin.setValue(value)
            self.annotation_size_spin.setValue(value)
            self.ylabel_bold_cb.setChecked(self.xlabel_bold_cb.isChecked())
        finally:
            self._syncing = False

    def _reset_to_base(self) -> None:
        self._load_style(self.style)

    def overrides(self) -> dict:
        families = tuple(
            family.strip()
            for family in self.font_family_edit.text().split(",")
            if family.strip()
        )
        x_size = self.xlabel_size_spin.value()
        y_size = x_size if self.sync_xy_cb.isChecked() else self.ylabel_size_spin.value()
        x_bold = self.xlabel_bold_cb.isChecked()
        y_bold = x_bold if self.sync_xy_cb.isChecked() else self.ylabel_bold_cb.isChecked()
        aspect = self.aspect_combo.currentData() or "auto"
        overrides = {
            "font_family": families or self.style.font_family,
            "xlabel_size": x_size,
            "ylabel_size": y_size,
            "xlabel_bold": x_bold,
            "ylabel_bold": y_bold,
            "title_size": self.title_size_spin.value(),
            "tick_size": self.tick_size_spin.value(),
            "legend_size": self.legend_size_spin.value(),
            "annotation_size": self.annotation_size_spin.value(),
            "line_width": self.line_width_spin.value(),
            "axes_linewidth": self.axes_width_spin.value(),
            "tick_width": self.tick_width_spin.value(),
            "legend": self.legend_cb.isChecked(),
            "annotation": self.annotation_cb.isChecked(),
            "grid": self.grid_cb.isChecked(),
            "minor_ticks": self.minor_cb.isChecked(),
            "spines_top": self.spines_cb.isChecked(),
            "spines_right": self.spines_cb.isChecked(),
            "ticks_top": self.ticks_top_cb.isChecked(),
            "ticks_right": self.ticks_right_cb.isChecked(),
            "legend_frame": self.legend_frame_cb.isChecked(),
            "axes_aspect": aspect,
        }
        ratio = ASPECT_RATIOS.get(aspect, 0.0)
        if self.sync_export_cb.isChecked() and ratio > 0:
            overrides["figure_size"] = canvas_size_for_ratio(ratio)
        return overrides
