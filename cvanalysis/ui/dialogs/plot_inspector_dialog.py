# -*- coding: utf-8 -*-
"""Per-plot color and element inspector opened from the canvas context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.ui.widgets.plot_color_panel import PlotColorPanel


class PlotInspectorDialog(QDialog):
    """Edit the current plot only; changes are applied live and saved by the caller."""

    changed = Signal()

    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self._loading = True
        self.setWindowTitle(f"当前图设置 - {tab.spec.label}")
        self.resize(620, 720)
        self._build_ui()
        self._loading = False

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.color_panel = PlotColorPanel()
        self.color_panel.bind(self.tab)
        self.color_panel.changed.connect(self.changed.emit)
        self.tabs.addTab(self.color_panel, "颜色")

        self.element_page = QWidget()
        element_layout = QVBoxLayout(self.element_page)
        element_layout.setContentsMargins(8, 8, 8, 8)
        element_layout.setSpacing(8)
        self._build_element_controls(element_layout)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.element_page)
        self.tabs.addTab(scroll, "元素与样式")

        info = QLabel("当前页只修改本图；点击关闭后可直接 Ctrl+S 保存到项目。")
        info.setWordWrap(True)
        info.setStyleSheet("color: #607d8b;")
        layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(90)
        self._apply_timer.timeout.connect(self._apply)

    @staticmethod
    def _option_float(options: dict, key: str, default: float) -> float:
        try:
            value = float(options.get(key, default))
        except (TypeError, ValueError):
            return default
        return value

    def _spin(self, value: float, low: float, high: float, step: float = 0.1) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    def _build_element_controls(self, layout: QVBoxLayout) -> None:
        tab = self.tab
        style = tab.base_style.with_overrides(tab.spec.overrides)
        options = tab.spec.analysis_options

        display = QGroupBox("显示")
        display_form = QFormLayout(display)
        self.title_edit = QLineEdit(tab.spec.title)
        display_form.addRow("标题文字:", self.title_edit)
        self.show_title_cb = QCheckBox("显示标题")
        self.show_title_cb.setChecked(style.show_title)
        display_form.addRow(self.show_title_cb)
        self.show_legend_cb = QCheckBox("显示图例")
        self.show_legend_cb.setChecked(tab.spec.show_legend and style.legend)
        display_form.addRow(self.show_legend_cb)
        self.show_axes_cb = QCheckBox("显示坐标轴文字")
        self.show_axes_cb.setChecked(tab.spec.show_axes)
        display_form.addRow(self.show_axes_cb)
        self.annotations_cb = QCheckBox("显示分析注释")
        self.annotations_cb.setChecked(tab.spec.annotations and style.annotation)
        display_form.addRow(self.annotations_cb)
        self.grid_cb = QCheckBox("显示网格")
        self.grid_cb.setChecked(style.grid)
        display_form.addRow(self.grid_cb)
        self.minor_ticks_cb = QCheckBox("显示次要刻度")
        self.minor_ticks_cb.setChecked(style.minor_ticks)
        display_form.addRow(self.minor_ticks_cb)
        self.spines_cb = QCheckBox("显示上/右边框")
        self.spines_cb.setChecked(style.spines_top and style.spines_right)
        display_form.addRow(self.spines_cb)
        self.ticks_top_cb = QCheckBox("上边框刻度")
        self.ticks_top_cb.setChecked(style.ticks_top)
        self.ticks_top_cb.setToolTip("上边框可见时，是否显示顶部刻度线；不影响刻度文字")
        display_form.addRow(self.ticks_top_cb)
        self.ticks_right_cb = QCheckBox("右边框刻度")
        self.ticks_right_cb.setChecked(style.ticks_right)
        self.ticks_right_cb.setToolTip("右边框可见时，是否显示右侧刻度线；不影响刻度文字")
        display_form.addRow(self.ticks_right_cb)
        self.spines_cb.toggled.connect(self.ticks_top_cb.setEnabled)
        self.spines_cb.toggled.connect(self.ticks_right_cb.setEnabled)
        self.ticks_top_cb.setEnabled(self.spines_cb.isChecked())
        self.ticks_right_cb.setEnabled(self.spines_cb.isChecked())
        layout.addWidget(display)

        fonts = QGroupBox("字体")
        font_form = QFormLayout(fonts)
        self.title_size_spin = self._spin(style.title_size, 4, 48, 0.5)
        self.label_size_spin = self._spin(style.label_size, 4, 48, 0.5)
        self.tick_size_spin = self._spin(style.tick_size, 4, 48, 0.5)
        self.legend_size_spin = self._spin(style.legend_size, 4, 48, 0.5)
        self.annotation_size_spin = self._spin(style.annotation_size, 4, 48, 0.5)
        font_form.addRow("标题字号:", self.title_size_spin)
        font_form.addRow("轴标签字号:", self.label_size_spin)
        font_form.addRow("刻度字号:", self.tick_size_spin)
        font_form.addRow("图例字号:", self.legend_size_spin)
        font_form.addRow("注释字号:", self.annotation_size_spin)
        self.title_bold_cb = QCheckBox("标题加粗")
        self.title_bold_cb.setChecked(style.title_bold)
        self.label_bold_cb = QCheckBox("轴标签加粗")
        self.label_bold_cb.setChecked(style.label_bold)
        self.annotation_bold_cb = QCheckBox("注释加粗")
        self.annotation_bold_cb.setChecked(style.annotation_bold)
        font_form.addRow(self.title_bold_cb)
        font_form.addRow(self.label_bold_cb)
        font_form.addRow(self.annotation_bold_cb)
        layout.addWidget(fonts)

        lines = QGroupBox("线条与图例")
        line_form = QFormLayout(lines)
        self.line_width_spin = self._spin(style.line_width, 0.2, 10, 0.1)
        self.marker_size_spin = self._spin(style.marker_size, 1, 30, 0.5)
        line_form.addRow("曲线线宽:", self.line_width_spin)
        line_form.addRow("点大小:", self.marker_size_spin)
        self.legend_columns_spin = QSpinBox()
        self.legend_columns_spin.setRange(1, 8)
        self.legend_columns_spin.setValue(max(1, int(style.legend_columns)))
        line_form.addRow("图例列数:", self.legend_columns_spin)
        self.legend_location = QComboBox()
        for label, value in (
            ("自动", "best"),
            ("右上", "upper right"),
            ("左上", "upper left"),
            ("右下", "lower right"),
            ("左下", "lower left"),
            ("上中", "upper center"),
            ("下中", "lower center"),
            ("中左", "center left"),
            ("中右", "center right"),
            ("居中", "center"),
        ):
            self.legend_location.addItem(label, value)
        index = self.legend_location.findData(style.legend_location)
        self.legend_location.setCurrentIndex(max(0, index))
        line_form.addRow("图例位置:", self.legend_location)
        self.legend_frame_cb = QCheckBox("图例边框")
        self.legend_frame_cb.setChecked(style.legend_frame)
        line_form.addRow(self.legend_frame_cb)
        layout.addWidget(lines)

        kind = tab.spec.kind
        if kind == "cv_contribution_vs_rate":
            graph = QGroupBox("柱状图元素")
            graph_form = QFormLayout(graph)
            self.bar_width_spin = self._spin(
                self._option_float(options, "bar_width", 0.72), 0.1, 1.0, 0.05
            )
            self.bar_alpha_spin = self._spin(
                self._option_float(options, "bar_alpha", 1.0), 0.05, 1.0, 0.05
            )
            graph_form.addRow("柱宽:", self.bar_width_spin)
            graph_form.addRow("柱透明度:", self.bar_alpha_spin)
            layout.addWidget(graph)
        elif kind == "cv_contribution":
            graph = QGroupBox("分解图元素")
            graph_form = QFormLayout(graph)
            self.fill_alpha_spin = self._spin(
                self._option_float(options, "fill_alpha", 0.12), 0.0, 1.0, 0.05
            )
            graph_form.addRow("填充透明度:", self.fill_alpha_spin)
            layout.addWidget(graph)
        elif kind in {"cv_overlay", "cp_gcd"}:
            graph = QGroupBox("曲线元素")
            graph_form = QFormLayout(graph)
            self.line_alpha_spin = self._spin(
                self._option_float(options, "line_alpha", 0.9), 0.05, 1.0, 0.05
            )
            graph_form.addRow("线条透明度:", self.line_alpha_spin)
            layout.addWidget(graph)
        layout.addStretch(1)

        controls = []
        for control_type in (QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox):
            controls.extend(self.element_page.findChildren(control_type))
        for control in controls:
            if isinstance(control, QCheckBox):
                control.stateChanged.connect(self._schedule_apply)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._schedule_apply)
            elif isinstance(control, QSpinBox):
                control.valueChanged.connect(self._schedule_apply)
            elif isinstance(control, QDoubleSpinBox):
                control.valueChanged.connect(self._schedule_apply)
            elif isinstance(control, QLineEdit):
                control.textChanged.connect(self._schedule_apply)

    def _schedule_apply(self, *args) -> None:
        if not self._loading:
            self._apply_timer.start()

    def reject(self) -> None:
        if not self._loading and self._apply_timer.isActive():
            self._apply_timer.stop()
            self._apply()
        super().reject()

    def _apply(self) -> None:
        if self._loading or self.tab is None:
            return
        tab = self.tab
        options = dict(tab.spec.analysis_options)
        if hasattr(self, "bar_width_spin"):
            options["bar_width"] = self.bar_width_spin.value()
            options["bar_alpha"] = self.bar_alpha_spin.value()
        if hasattr(self, "fill_alpha_spin"):
            options["fill_alpha"] = self.fill_alpha_spin.value()
        if hasattr(self, "line_alpha_spin"):
            options["line_alpha"] = self.line_alpha_spin.value()
        tab.spec.analysis_options = options
        tab.spec.title = self.title_edit.text().strip()
        tab.spec.show_legend = self.show_legend_cb.isChecked()
        tab.spec.show_axes = self.show_axes_cb.isChecked()
        tab.spec.annotations = self.annotations_cb.isChecked()
        overrides = dict(tab.spec.overrides)
        overrides.update(
            {
                "show_title": self.show_title_cb.isChecked(),
                "legend": self.show_legend_cb.isChecked(),
                "annotation": self.annotations_cb.isChecked(),
                "title_size": self.title_size_spin.value(),
                "label_size": self.label_size_spin.value(),
                "xlabel_size": None,
                "ylabel_size": None,
                "tick_size": self.tick_size_spin.value(),
                "legend_size": self.legend_size_spin.value(),
                "annotation_size": self.annotation_size_spin.value(),
                "title_bold": self.title_bold_cb.isChecked(),
                "label_bold": self.label_bold_cb.isChecked(),
                "xlabel_bold": None,
                "ylabel_bold": None,
                "annotation_bold": self.annotation_bold_cb.isChecked(),
                "line_width": self.line_width_spin.value(),
                "marker_size": self.marker_size_spin.value(),
                "grid": self.grid_cb.isChecked(),
                "minor_ticks": self.minor_ticks_cb.isChecked(),
                "spines_top": self.spines_cb.isChecked(),
                "spines_right": self.spines_cb.isChecked(),
                "ticks_top": self.ticks_top_cb.isChecked(),
                "ticks_right": self.ticks_right_cb.isChecked(),
                "legend_frame": self.legend_frame_cb.isChecked(),
                "legend_columns": self.legend_columns_spin.value(),
                "legend_location": self.legend_location.currentData(),
            }
        )
        tab.apply_overrides(overrides)
        self.color_panel.refresh_colors()
        self.changed.emit()
