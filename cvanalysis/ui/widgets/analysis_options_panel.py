"""Embedded bottom-right editor for the active plot."""
import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QWidget, QComboBox, QCheckBox, QDoubleSpinBox, QPushButton, QLabel,
    QLineEdit, QScrollArea, QFrame, QGroupBox, QSizePolicy)
from cvanalysis.domain.units import (
    CURRENT,
    IMPEDANCE,
    IMPEDANCE_AREA,
    current_family,
    unit_factor,
    unit_labels,
)
from cvanalysis.plotting.axis_limits import (
    axis_display_units,
    axis_limit_unit_values,
    axis_limit_values,
    common_axis_display_unit,
    plot_axis_specs,
)
from cvanalysis.plotting.paper import paper_legend_settings, paper_overrides


class AnalysisOptionsPanel(QWidget):
    applied = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("当前图：分析与论文排版")
        self.tab = None
        layout = QVBoxLayout(self)
        self.context = QLabel()
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        self.pages = QTabWidget()
        layout.addWidget(self.pages)
        self.analysis_page = QWidget()
        self.form = QFormLayout(self.analysis_page)
        self.pages.addTab(self.scroll_page(self.analysis_page), "分析参数")

        self.axis_page = QWidget()
        axis_outer = QVBoxLayout(self.axis_page)
        axis_outer.setContentsMargins(8, 8, 8, 8)
        axis_outer.setSpacing(8)
        self.axis_hint = QLabel(
            "留空表示自动范围。多个子图或双 Y 轴会分别显示设置栏目；"
            "对数轴范围必须为正数。Nyquist 图设置手动范围后改用独立 X/Y 范围。"
            "切换显示单位后点击底部“应用到当前图”，已有范围会按物理值自动换算。"
        )
        self.axis_hint.setWordWrap(True)
        self.axis_hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.axis_hint.setStyleSheet("color: #607d8b;")
        axis_outer.addWidget(self.axis_hint)
        self.unit_host = QWidget()
        self.unit_form = QFormLayout(self.unit_host)
        self.unit_form.setContentsMargins(0, 0, 0, 0)
        self.unit_form.setHorizontalSpacing(8)
        self.unit_form.setVerticalSpacing(7)
        axis_outer.addWidget(self.unit_host)
        log_format_form = QFormLayout()
        self.log_tick_controls = {}
        for side, label in (("x", "X 对数轴刻度"), ("y", "Y 对数轴刻度")):
            combo = QComboBox()
            for text, value in (("默认", "auto"), ("科学计数法（10 的幂）", "scientific"), ("小数", "decimal")):
                combo.addItem(text, value)
            combo.setToolTip("应用于当前图所有对应方向的对数轴；线性轴不受影响。")
            log_format_form.addRow(label, combo)
            self.log_tick_controls[side] = combo
        axis_outer.addLayout(log_format_form)
        self.unified_ticks_cb = QCheckBox("强制 X/Y 刻度间隔一致")
        self.unified_ticks_cb.setToolTip(
            "让 X/Y 使用相同数值的主刻度步长；适合两轴范围相同的 Nyquist 图。"
            "仅对线性单坐标轴图生效。"
        )
        axis_outer.addWidget(self.unified_ticks_cb)
        self.unified_interval_host = QWidget()
        interval_row = QHBoxLayout(self.unified_interval_host)
        interval_row.setContentsMargins(24, 0, 0, 0)
        interval_row.setSpacing(6)
        interval_row.addWidget(QLabel("主刻度间隔:"))
        self.unified_interval_edit = QLineEdit()
        self.unified_interval_edit.setPlaceholderText("自动（留空）")
        self.unified_interval_edit.setToolTip(
            "手动指定 X/Y 共用的主刻度数值间隔，例如 100；留空由程序自动选择。"
        )
        self.unified_interval_edit.setMaximumWidth(120)
        interval_row.addWidget(self.unified_interval_edit)
        self.unified_interval_unit_label = QLabel("")
        self.unified_interval_unit_label.setStyleSheet("color: #607d8b;")
        interval_row.addWidget(self.unified_interval_unit_label)
        interval_row.addStretch(1)
        axis_outer.addWidget(self.unified_interval_host)
        self.unified_ticks_cb.toggled.connect(self._update_unified_interval_enabled)
        self.axis_sections_host = QWidget()
        self.axis_sections_layout = QVBoxLayout(self.axis_sections_host)
        self.axis_sections_layout.setContentsMargins(0, 0, 0, 0)
        self.axis_sections_layout.setSpacing(8)
        axis_outer.addWidget(self.axis_sections_host)
        axis_outer.addStretch(1)
        self.axis_clear_button = QPushButton("清空全部范围输入")
        self.axis_clear_button.setProperty("secondary", True)
        self.axis_clear_button.setToolTip("清空后再点击“应用到当前图”即可恢复自动范围")
        self.axis_clear_button.clicked.connect(self._clear_axis_limit_inputs)
        axis_outer.addWidget(self.axis_clear_button)
        self.pages.addTab(self.scroll_page(self.axis_page), "坐标范围")
        self.axis_controls = {}
        self.axis_specs = []
        self.unit_controls = {}

        paper = QWidget()
        form = QFormLayout(paper)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.paper_enabled = QCheckBox("按论文占比补偿字号")
        self.paper_enabled.setToolTip("保持逻辑画布尺寸；按论文中的实际插入宽度补偿源图字体。PNG/TIFF DPI 可在导出时单独调整。")
        form.addRow(self.paper_enabled)
        self.fraction = QLineEdit("0.5")
        self.fraction.setToolTip("图片宽度 ÷ 页面版心宽度，如 0.5、0.33、0.25；也接受 0/25 表示 0.25")
        form.addRow("页面版心宽度占比", self.fraction)
        self.page_width = self.spin(50, 400, 160)
        self.page_width.setSuffix(" mm")
        form.addRow("版心宽度（不含页边距）", self.page_width)
        self.body_size = self.spin(5, 30, 10)
        self.body_size.setSuffix(" pt")
        form.addRow("论文正文字号", self.body_size)
        self.legend_placement = QComboBox()
        for label, value in (("自动", "auto"), ("图内", "inside"), ("图外", "outside")):
            self.legend_placement.addItem(label, value)
        form.addRow("图例位置", self.legend_placement)
        self.legend_outside_threshold = self.spin(0, 1, .5)
        self.legend_outside_threshold.setDecimals(2)
        self.legend_outside_threshold.setSingleStep(.05)
        self.legend_outside_threshold.setToolTip("自动模式下，页面占比小于此值时将图例放到图外。")
        form.addRow("自动外置阈值", self.legend_outside_threshold)
        self.legend_columns = QComboBox()
        self.legend_columns.addItem("自动", "auto")
        for count in range(1, 9):
            self.legend_columns.addItem(f"{count} 列", count)
        form.addRow("图例列数", self.legend_columns)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(80)
        form.addRow(self.preview)
        self.pages.addTab(self.scroll_page(paper), "论文尺寸与字号")
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #a33")
        layout.addWidget(self.error)
        apply = QPushButton("应用到当前图")
        self.apply_button = apply
        apply.clicked.connect(self.apply)
        layout.addWidget(apply)
        for control in (self.fraction, self.page_width, self.body_size, self.legend_outside_threshold):
            (control.textChanged if isinstance(control, QLineEdit) else control.valueChanged).connect(self.update_preview)
        self.paper_enabled.toggled.connect(self.update_preview)
        self.legend_placement.currentIndexChanged.connect(self._update_legend_controls)
        self.legend_placement.currentIndexChanged.connect(self.update_preview)
        self.legend_columns.currentIndexChanged.connect(self.update_preview)
        self.bind(None)

    @staticmethod
    def scroll_page(widget):
        area = QScrollArea()
        area.setFrameShape(QFrame.NoFrame)
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    @staticmethod
    def spin(low, high, value):
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(low, high)
        spin.setValue(value)
        return spin

    def bind(self, tab):
        self.tab = tab
        self.pages.setEnabled(tab is not None)
        self.apply_button.setEnabled(tab is not None)
        if tab is None:
            self.controls = {}
            self.axis_controls = {}
            self.axis_specs = []
            self.unit_controls = {}
            self._clear_unit_controls()
            self.unit_host.setVisible(False)
            self.unified_ticks_cb.setVisible(False)
            self.unified_interval_host.setVisible(False)
            self._clear_axis_sections()
            self.axis_clear_button.setEnabled(False)
            self.context.setText("当前图设置：创建或选择图表后可编辑")
            self.error.clear()
            return
        self.context.setText("当前图：" + tab.spec.label)
        self.axis_clear_button.setEnabled(True)
        while self.form.rowCount():
            self.form.removeRow(0)
        self.controls = {}
        spec = tab.spec
        formats = spec.analysis_options.get("log_tick_formats")
        formats = formats if isinstance(formats, dict) else {}
        for side, combo in self.log_tick_controls.items():
            combo.setCurrentIndex(max(0, combo.findData(formats.get(side, "auto"))))
        if spec.kind == "cv_cap_scan":
            combo = QComboBox()
            for label, key in (
                ("一次函数 C=mv+b", "linear"),
                ("直线拟合（跟随坐标轴）", "coordinate_line"),
                ("幂律 C=avⁿ", "power"),
                ("不拟合", "none"),
            ):
                combo.addItem(label, key)
            combo.setToolTip("一次函数在原始数据上拟合 C=mv+b；直线拟合会按当前 X/Y 轴类型变换数据，使结果在图上为直线；幂律拟合保留 C=avⁿ 模型。")
            fit_index = combo.findData(spec.analysis_options.get("fit_method", "power"))
            combo.setCurrentIndex(fit_index if fit_index >= 0 else combo.findData("power"))
            self.form.addRow("拟合方式", combo)
            self.controls["fit_method"] = combo
            x_scale = QComboBox()
            y_scale = QComboBox()
            for control in (x_scale, y_scale):
                control.addItem("自动（线性）", "auto")
                control.addItem("线性", "linear")
                control.addItem("对数", "log")
            x_request = spec.analysis_options.get("x_axis_scale")
            if x_request is None:
                x_request = "log" if spec.x_log else "auto"
            y_request = spec.analysis_options.get("y_axis_scale", "auto")
            x_scale.setCurrentIndex(max(0, x_scale.findData(x_request)))
            y_scale.setCurrentIndex(max(0, y_scale.findData(y_request)))
            self.form.addRow("横轴类型", x_scale)
            self.form.addRow("纵轴类型", y_scale)
            self.controls["x_axis_scale"] = x_scale
            self.controls["y_axis_scale"] = y_scale
            for label, key in (("显示误差棒（循环标准差）", "error_bars"), ("显示拟合线", "fit_line")):
                cb = QCheckBox(label)
                cb.setChecked(spec.analysis_options.get(key, True))
                self.form.addRow(cb)
                self.controls[key] = cb
        if spec.kind in ("cv_current_scan", "cv_bvalue"):
            control = self.spin(-1000, 1000, spec.target_voltage or 0)
            control.setSuffix(" V")
            self.form.addRow("目标电位", control)
            self.controls["target_voltage"] = control
            if spec.kind == "cv_bvalue":
                combo = QComboBox()
                for label, key in (
                    ("旧版平均绝对电流（默认）", "absolute"),
                    ("正扫支路", "up"),
                    ("反扫支路", "down"),
                ):
                    combo.addItem(label, key)
                combo.setToolTip(
                    "b 值通常使用固定电位处单一支路或峰电流。旧版平均口径会混合正反扫响应；"
                    "保留默认仅为兼容已有结果。"
                )
                selected = spec.analysis_options.get("b_current_mode", "absolute")
                index = combo.findData(selected)
                combo.setCurrentIndex(index if index >= 0 else combo.findData("absolute"))
                self.form.addRow("b 值电流来源", combo)
                self.controls["b_current_mode"] = combo
        if spec.kind == "cv_contribution":
            control = self.spin(.000001, 1000000, spec.selected_scan_rate or .01)
            control.setSuffix(" V/s")
            self.form.addRow("分解扫速", control)
            self.controls["selected_scan_rate"] = control
        if spec.kind.startswith("eis_"):
            for label, key in (("最低频率（留空不限）", "frequency_low"), ("最高频率（留空不限）", "frequency_high")):
                value = getattr(spec, key)
                control = QLineEdit("" if value is None else str(value))
                self.form.addRow(label + " Hz", control)
                self.controls[key] = control
        if spec.kind.startswith("cp_"):
            cp_options = (
                ("电位-时间自动补全保持区间", "complete_holds", True),
                ("容量计入恒压保持段", "include_holds", False),
                ("容量-循环图显示充电容量", "show_charge", True),
                ("容量-循环图显示库伦效率", "show_efficiency", True),
            )
            for label, key, default in cp_options:
                if key in {"include_holds", "show_charge", "show_efficiency"} and spec.kind != "cp_capacity":
                    continue
                if key == "complete_holds" and spec.kind != "cp_gcd":
                    continue
                cb = QCheckBox(label)
                cb.setChecked(bool(spec.analysis_options.get(key, default)))
                self.form.addRow(cb)
                self.controls[key] = cb
        for label, key in (("显示图例", "show_legend"), ("显示坐标轴", "show_axes"), ("显示分析注释", "annotations")):
            cb = QCheckBox(label)
            cb.setChecked(getattr(spec, key))
            self.form.addRow(cb)
            self.controls[key] = cb
        data = spec.paper_layout
        self.paper_enabled.setChecked(data.get("enabled", False))
        self.fraction.setText(str(data.get("fraction", .5)))
        self.page_width.setValue(data.get("text_width_mm", 160))
        self.body_size.setValue(data.get("body_pt", 10))
        self.legend_placement.setCurrentIndex(max(0, self.legend_placement.findData(data.get("legend_placement", "auto"))))
        try:
            threshold = float(data.get("legend_outside_threshold", .5))
        except (TypeError, ValueError):
            threshold = .5
        self.legend_outside_threshold.setValue(threshold if math.isfinite(threshold) and 0 <= threshold <= 1 else .5)
        columns = data.get("legend_columns", "auto")
        if columns != "auto":
            try:
                columns = int(columns)
            except (TypeError, ValueError, OverflowError):
                columns = "auto"
        index = self.legend_columns.findData(columns)
        self.legend_columns.setCurrentIndex(max(0, index))
        self._update_legend_controls()
        self.error.clear()
        self.update_preview()
        self.refresh_axis_scale_labels()
        self._rebuild_unit_controls(tab)
        self._refresh_unified_tick_controls(tab)
        self._rebuild_axis_limit_page(tab)

    def refresh_axis_scale_labels(self):
        """Show which scale Auto currently resolves to in the active rendering."""
        if self.tab is None or not self.tab.figure.axes:
            return
        axis = self.tab.figure.axes[0]
        for key, mpl_axis in (("x_axis_scale", axis.xaxis), ("y_axis_scale", axis.yaxis)):
            control = self.controls.get(key)
            if control is None:
                continue
            index = control.findData("auto")
            if index < 0:
                continue
            label = "自动（对数）" if mpl_axis.get_scale() == "log" else "自动（线性）"
            was_blocked = control.blockSignals(True)
            control.setItemText(index, label)
            control.blockSignals(was_blocked)

    def _update_legend_controls(self, *args):
        self.legend_outside_threshold.setEnabled(self.legend_placement.currentData() == "auto")

    @staticmethod
    def _unified_tick_target(tab):
        if tab is None:
            return None
        kind = tab.spec.kind
        if kind in {"eis_bode", "cp_capacity"}:
            return None
        if kind == "eis_fit":
            axes = tab.figure.axes[:1]
        elif len(tab.figure.axes) == 1:
            axes = tab.figure.axes
        else:
            return None
        if not axes:
            return None
        ax = axes[0]
        if ax.get_xscale() != "linear" or ax.get_yscale() != "linear":
            return None
        return ax

    def _common_tick_unit(self, tab):
        target = self._unified_tick_target(tab)
        return common_axis_display_unit(target) if target is not None else None

    def _update_unified_interval_enabled(self, *args) -> None:
        self.unified_interval_edit.setEnabled(self.unified_ticks_cb.isChecked())

    def _sync_unified_tick_interval(self, tab) -> None:
        if tab is None:
            return
        options = tab.spec.analysis_options
        try:
            interval = float(options.get("unified_tick_interval"))
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(interval) or interval <= 0:
            return
        current = self._common_tick_unit(tab)
        stored = options.get("unified_tick_interval_unit")
        if isinstance(stored, dict) and current is not None:
            try:
                ratio = float(current[1]) / float(stored.get("factor"))
            except (TypeError, ValueError, ZeroDivisionError):
                ratio = 1.0
            if math.isfinite(ratio) and abs(ratio - 1.0) > 1e-12:
                interval *= ratio
                options["unified_tick_interval"] = interval
        if current is not None:
            options["unified_tick_interval_unit"] = {
                "label": str(current[0]),
                "factor": float(current[1]),
            }

    def _refresh_unified_tick_controls(self, tab) -> None:
        available = self._unified_tick_target(tab) is not None
        self.unified_ticks_cb.setVisible(available)
        self.unified_interval_host.setVisible(available)
        if not available:
            self.unified_ticks_cb.setChecked(False)
            self.unified_interval_edit.clear()
            self.unified_interval_unit_label.clear()
            self._update_unified_interval_enabled()
            return
        options = tab.spec.analysis_options
        self.unified_ticks_cb.setChecked(
            bool(options.get("unified_xy_ticks", False))
        )
        self._sync_unified_tick_interval(tab)
        try:
            interval = float(options.get("unified_tick_interval"))
        except (TypeError, ValueError, OverflowError):
            interval = None
        if interval is None or not math.isfinite(interval) or interval <= 0:
            self.unified_interval_edit.clear()
        else:
            self.unified_interval_edit.setText(f"{interval:g}")
        unit = self._common_tick_unit(tab)
        self.unified_interval_unit_label.setText(f"({unit[0]})" if unit else "")
        self._update_unified_interval_enabled()

    @staticmethod
    def _unit_family_specs(spec):
        kind = spec.kind
        if kind.startswith("eis_"):
            family = IMPEDANCE_AREA if spec.normalization == "area" else IMPEDANCE
            return [("impedance", "阻抗单位", family)]
        if kind in {
            "cv_overlay",
            "cv_current_scan",
            "cv_bvalue",
            "cv_contribution",
        }:
            return [("current", "电流单位", current_family(spec.normalization))]
        if kind == "cp_gcd":
            return [("current", "电流单位", CURRENT)]
        return []

    def _clear_unit_controls(self) -> None:
        while self.unit_form.rowCount():
            self.unit_form.removeRow(0)

    def _rebuild_unit_controls(self, tab) -> None:
        self._clear_unit_controls()
        self.unit_controls = {}
        if tab is None:
            self.unit_host.setVisible(False)
            return
        specs = self._unit_family_specs(tab.spec)
        overrides = tab.spec.analysis_options.get("unit_overrides")
        overrides = overrides if isinstance(overrides, dict) else {}
        for key, label, family in specs:
            combo = QComboBox()
            combo.addItem("自动", "auto")
            for unit in unit_labels(family):
                combo.addItem(unit, unit)
            selected = overrides.get(key)
            index = combo.findData(selected) if selected else 0
            combo.setCurrentIndex(max(0, index))
            combo.setToolTip(
                "自动按数据量级选择显示单位；手动指定后点击“应用到当前图”生效，"
                "已有坐标范围会按物理值自动换算。"
            )
            self.unit_form.addRow(label + ":", combo)
            self.unit_controls[key] = combo
        self.unit_host.setVisible(bool(specs))

    def _sync_axis_limit_units(self, tab) -> None:
        """Keep stored limits displayed in the unit currently shown on screen."""
        if tab is None:
            return
        options = tab.spec.analysis_options
        limits = options.get("axis_limits")
        stored_all = options.get("axis_limit_units")
        if not isinstance(limits, dict) or not isinstance(stored_all, dict):
            return
        for spec in self.axis_specs:
            entry = limits.get(spec.key)
            if not isinstance(entry, dict) or spec.index >= len(tab.figure.axes):
                continue
            ax = tab.figure.axes[spec.index]
            current = axis_display_units(ax)
            stored = axis_limit_unit_values(options, spec.key)
            if not current or not stored:
                continue
            updated_units = {}
            for side in ("x", "y"):
                low_key = f"{side}_min"
                high_key = f"{side}_max"
                if low_key not in entry and high_key not in entry:
                    continue
                current_info = current.get(side)
                stored_info = stored.get(side)
                if current_info is None:
                    continue
                if stored_info is not None:
                    try:
                        ratio = float(current_info[1]) / float(stored_info["factor"])
                    except (TypeError, ValueError, ZeroDivisionError):
                        ratio = 1.0
                    if math.isfinite(ratio) and abs(ratio - 1.0) > 1e-12:
                        for field in (low_key, high_key):
                            value = entry.get(field)
                            if value is None or value == "":
                                continue
                            try:
                                entry[field] = float(value) * ratio
                            except (TypeError, ValueError, OverflowError):
                                continue
                updated_units[side] = {
                    "label": str(current_info[0]),
                    "factor": float(current_info[1]),
                }
            if updated_units:
                stored_all[spec.key] = updated_units
            else:
                stored_all.pop(spec.key, None)
        options["axis_limit_units"] = stored_all

    def _collect_axis_limit_units(self, limits: dict) -> dict:
        if self.tab is None:
            return {}
        units: dict[str, dict] = {}
        for spec in self.axis_specs:
            entry = limits.get(spec.key)
            if not isinstance(entry, dict) or spec.index >= len(self.tab.figure.axes):
                continue
            ax = self.tab.figure.axes[spec.index]
            displayed = axis_display_units(ax)
            side_units = {}
            for side in ("x", "y"):
                if f"{side}_min" not in entry and f"{side}_max" not in entry:
                    continue
                info = displayed.get(side)
                if info is not None:
                    side_units[side] = {
                        "label": str(info[0]),
                        "factor": float(info[1]),
                    }
            if side_units:
                units[spec.key] = side_units
        return units

    def _clear_axis_sections(self) -> None:
        while self.axis_sections_layout.count():
            item = self.axis_sections_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        # deleteLater is asynchronous; ensure stale group boxes cannot paint
        # over the newly built sections before the event loop deletes them.
        for child in self.axis_sections_host.findChildren(QWidget):
            if child.parent() is self.axis_sections_host:
                child.hide()
                child.setParent(None)
                child.deleteLater()

    def _axis_range_row(self, values: dict, prefix: str):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        low = QLineEdit()
        high = QLineEdit()
        low.setPlaceholderText("最小（自动）")
        high.setPlaceholderText("最大（自动）")
        for edit, field in ((low, f"{prefix}_min"), (high, f"{prefix}_max")):
            value = values.get(field)
            edit.setText("" if value is None else f"{value:g}")
            edit.setToolTip("留空表示自动；可使用科学计数法，如 1e-6。")
            edit.setMinimumWidth(60)
        layout.addWidget(low, 1)
        layout.addWidget(QLabel("–"))
        layout.addWidget(high, 1)
        return row, low, high

    def _rebuild_axis_limit_page(self, tab) -> None:
        self._clear_axis_sections()
        self.axis_controls = {}
        self.axis_specs = []
        if tab is None:
            return
        specs = plot_axis_specs(tab.spec.kind, tab.figure)
        self.axis_specs = specs
        self._sync_axis_limit_units(tab)
        for spec in specs:
            group = QGroupBox(spec.label)
            form = QFormLayout(group)
            form.setContentsMargins(9, 24, 9, 9)
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(7)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            values = axis_limit_values(tab.spec.analysis_options, spec.key)
            displayed = (
                axis_display_units(tab.figure.axes[spec.index])
                if spec.index < len(tab.figure.axes)
                else {}
            )
            controls: dict[str, QLineEdit] = {}
            if spec.editable_x:
                row, low, high = self._axis_range_row(values, "x")
                unit = displayed.get("x")
                label = "X 轴范围" + (f" ({unit[0]})" if unit else "") + ":"
                form.addRow(label, row)
                controls["x_min"] = low
                controls["x_max"] = high
            else:
                note = QLabel("X 轴与左轴共享，仅设置 Y 范围。")
                note.setStyleSheet("color: #78909c;")
                form.addRow(note)
            if spec.editable_y:
                row, low, high = self._axis_range_row(values, "y")
                unit = displayed.get("y")
                label = "Y 轴范围" + (f" ({unit[0]})" if unit else "") + ":"
                form.addRow(label, row)
                controls["y_min"] = low
                controls["y_max"] = high
            else:
                note = QLabel("该轴范围由其他栏目控制。")
                note.setStyleSheet("color: #78909c;")
                form.addRow(note)
            self.axis_sections_layout.addWidget(group)
            self.axis_controls[spec.key] = controls
        self.axis_sections_layout.addStretch(1)

    def _clear_axis_limit_inputs(self) -> None:
        for controls in self.axis_controls.values():
            for edit in controls.values():
                edit.clear()

    def _parse_axis_limit(self, edit: QLineEdit, label: str) -> float | None:
        text = edit.text().strip()
        if not text:
            return None
        try:
            value = float(text)
        except (TypeError, ValueError):
            raise ValueError(f"{label}必须是数值或留空") from None
        if not math.isfinite(value):
            raise ValueError(f"{label}必须是有限数值或留空")
        return value

    def _collect_axis_limits(self) -> dict:
        limits: dict[str, dict] = {}
        if self.tab is None:
            return limits
        for spec in self.axis_specs:
            controls = self.axis_controls.get(spec.key, {})
            entry: dict[str, float] = {}
            axis = (
                self.tab.figure.axes[spec.index]
                if spec.index < len(self.tab.figure.axes)
                else None
            )
            if spec.editable_x and "x_min" in controls:
                x_min = self._parse_axis_limit(controls["x_min"], f"{spec.label} X 最小值")
                x_max = self._parse_axis_limit(controls["x_max"], f"{spec.label} X 最大值")
                if x_min is not None and x_max is not None and x_min >= x_max:
                    raise ValueError(f"{spec.label}：X 最小值必须小于最大值")
                if axis is not None and axis.get_xscale() == "log":
                    if any(value is not None and value <= 0 for value in (x_min, x_max)):
                        raise ValueError(f"{spec.label}：对数 X 轴范围必须为正数")
                if x_min is not None:
                    entry["x_min"] = x_min
                if x_max is not None:
                    entry["x_max"] = x_max
            if spec.editable_y and "y_min" in controls:
                y_min = self._parse_axis_limit(controls["y_min"], f"{spec.label} Y 最小值")
                y_max = self._parse_axis_limit(controls["y_max"], f"{spec.label} Y 最大值")
                if y_min is not None and y_max is not None and y_min >= y_max:
                    raise ValueError(f"{spec.label}：Y 最小值必须小于最大值")
                if axis is not None and axis.get_yscale() == "log":
                    if any(value is not None and value <= 0 for value in (y_min, y_max)):
                        raise ValueError(f"{spec.label}：对数 Y 轴范围必须为正数")
                if y_min is not None:
                    entry["y_min"] = y_min
                if y_max is not None:
                    entry["y_max"] = y_max
            if entry:
                limits[spec.key] = entry
        return limits

    def paper_values(self):
        text = self.fraction.text().strip()
        if text.startswith("0/"):
            text = "0." + text[2:]
        threshold = self.legend_outside_threshold.value()
        return dict(
            enabled=self.paper_enabled.isChecked(),
            fraction=float(text),
            text_width_mm=self.page_width.value(),
            body_pt=self.body_size.value(),
            legend_placement=self.legend_placement.currentData() or "auto",
            legend_outside_threshold=threshold,
            legend_columns=self.legend_columns.currentData() or "auto",
        )

    def update_preview(self, *args):
        if self.tab is None:
            return
        try:
            data = self.paper_values()
            style = self.tab.base_style.with_overrides(self.tab.spec.overrides)
            values = paper_overrides({**data, "enabled": True}, style)
            scale = data["text_width_mm"] * data["fraction"] / (style.figure_size[0] * 25.4)
            placement, threshold, columns = paper_legend_settings(data, fraction=data["fraction"])
            placement_label = "图外" if placement == "outside" else "图内"
            if data["legend_placement"] == "auto":
                placement_label += f"（占比 {'<' if data['fraction'] < threshold else '≥'} {threshold:g}）"
            columns_label = "自动列数" if columns == "auto" else f"{columns} 列"
            small_font_notice = "\n占比小于 0.33 时，补偿字号自动再缩至 80%。" if data["fraction"] < .33 else ""
            self.preview.setText(
                f"PNG 默认 {round(style.figure_size[0]*style.save_dpi)} × {round(style.figure_size[1]*style.save_dpi)} px（导出时可改 DPI）；"
                f"论文宽度 {data['text_width_mm'] * data['fraction']:.1f} mm，缩放 {scale:.1%}。\n"
                f"轴标题：源图 {values['xlabel_size']:.2f} → 论文 {values['xlabel_size']*scale:.2f} pt；"
                f"刻度/图例 {values['tick_size']*scale:.2f} pt，注释 {values['annotation_size']*scale:.2f} pt。\n"
                f"图例：{placement_label}，{columns_label}。{small_font_notice}")
        except (ValueError, TypeError) as exc:
            self.preview.setText(str(exc))

    def apply(self):
        if self.tab is None:
            return
        try:
            paper = self.paper_values()
            paper_overrides(paper, self.tab.base_style)
            paper_legend_settings(paper, fraction=paper["fraction"])
            changes, analysis = {}, {}
            for key, control in self.controls.items():
                if isinstance(control, QComboBox):
                    analysis[key] = control.currentData()
                elif key in (
                    "fit_line",
                    "error_bars",
                    "complete_holds",
                    "include_holds",
                    "show_charge",
                    "show_efficiency",
                ):
                    analysis[key] = control.isChecked()
                elif isinstance(control, QCheckBox):
                    changes[key] = control.isChecked()
                elif isinstance(control, QLineEdit):
                    value = float(control.text()) if control.text().strip() else None
                    if value is not None and (not math.isfinite(value) or value <= 0):
                        raise ValueError("频率必须为有限正数或留空")
                    changes[key] = value
                else:
                    changes[key] = control.value()
            if changes.get("frequency_low") is not None and changes.get("frequency_high") is not None and changes["frequency_low"] > changes["frequency_high"]:
                raise ValueError("最低频率不能大于最高频率")
            axis_limits = self._collect_axis_limits()
            axis_limit_units = self._collect_axis_limit_units(axis_limits)
            unit_overrides = {
                key: control.currentData()
                for key, control in self.unit_controls.items()
                if control.currentData() not in (None, "", "auto")
            }
            unified_ticks_available = self._unified_tick_target(self.tab) is not None
            unified_ticks = (
                unified_ticks_available and self.unified_ticks_cb.isChecked()
            )
            unified_interval = None
            if unified_ticks:
                text = self.unified_interval_edit.text().strip()
                if text:
                    try:
                        unified_interval = float(text)
                    except (TypeError, ValueError):
                        raise ValueError("主刻度间隔必须是数值或留空") from None
                    if not math.isfinite(unified_interval) or unified_interval <= 0:
                        raise ValueError("主刻度间隔必须为有限正数或留空")
        except (ValueError, TypeError) as exc:
            self.error.setStyleSheet("color: #a33")
            self.error.setText(str(exc))
            return
        for key, value in changes.items():
            setattr(self.tab.spec, key, value)
        self.tab.spec.analysis_options.update(analysis)
        log_formats = {
            side: combo.currentData()
            for side, combo in self.log_tick_controls.items()
            if combo.currentData() in ("scientific", "decimal")
        }
        if log_formats:
            self.tab.spec.analysis_options["log_tick_formats"] = log_formats
        else:
            self.tab.spec.analysis_options.pop("log_tick_formats", None)
        if unit_overrides:
            self.tab.spec.analysis_options["unit_overrides"] = unit_overrides
        else:
            self.tab.spec.analysis_options.pop("unit_overrides", None)
        if unified_ticks:
            self.tab.spec.analysis_options["unified_xy_ticks"] = True
            if unified_interval is not None:
                self.tab.spec.analysis_options["unified_tick_interval"] = (
                    unified_interval
                )
                common = self._common_tick_unit(self.tab)
                if common is not None:
                    self.tab.spec.analysis_options[
                        "unified_tick_interval_unit"
                    ] = {"label": str(common[0]), "factor": float(common[1])}
                else:
                    self.tab.spec.analysis_options.pop(
                        "unified_tick_interval_unit", None
                    )
            else:
                self.tab.spec.analysis_options.pop("unified_tick_interval", None)
                self.tab.spec.analysis_options.pop(
                    "unified_tick_interval_unit", None
                )
        else:
            self.tab.spec.analysis_options.pop("unified_xy_ticks", None)
            self.tab.spec.analysis_options.pop("unified_tick_interval", None)
            self.tab.spec.analysis_options.pop("unified_tick_interval_unit", None)
        if axis_limits:
            self.tab.spec.analysis_options["axis_limits"] = axis_limits
            if axis_limit_units:
                self.tab.spec.analysis_options["axis_limit_units"] = axis_limit_units
            else:
                self.tab.spec.analysis_options.pop("axis_limit_units", None)
        else:
            self.tab.spec.analysis_options.pop("axis_limits", None)
            self.tab.spec.analysis_options.pop("axis_limit_units", None)
        self.tab.spec.paper_layout = paper
        self.tab.redraw()
        self._rebuild_unit_controls(self.tab)
        self._refresh_unified_tick_controls(self.tab)
        self._rebuild_axis_limit_page(self.tab)
        self.applied.emit(self.tab)
        self.error.setStyleSheet("color: #2e7d32")
        self.error.setText("已应用")
