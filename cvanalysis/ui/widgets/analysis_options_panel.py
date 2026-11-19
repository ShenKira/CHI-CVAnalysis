"""Embedded bottom-right editor for the active plot."""
import math

from PySide6.QtCore import QEvent, Qt, QTimer, QSignalBlocker, Signal
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QWidget, QComboBox, QCheckBox, QDoubleSpinBox, QPushButton, QLabel,
    QLineEdit, QScrollArea, QFrame, QGroupBox, QSizePolicy, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from cvanalysis.analysis.cp import CPRunSummary, analyze_cp_run
from cvanalysis.analysis.cp_series import (
    cp_concat_entries,
    cp_cycle_values,
    find_cp_cycle_value,
    normalize_cp_concat_config,
    resolve_cp_unified_reference,
)
from cvanalysis.domain.units import (
    CAPACITANCE,
    CURRENT,
    IMPEDANCE,
    IMPEDANCE_AREA,
    current_family,
    unit_factor,
    unit_labels,
    cp_plot_units,
    canonical_unit,
    capacitance_family,
    charge_family,
    sweep_current_family,
)
from cvanalysis.plotting.axis_limits import (
    axis_display_units,
    axis_display_dimensions,
    axis_limit_values,
    common_axis_display_unit,
    plot_axis_specs,
    sync_axis_limit_units,
)
from cvanalysis.plotting.legend import DEFAULT_CYCLE_LEGEND_LIMIT
from cvanalysis.plotting.cp_renderer import cp_automatic_unit
from cvanalysis.plotting.paper import paper_legend_settings, paper_overrides
from cvanalysis.plotting.template_format import TemplateError, format_template
from cvanalysis.plotting.it_references import references_from_options
from cvanalysis.ui.theme import apply_button_role, apply_theme_role
from cvanalysis.ui.dialogs.dunn_basis import BASIS_LABELS, BASIS_NOTE, show_dunn_basis
from cvanalysis.ui.tokens import BASE_FONT_SIZE, UiTokens
from cvanalysis.ui.widgets.formatted_text_preview import FormattedTextPreview


class AnalysisOptionsPanel(QWidget):
    applied = Signal(object)
    detach_requested = Signal()
    tab_bar_changed = Signal()
    cp_concat_settings_requested = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("当前图：分析与论文排版")
        self.tab = None
        self._reference_connected_tab = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.context.setToolTip("双击标题，在独立窗口中操作当前图选项；关闭窗口后返回工作区。")
        self.context.installEventFilter(self)
        apply_theme_role(self.context, "title")
        layout.addWidget(self.context)
        self.pages = QTabWidget()
        self.pages.setDocumentMode(True)
        self.pages.setElideMode(Qt.ElideRight)
        self.pages.setUsesScrollButtons(True)
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
        apply_theme_role(self.axis_hint, "hint")
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
        self.unified_ticks_cb = QCheckBox("统一 X/Y 刻度的数值间隔")
        self.unified_ticks_cb.setToolTip(
            "让 X/Y 使用相同数值的主刻度步长；物理单位不同时仅表示数字相同。适合 Nyquist 图。"
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
        apply_theme_role(self.unified_interval_unit_label, "hint")
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
        apply_button_role(self.axis_clear_button, "secondary")
        self.axis_clear_button.setToolTip("清空后再点击“应用到当前图”即可恢复自动范围")
        self.axis_clear_button.clicked.connect(self._clear_axis_limit_inputs)
        axis_outer.addWidget(self.axis_clear_button)
        self.pages.addTab(self.scroll_page(self.axis_page), "坐标范围")
        self.axis_controls = {}
        self.axis_specs = []
        self.unit_controls = {}
        self._axis_unit_snapshots = {}
        self._axis_range_labels = {}
        self._cp_refresh_unit_controls = None
        self._unit_controls_signature = ()

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
        apply_theme_role(self.error, "error")
        layout.addWidget(self.error)
        apply = QPushButton("应用到当前图")
        self.apply_button = apply
        apply_button_role(apply, "primary", pill=True)
        apply.clicked.connect(self.apply)
        layout.addWidget(apply)
        for control in (self.fraction, self.page_width, self.body_size, self.legend_outside_threshold):
            (control.textChanged if isinstance(control, QLineEdit) else control.valueChanged).connect(self.update_preview)
        self.paper_enabled.toggled.connect(self.update_preview)
        self.legend_placement.currentIndexChanged.connect(self._update_legend_controls)
        self.legend_placement.currentIndexChanged.connect(self.update_preview)
        self.legend_columns.currentIndexChanged.connect(self.update_preview)
        self._detach_surfaces = (self.context, self.analysis_page, self.axis_page, paper, self.pages.tabBar())
        self._bar_scan_timer = QTimer(self)
        self._bar_scan_timer.setSingleShot(True)
        self._bar_scan_timer.timeout.connect(self.refresh_detach_tab_bar)
        self.pages.installEventFilter(self)
        for surface in self._detach_surfaces[1:]:
            surface.installEventFilter(self)
        self.bind(None)

    def eventFilter(self, watched, event):
        if watched is getattr(self, "pages", None) and event.type() in (QEvent.ChildAdded, QEvent.StyleChange, QEvent.Show):
            self._bar_scan_timer.start(0)
        if watched in getattr(self, "_detach_surfaces", (self.context,)) and event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self.detach_requested.emit()
            return True
        return super().eventFilter(watched, event)

    def refresh_detach_tab_bar(self):
        bar = self.pages.tabBar()
        changed = self._detach_surfaces[-1] is not bar
        self._detach_surfaces = (*self._detach_surfaces[:-1], bar)
        bar.installEventFilter(self)
        if changed:
            self.tab_bar_changed.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.detach_requested.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

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

    @staticmethod
    def _cp_run_summary(run):
        return (
            run.summary
            if isinstance(run.summary, CPRunSummary)
            else analyze_cp_run(run)
        )

    def _cp_live_context(self):
        if self.tab is None:
            return [], {}
        spec = self.tab.spec
        selected = set(spec.run_ids)
        runs = [
            run
            for run in self.tab.dataset.cp_runs
            if run.run_id in selected
        ]
        summaries = {
            run.run_id: self._cp_run_summary(run) for run in runs
        }
        return runs, summaries

    def _populate_cp_reference_runs(self, combo) -> None:
        """Refresh only the unified-reference file combo from live plot data."""
        if self.tab is None or combo is None:
            return
        runs, summaries = self._cp_live_context()
        spec = self.tab.spec
        order, _ranges = normalize_cp_concat_config(
            runs,
            summaries,
            order=spec.analysis_options.get("cp_concat_order"),
            ranges=spec.analysis_options.get("cp_concat_ranges"),
        )
        by_id = {run.run_id: run for run in runs}
        saved = str(
            spec.analysis_options.get("capacity_percent_reference_run_id")
            or ""
        )
        current = combo.currentData()
        with QSignalBlocker(combo):
            combo.clear()
            for run_id in order:
                run = by_id.get(run_id)
                if run is None:
                    continue
                combo.addItem(run.display_short_name, run_id)
                combo.setItemData(
                    combo.count() - 1,
                    run.display_name,
                    Qt.ToolTipRole,
                )
            if combo.count() == 0:
                combo.addItem("（当前图没有 CP 数据）", None)
            target = current if current in by_id else saved
            index = combo.findData(target) if target else -1
            hidden = self.tab.dataset.find_cp(saved) if index < 0 and saved else None
            if hidden is not None:
                combo.insertItem(0, f"（未勾选）{hidden.display_short_name}", None)
                index = 0
            combo.setCurrentIndex(index if index >= 0 else 0)

    def refresh_cp_concat_controls(self) -> None:
        """Refresh concat-only controls without discarding other pending edits."""
        if self.tab is None or self.tab.spec.kind != "cp_capacity":
            return
        run_combo = self.controls.get("capacity_percent_reference_run_id")
        if run_combo is not None:
            self._populate_cp_reference_runs(run_combo)
        refresh_cycles = getattr(self, "_cp_concat_refresh_cycles", None)
        if refresh_cycles is not None:
            refresh_cycles()
        refresh_summary = getattr(self, "_cp_concat_refresh_summary", None)
        if refresh_summary is not None:
            refresh_summary()
        update_controls = getattr(self, "_cp_concat_update_controls", None)
        if update_controls is not None:
            update_controls()

    def _on_reference_redraw(self, tab):
        table = getattr(self, "_it_reference_table", None)
        if tab is not self.tab or table is None:
            return
        records = references_from_options(tab.spec.analysis_options)
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            unit = record.get("unit")
            unit_label = unit.get("label", "") if isinstance(unit, dict) else ""
            value = QTableWidgetItem(f"{record.get('value', '')} {unit_label}".strip())
            value.setData(Qt.UserRole, str(record.get("id", "")))
            table.setItem(row, 0, value)
            label = str(record.get("label") or "自动图注")
            if record.get("label_visible", True) is False:
                label = "已关闭（" + label + "）"
            table.setItem(row, 1, QTableWidgetItem(label))

    def bind(self, tab):
        if self._reference_connected_tab is not None:
            try:
                self._reference_connected_tab.rendered.disconnect(self._on_reference_redraw)
            except (RuntimeError, TypeError):
                pass
            self._reference_connected_tab = None
        self.tab = tab
        self._cp_reference_needs_confirmation = False
        self._it_position_controls = {}
        self._it_label_visibility_items = {}
        self._cp_reference_unit_state = None
        self._cp_refresh_unit_controls = None
        self._it_reference_table = None
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
        if spec.kind in ("cv_contribution", "cv_contribution_vs_rate"):
            branch = QComboBox()
            branch.addItem("正扫（电位递增）", "up")
            branch.addItem("反扫（电位递减）", "down")
            branch.setCurrentIndex(max(0, branch.findData(spec.analysis_options.get("dunn_branch", "up"))))
            self.form.addRow("Dunn 扫描支路", branch)
            self.controls["dunn_branch"] = branch
            basis = QComboBox()
            for key, label in BASIS_LABELS.items():
                basis.addItem(label, key)
            basis.setCurrentIndex(max(0, basis.findData(spec.analysis_options.get("dunn_fraction_basis", "fitted"))))
            basis.setToolTip(BASIS_NOTE)
            self.form.addRow("贡献率 100% 基准", basis)
            self.controls["dunn_fraction_basis"] = basis
        if spec.kind == "cv_contribution_vs_rate":
            layout = QComboBox()
            layout.addItem("随基准自动", "auto")
            layout.addItem("并排", "grouped")
            layout.addItem("堆叠（扩散在下）", "stacked")
            layout.setCurrentIndex(max(0, layout.findData(spec.analysis_options.get("dunn_bar_layout", "auto"))))
            layout.setToolTip("自动模式下，拟合分量之和为基准时堆叠，实测净电荷为基准时并排。堆叠时异号分量从零线分别向两侧绘制。")
            self.form.addRow("柱状图布局", layout)
            self.controls["dunn_bar_layout"] = layout
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
        if spec.kind in {"lsv_curve", "it_curve"}:
            entries = (("电压窗口下限 (V)", "lsv_window_low"), ("电压窗口上限 (V)", "lsv_window_high")) if spec.kind == "lsv_curve" else (("参考时间 (s)", "it_reference_time"),)
            for label, key in entries:
                value = spec.analysis_options.get(key)
                edit = QLineEdit("" if value is None else str(value))
                edit.setPlaceholderText("留空不显示")
                if key == "it_reference_time":
                    edit.setToolTip("选择最接近该时间的实测点，绘制电流水平线；不进行插值。")
                self.form.addRow(label, edit)
                self.controls[key] = edit
            prefix = "lsv" if spec.kind == "lsv_curve" else "it"
            display_group = QGroupBox("电流显示")
            display_form = QFormLayout(display_group)
            display_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            display_mode = QComboBox()
            for label, value in (
                ("跟随全局归一化", "follow"),
                ("电流 / 参考面积", "reference_area"),
                ("电流 / 参考电容", "reference_capacitance"),
            ):
                display_mode.addItem(label, value)
            display_mode.setCurrentIndex(
                max(
                    0,
                    display_mode.findData(
                        spec.analysis_options.get(
                            f"{prefix}_current_display", "follow"
                        )
                    ),
                )
            )
            display_mode.setToolTip(
                "参考模式使用原始电流除以输入的参考面积或参考电容，"
                "并忽略顶部的全局面积/质量归一化。"
            )
            display_form.addRow("Y 轴显示", display_mode)
            area_edit = QLineEdit()
            saved_area = spec.analysis_options.get(
                f"{prefix}_reference_area_cm2"
            )
            if saved_area is None:
                source_runs = [
                    run
                    for run in (
                        tab.dataset.lsv_runs
                        if spec.kind == "lsv_curve"
                        else tab.dataset.it_runs
                    )
                    if run.run_id in spec.run_ids
                ]
                areas = [
                    float(run.params.area_cm2)
                    for run in source_runs
                    if run.params.has_area()
                ]
                if areas and len(areas) == len(source_runs) and all(
                    abs(value - areas[0])
                    <= max(1e-12, abs(areas[0]) * 1e-9)
                    for value in areas
                ):
                    saved_area = areas[0]
            if saved_area is not None:
                try:
                    area_edit.setText(f"{float(saved_area):.12g}")
                except (TypeError, ValueError, OverflowError):
                    pass
            area_edit.setPlaceholderText("例如 0.25")
            area_edit.setToolTip(
                "当前图所有选中数据共用的参考面积（cm²）；"
                "留空或非正数将无法应用参考面积模式。"
            )
            display_form.addRow("参考面积 (cm²)", area_edit)
            capacitor_row = QWidget()
            capacitor_layout = QHBoxLayout(capacitor_row)
            capacitor_layout.setContentsMargins(0, 0, 0, 0)
            capacitor_layout.setSpacing(6)
            cap_edit = QLineEdit()
            cap_edit.setPlaceholderText("例如 1.5")
            cap_edit.setToolTip(
                "当前图所有选中数据共用的参考电容；"
                "内部按法拉保存，单位切换时自动换算输入值。"
            )
            cap_unit = QComboBox()
            cap_factors = dict(CAPACITANCE.units)
            saved_cap_unit = canonical_unit(
                spec.analysis_options.get(
                    f"{prefix}_reference_capacitance_unit"
                )
                or "F"
            )
            if saved_cap_unit not in cap_factors:
                saved_cap_unit = "F"
            cap_unit.addItem("F", "F")
            for name in ("mF", "µF", "nF", "pF"):
                cap_unit.addItem(name, name)
            cap_unit.setCurrentIndex(max(0, cap_unit.findData(saved_cap_unit)))
            cap_unit.setToolTip("参考电容输入单位。")
            saved_cap_f = spec.analysis_options.get(
                f"{prefix}_reference_capacitance_f"
            )
            if saved_cap_f is not None:
                try:
                    cap_edit.setText(
                        f"{float(saved_cap_f) * cap_factors[saved_cap_unit]:.12g}"
                    )
                except (TypeError, ValueError, OverflowError):
                    pass
            capacitor_layout.addWidget(cap_edit, 1)
            capacitor_layout.addWidget(cap_unit)
            display_form.addRow("参考电容", capacitor_row)
            display_hint = QLabel()
            display_hint.setWordWrap(True)
            display_hint.setSizePolicy(
                QSizePolicy.Preferred, QSizePolicy.Maximum
            )
            apply_theme_role(display_hint, "hint")
            display_form.addRow(display_hint)
            self.form.addRow(display_group)
            self.controls[f"{prefix}_current_display"] = display_mode
            self.controls[f"{prefix}_reference_area_cm2"] = area_edit
            self.controls[f"{prefix}_reference_capacitance"] = cap_edit
            self.controls[f"{prefix}_reference_capacitance_unit"] = cap_unit
            reference_state = {"unit": saved_cap_unit}
            self._sweep_reference_state = getattr(
                self, "_sweep_reference_state", {}
            )
            self._sweep_reference_state[prefix] = reference_state

            def update_display_controls(*_args):
                mode_value = display_mode.currentData()
                area_edit.setEnabled(mode_value == "reference_area")
                cap_edit.setEnabled(mode_value == "reference_capacitance")
                cap_unit.setEnabled(mode_value == "reference_capacitance")
                if mode_value == "reference_area":
                    display_hint.setText(
                        "使用原始电流 ÷ 参考面积；本图忽略全局面积/质量归一化。"
                    )
                elif mode_value == "reference_capacitance":
                    display_hint.setText(
                        "使用原始电流 ÷ 参考电容；本图忽略全局面积/质量归一化。"
                    )
                else:
                    display_hint.setText(
                        "跟随顶部的全局归一化设置；已有 I-T 图保持原有行为。"
                        if spec.kind == "it_curve"
                        else "跟随顶部的全局归一化设置；已有 LSV 图保持原有行为。"
                    )

            def cap_unit_changed(*_args):
                old_unit = reference_state["unit"]
                new_unit = cap_unit.currentData() or "F"
                text = cap_edit.text().strip()
                if text and old_unit in cap_factors and new_unit in cap_factors:
                    try:
                        base_f = (
                            float(text)
                            / cap_factors[old_unit]
                        )
                        cap_edit.setText(
                            f"{base_f * cap_factors[new_unit]:.12g}"
                        )
                    except (TypeError, ValueError, OverflowError):
                        pass
                reference_state["unit"] = new_unit

            display_mode.currentIndexChanged.connect(update_display_controls)
            cap_unit.currentIndexChanged.connect(cap_unit_changed)
            update_display_controls()
            if spec.kind == "lsv_curve":
                clip_negative = QCheckBox("负电流显示为零")
                clip_negative.setChecked(bool(spec.analysis_options.get("lsv_clip_negative", False)))
                clip_negative.setToolTip("仅改变当前 LSV 图的显示：负电流截为零；不修改原始数据或原始数据导出。")
                self.form.addRow(clip_negative)
                self.controls["lsv_clip_negative"] = clip_negative
            if spec.kind == "it_curve":
                add_reference = QPushButton("添加参考线…")
                apply_button_role(add_reference, "secondary")
                add_reference.clicked.connect(lambda: tab.open_it_reference_manager(add=True))
                self.form.addRow(add_reference)
                table = QTableWidget(0, 2)
                table.setHorizontalHeaderLabels(["参考值", "图注"])
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
                table.verticalHeader().setVisible(False)
                table.setEditTriggers(QAbstractItemView.NoEditTriggers)
                table.setSelectionBehavior(QAbstractItemView.SelectRows)
                table.setMaximumHeight(120)
                table.setToolTip("双击参考线打开管理表；也可双击图上的线或图注。")
                table.cellDoubleClicked.connect(lambda row, _column: tab.open_it_reference_manager(
                    selected_id=table.item(row, 0).data(Qt.UserRole)))
                self.form.addRow(table)
                self._it_reference_table = table
                self._on_reference_redraw(tab)
                tab.rendered.connect(self._on_reference_redraw)
                self._reference_connected_tab = tab
                show_reference_labels = QCheckBox("显示参考时间的点标签")
                show_reference_labels.setChecked(spec.analysis_options.get("it_reference_show_labels", True) is not False)
                show_reference_labels.setToolTip("关闭后仍绘制参考时间对应的水平线和实测点；手动添加的参考线标签不受影响。")
                self.form.addRow(show_reference_labels)
                self.controls["it_reference_show_labels"] = show_reference_labels
                label_mode = QComboBox()
                for label, value in (("时间＋电流", "time_current"), ("仅电流", "current"), ("自定义文字 / 格式", "custom")):
                    label_mode.addItem(label, value)
                label_mode.setCurrentIndex(max(0, label_mode.findData(spec.analysis_options.get("it_reference_label_mode", "time_current"))))
                self.form.addRow("参考点标注", label_mode)
                self.controls["it_reference_label_mode"] = label_mode
                custom_label = QLineEdit(str(spec.analysis_options.get("it_reference_label_text", "")))
                custom_label.setPlaceholderText("例如 I = {current:.2f} {unit}")
                custom_label.setToolTip(r"可用变量：{time}、{current}、{unit}、{name}。支持 {current:.2f}、$I_{ref}$ 和公式外 \n 换行；数学分组中可写 $I_{current:.2f}$。精度最多 12 位，不执行表达式。")
                label_mode.currentIndexChanged.connect(lambda: custom_label.setEnabled(show_reference_labels.isChecked() and label_mode.currentData() == "custom"))
                custom_label.setEnabled(show_reference_labels.isChecked() and label_mode.currentData() == "custom")
                self.form.addRow("自定义标注", custom_label)
                custom_preview = FormattedTextPreview()
                apply_theme_role(custom_preview, "hint")
                def update_custom_preview():
                    try:
                        value = format_template(custom_label.text(), {"time": 1.2, "current": 2.0, "unit": "µA", "name": "示例"}, strict=True)
                        custom_preview.show_preview("格式示例：" + value if value else "")
                    except TemplateError as exc:
                        custom_preview.show_preview("格式无效：" + str(exc))
                custom_label.textChanged.connect(update_custom_preview)
                update_custom_preview()
                self.form.addRow(custom_preview)
                self.controls["it_reference_label_text"] = custom_label
                number_format = QComboBox()
                for text, value in (("自动（4 位有效数字）", "auto"), ("有效数字", "significant"),
                                    ("固定小数位", "fixed"), ("科学计数法", "scientific")):
                    number_format.addItem(text, value)
                number_format.setCurrentIndex(max(0, number_format.findData(spec.analysis_options.get("it_reference_number_format", "auto"))))
                self.form.addRow("标注数值格式", number_format)
                self.controls["it_reference_number_format"] = number_format
                digits = QSpinBox()
                digits.setRange(0, 10)
                try:
                    digits.setValue(int(spec.analysis_options.get("it_reference_digits", 4)))
                except (TypeError, ValueError, OverflowError):
                    digits.setValue(4)
                digits.setToolTip("有效数字模式控制有效位数；固定小数和科学计数法控制小数位数。")
                def update_digits():
                    digits.setMinimum(1 if number_format.currentData() == "significant" else 0)
                    digits.setEnabled(show_reference_labels.isChecked() and number_format.currentData() != "auto")
                number_format.currentIndexChanged.connect(update_digits)
                update_digits()
                self.form.addRow("数值位数", digits)
                self.controls["it_reference_digits"] = digits
                current_unit = QComboBox()
                for text, value in (("跟随电流轴", "axis"), ("原单位", "original"), ("自动选择", "auto"),
                                    ("A", "A"), ("mA", "mA"), ("µA", "µA"), ("nA", "nA"), ("pA", "pA")):
                    current_unit.addItem(text, value)
                current_unit.setCurrentIndex(max(0, current_unit.findData(spec.analysis_options.get("it_reference_current_unit", "axis"))))
                current_unit.setToolTip(
                    "仅改变参考点标注的单位；面积归一化附加 /cm²，"
                    "参考电容显示附加 /F，质量归一化附加 /g。"
                )
                self.form.addRow("标注电流单位", current_unit)
                self.controls["it_reference_current_unit"] = current_unit
                position_mode = QComboBox()
                position_mode.addItem("自动避让", "auto")
                position_mode.addItem("手动指定", "manual")
                position_mode.setCurrentIndex(max(0, position_mode.findData(spec.analysis_options.get("it_reference_position", "auto"))))
                position_mode.setToolTip("自动位置会尽量避开绘图区边缘、图例和其他标注；手动位置为绘图区内的百分比。")
                self.form.addRow("标注位置", position_mode)
                self.controls["it_reference_position"] = position_mode
                position_hint = QLabel("逐条控制标签显示；手动位置按绘图区百分比，左下为 0%，右上为 100%。")
                position_hint.setWordWrap(True)
                position_hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
                apply_theme_role(position_hint, "hint")
                self.form.addRow(position_hint)
                table = QTableWidget(0, 4)
                table.setHorizontalHeaderLabels(("数据", "显示", "X", "Y"))
                table.verticalHeader().setVisible(False)
                table.setSelectionMode(QAbstractItemView.NoSelection)
                table.setWordWrap(False)
                table.setTextElideMode(Qt.ElideMiddle)
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
                table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
                table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
                table.setColumnWidth(1, 52)
                table.setColumnWidth(2, 75)
                table.setColumnWidth(3, 75)
                table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                saved_positions = spec.analysis_options.get("it_reference_positions", {})
                if not isinstance(saved_positions, dict):
                    saved_positions = {}
                saved_visibility = spec.analysis_options.get("it_reference_label_visibility", {})
                if not isinstance(saved_visibility, dict):
                    saved_visibility = {}
                selected_runs = [run for run in tab.dataset.it_runs if run.run_id in spec.run_ids]
                point_size = self.font().pointSizeF()
                if point_size <= 0:
                    point_size = BASE_FONT_SIZE
                tokens = UiTokens.from_scale(point_size / BASE_FONT_SIZE)
                table_row_height = max(tokens.row_height, tokens.control_height)
                table.setFixedHeight(
                    table.horizontalHeader().sizeHint().height()
                    + min(max(len(selected_runs), 1), 4) * table_row_height
                    + 2 * table.frameWidth()
                )
                for index, run in enumerate(selected_runs):
                    table.insertRow(index)
                    item = QTableWidgetItem(run.display_name)
                    item.setToolTip(run.display_name)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(index, 0, item)
                    visibility = QTableWidgetItem()
                    visibility.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    visibility.setCheckState(Qt.Unchecked if saved_visibility.get(run.run_id, True) is False else Qt.Checked)
                    visibility.setToolTip("控制该数据对应的参考时间标签；不影响水平线或实测点。")
                    table.setItem(index, 1, visibility)
                    self._it_label_visibility_items[run.run_id] = visibility
                    default = (75., max(10., 85. - index * 12.))
                    position = saved_positions.get(run.run_id, default)
                    widgets = []
                    for column in range(2):
                        spin = QDoubleSpinBox()
                        spin.setRange(0., 100.)
                        spin.setDecimals(1)
                        spin.setSuffix(" %")
                        try:
                            spin.setValue(float(position[column]))
                        except (ValueError, TypeError, IndexError, KeyError, OverflowError):
                            spin.setValue(default[column])
                        table.setCellWidget(index, column + 2, spin)
                        widgets.append(spin)
                    self._it_position_controls[run.run_id] = tuple(widgets)
                self.form.addRow(table)
                leader = QCheckBox("手动位置显示参考点引线")
                leader.setChecked(bool(spec.analysis_options.get("it_reference_leader", False)))
                self.form.addRow(leader)
                self.controls["it_reference_leader"] = leader
                def update_position_controls():
                    enabled = show_reference_labels.isChecked()
                    manual = enabled and position_mode.currentData() == "manual"
                    position_hint.setVisible(enabled)
                    table.setVisible(enabled)
                    leader.setVisible(manual)
                    label_mode.setEnabled(enabled)
                    custom_label.setEnabled(enabled and label_mode.currentData() == "custom")
                    number_format.setEnabled(enabled)
                    update_digits()
                    current_unit.setEnabled(enabled)
                    position_mode.setEnabled(enabled)
                    for controls in self._it_position_controls.values():
                        for spin in controls:
                            spin.setEnabled(manual)
                position_mode.currentIndexChanged.connect(update_position_controls)
                show_reference_labels.toggled.connect(update_position_controls)
                update_position_controls()
        if spec.kind.startswith("cp_"):
            cp_options = (
                ("电位-时间自动补全保持区间", "complete_holds", True),
                ("容量计入恒压保持段", "include_holds", False),
                ("容量-循环图显示库伦效率", "show_efficiency", True),
            )
            cp_tooltips = {
                "complete_holds": (
                    "文件包含 Hold Time/Current 块时，在每个活动电流段后"
                    "插入高/低电位保持平台；保持段电流仍用于容量分解。"
                ),
                "include_holds": (
                    "关闭时只用恒流活动段计算容量；开启时把保持段电流积分"
                    "计入充电/放电容量。"
                ),
                "show_efficiency": "在容量-循环图右侧绘制库伦效率曲线。",
            }
            for label, key, default in cp_options:
                if key in {"include_holds", "show_charge", "show_efficiency"} and spec.kind != "cp_capacity":
                    continue
                if key == "complete_holds" and spec.kind != "cp_gcd":
                    continue
                cb = QCheckBox(label)
                cb.setChecked(bool(spec.analysis_options.get(key, default)))
                cb.setToolTip(cp_tooltips.get(key, ""))
                self.form.addRow(cb)
                self.controls[key] = cb
            if spec.kind == "cp_capacity":
                quantity = QComboBox()
                quantity.addItem("容量（电荷）", "capacity")
                quantity.addItem("电容（Q/ΔV）", "capacitance")
                quantity.setCurrentIndex(max(0, quantity.findData(spec.analysis_options.get("cp_quantity", "capacity"))))
                quantity.setToolTip("电容按每段充放电电荷除以该段实测电位差计算；保持段是否计入电荷由上方选项控制。")
                self.form.addRow("纵轴量", quantity)
                self.controls["cp_quantity"] = quantity
                normalization = spec.normalization
                runs = [run for run in tab.dataset.cp_runs if run.run_id in spec.run_ids]
                if normalization == "area" and not all(run.params.has_area() for run in runs):
                    normalization = "none"
                if normalization == "mass" and not all(run.params.has_mass() for run in runs):
                    normalization = "none"
                unit_combo = QComboBox()
                unit_combo.addItem("自动", "auto")
                for name, factor in cp_plot_units(quantity.currentData(), normalization):
                    unit_combo.addItem(name, name)
                saved_unit = canonical_unit(spec.analysis_options.get("cp_display_unit"))
                unit_index = unit_combo.findData(saved_unit or cp_plot_units(quantity.currentData(), normalization)[0][0])
                self._cp_reference_needs_confirmation = bool(saved_unit and unit_index < 0)
                unit_combo.setCurrentIndex(unit_index if unit_index >= 0 else 0)
                self.form.addRow("显示与参考单位", unit_combo)
                self.controls["cp_display_unit"] = unit_combo
                series = QComboBox()
                for label, value in (("充电与放电", "both"), ("仅充电", "charge"),
                                     ("仅放电", "discharge"), ("充放电平均", "mean")):
                    series.addItem(label, value)
                previous = spec.analysis_options.get("capacity_series", "both" if spec.analysis_options.get("show_charge", True) else "discharge")
                series.setCurrentIndex(max(0, series.findData(previous)))
                self.form.addRow("容量显示", series)
                self.controls["capacity_series"] = series
                concat_group = QGroupBox("跨文件拼接")
                concat_layout = QFormLayout(concat_group)
                concat_layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
                concat_enabled = QCheckBox("拼接所选 CP 文件的循环")
                concat_enabled.setToolTip(
                    "把本图选中的多个 CP 文件按下方顺序和循环范围接成一条容量-循环曲线；"
                    "编号方式与各文件范围可在“设置各文件循环范围”中调整。"
                )
                concat_enabled.setChecked(
                    bool(spec.analysis_options.get("cp_concat_enabled", False))
                )
                concat_layout.addRow(concat_enabled)
                self.controls["cp_concat_enabled"] = concat_enabled
                concat_mode = QComboBox()
                concat_mode.addItem("连续重编号（1..N）", "sequential")
                concat_mode.addItem("按实际累计编号（保留空号）", "cumulative")
                concat_mode.setCurrentIndex(
                    max(
                        0,
                        concat_mode.findData(
                            spec.analysis_options.get("cp_concat_cycle_mode", "sequential")
                        ),
                    )
                )
                concat_mode.setToolTip(
                    "连续编号把参与循环从 1 编到 N；实际累计编号保留各文件中的循环编号和空号。"
                )
                concat_layout.addRow("循环编号", concat_mode)
                self.controls["cp_concat_cycle_mode"] = concat_mode
                concat_button = QPushButton("设置各文件循环范围...")
                apply_button_role(concat_button, "secondary")
                concat_button.setToolTip(
                    "调整本图中 CP 文件的拼接顺序，并设置每个文件参与绘制的循环范围。"
                )
                concat_button.clicked.connect(
                    lambda: self.cp_concat_settings_requested.emit()
                )
                concat_layout.addRow(concat_button)
                self.cp_concat_button = concat_button
                concat_summary = QLabel()
                concat_summary.setWordWrap(True)
                concat_summary.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.Maximum
                )
                apply_theme_role(concat_summary, "hint")
                concat_layout.addRow(concat_summary)
                self.cp_concat_summary = concat_summary
                self.form.addRow(concat_group)
                mode = QComboBox()
                for label, value in (("实际数值", "absolute"), ("百分比：手动", "manual"),
                                     ("百分比：各文件按循环", "cycle"),
                                     ("百分比：统一参考循环", "unified")):
                    mode.addItem(label, value)
                mode.setCurrentIndex(max(0, mode.findData(spec.analysis_options.get("capacity_percent_mode", "absolute"))))
                mode.setToolTip(
                    "参考值对应所选的容量或电容；各文件按循环模式为每个文件分别使用其参考循环的对应值作为 100%，"
                    "可能产生多个 100% 点；统一参考循环模式让所有文件共用同一文件+Cycle 基准。"
                )
                self.form.addRow("容量标度", mode)
                self.controls["capacity_percent_mode"] = mode
                for label, key, default in (("100% 参考值", "capacity_percent_reference", ""),
                                            ("参考循环编号", "capacity_percent_cycle", "1")):
                    value = spec.analysis_options.get(key, default)
                    edit = QLineEdit("" if value is None else str(value))
                    self.form.addRow(label, edit)
                    self.controls[key] = edit
                def confirm_reference(_text):
                    self._cp_reference_needs_confirmation = False
                    reference_state["unit"] = current_physical_unit()
                    update_reference_unit()
                self.controls["capacity_percent_reference"].textEdited.connect(confirm_reference)
                exponent = QComboBox()
                for power in range(-12, 7):
                    exponent.addItem("×1（当前单位）" if power == 0 else f"×10^{power}", power)
                exponent_index = exponent.findData(spec.analysis_options.get("capacity_percent_reference_exponent", 0))
                exponent.setCurrentIndex(exponent_index if exponent_index >= 0 else exponent.findData(0))
                exponent.setToolTip("手动参考值乘以该倍率；例如图中刻度为 1.65 且标注 1e−7 时，填写 1.65 并选择 ×10^-7。也可直接输入 1.65e-7 并选择 ×1。")
                self.form.addRow("参考值倍率", exponent)
                self.controls["capacity_percent_reference_exponent"] = exponent

                unified_group = QGroupBox("统一参考循环")
                unified_form = QFormLayout(unified_group)
                unified_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
                ref_run_combo = QComboBox()
                ref_run_combo.setToolTip(
                    "选择作为统一 100% 基准的 CP 文件；只列出当前图选中的 CP 数据。"
                )
                ref_cycle_combo = QComboBox()
                ref_cycle_combo.setToolTip(
                    "选择参考 Cycle；只列出该文件当前拼接显示范围内的循环。"
                )
                for combo in (ref_run_combo, ref_cycle_combo):
                    combo.setSizeAdjustPolicy(
                        QComboBox.AdjustToMinimumContentsLengthWithIcon
                    )
                    combo.setMinimumContentsLength(10)
                    combo.setSizePolicy(
                        QSizePolicy.Expanding, QSizePolicy.Fixed
                    )
                unified_preview = QLabel()
                unified_preview.setWordWrap(True)
                unified_preview.setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.Maximum
                )
                unified_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
                apply_theme_role(unified_preview, "hint")
                unified_form.addRow("参考文件", ref_run_combo)
                unified_form.addRow("参考 Cycle", ref_cycle_combo)
                unified_form.addRow("参考值预览", unified_preview)
                self.form.addRow(unified_group)
                self.controls["capacity_percent_reference_run_id"] = ref_run_combo
                self.controls["capacity_percent_reference_cycle"] = ref_cycle_combo
                self.cp_unified_preview = unified_preview
                self._populate_cp_reference_runs(ref_run_combo)
                saved_ref_id = str(
                    spec.analysis_options.get("capacity_percent_reference_run_id")
                    or ""
                )

                def displayed_unified_cycles(run_id):
                    if not run_id:
                        return []
                    live_runs, live_summaries = self._cp_live_context()
                    summary = live_summaries.get(str(run_id))
                    if summary is None:
                        return []
                    if not concat_enabled.isChecked():
                        return list(summary.cycles)
                    _order, ranges = normalize_cp_concat_config(
                        live_runs,
                        live_summaries,
                        order=spec.analysis_options.get("cp_concat_order"),
                        ranges=spec.analysis_options.get("cp_concat_ranges"),
                    )
                    bounds = ranges.get(str(run_id))
                    if bounds is None:
                        return []
                    return [
                        cycle
                        for cycle in summary.cycles
                        if bounds["start"] <= cycle.index <= bounds["end"]
                    ]

                def update_unified_preview(*_args):
                    run_id = ref_run_combo.currentData()
                    cycle_index = ref_cycle_combo.currentData()
                    if not run_id or cycle_index is None:
                        unified_preview.setText("请选择参考文件和参考循环。")
                        return
                    run = (
                        self.tab.dataset.find_cp(str(run_id))
                        if self.tab is not None
                        else None
                    )
                    if run is None:
                        unified_preview.setText("参考文件不在当前图中。")
                        return
                    values = cp_cycle_values(
                        run,
                        self._cp_run_summary(run),
                        quantity=quantity.currentData(),
                        normalization=normalization,
                        include_holds=self.controls["include_holds"].isChecked(),
                    )
                    value = find_cp_cycle_value(values, cycle_index)
                    if value is None:
                        unified_preview.setText(
                            f"Cycle {cycle_index} 没有可用的容量/电容数值。"
                        )
                        return
                    unit = current_physical_unit()
                    factor = dict(
                        cp_plot_units(quantity.currentData(), normalization)
                    ).get(unit, 1.0)

                    def fmt(number):
                        if not math.isfinite(number):
                            return "—"
                        return f"{number * factor:.4g} {unit}"

                    unified_preview.setText(
                        f"Cycle {cycle_index}：充电 {fmt(value.charge)}；"
                        f"放电 {fmt(value.discharge)}；平均 {fmt(value.mean)}"
                    )

                def refresh_unified_cycles(*_args):
                    run_id = ref_run_combo.currentData()
                    previous = ref_cycle_combo.currentData()
                    saved_cycle = spec.analysis_options.get(
                        "capacity_percent_reference_cycle"
                    )
                    with QSignalBlocker(ref_cycle_combo):
                        ref_cycle_combo.clear()
                        for cycle in displayed_unified_cycles(run_id):
                            ref_cycle_combo.addItem(
                                f"Cycle {cycle.index}", int(cycle.index)
                            )
                        if ref_cycle_combo.count() == 0:
                            ref_cycle_combo.addItem("（范围内没有循环）", None)
                        target = previous
                        if run_id == saved_ref_id and saved_cycle is not None:
                            try:
                                target = int(saved_cycle)
                            except (TypeError, ValueError, OverflowError):
                                target = previous
                        index = (
                            ref_cycle_combo.findData(target)
                            if target is not None
                            else -1
                        )
                        ref_cycle_combo.setCurrentIndex(index if index >= 0 else 0)
                    update_unified_preview()
                    update_reference_controls()

                def update_concat_summary(*_args):
                    live_runs, summaries = self._cp_live_context()
                    order, ranges = normalize_cp_concat_config(
                        live_runs,
                        summaries,
                        order=spec.analysis_options.get("cp_concat_order"),
                        ranges=spec.analysis_options.get("cp_concat_ranges"),
                    )
                    entries = cp_concat_entries(
                        live_runs, summaries, order=order, ranges=ranges
                    )
                    cycle_count = sum(
                        entry.included_count for entry in entries
                    )
                    numbering = (
                        "连续编号"
                        if concat_mode.currentData() == "sequential"
                        else "实际累计编号"
                    )
                    prefix = "" if concat_enabled.isChecked() else "未启用拼接；"
                    concat_summary.setText(
                        f"{prefix}{len(entries)} 个 CP 文件，"
                        f"{cycle_count} 个参与循环；{numbering}"
                    )

                def update_reference_controls():
                    self.controls["capacity_percent_reference"].setEnabled(mode.currentData() == "manual")
                    exponent.setEnabled(mode.currentData() == "manual")
                    self.controls["capacity_percent_cycle"].setEnabled(mode.currentData() == "cycle")
                    unified = mode.currentData() == "unified"
                    unified_group.setVisible(unified)
                    ref_run_combo.setEnabled(unified and ref_run_combo.count() > 0)
                    ref_cycle_combo.setEnabled(
                        unified and ref_cycle_combo.currentData() is not None
                    )
                mode.currentIndexChanged.connect(update_reference_controls)
                update_reference_controls()
                self._cp_concat_refresh_cycles = refresh_unified_cycles
                self._cp_concat_refresh_summary = update_concat_summary
                self._cp_concat_update_controls = update_reference_controls
                unit_hint = QLabel()
                unit_hint.setWordWrap(True)
                apply_theme_role(unit_hint, "hint")
                auto_unit_cache = {}
                def current_physical_unit():
                    if unit_combo.currentData() == "auto":
                        live_runs = [run for run in tab.dataset.cp_runs if run.run_id in tab.spec.run_ids]
                        summaries = [(run, run.summary if isinstance(run.summary, CPRunSummary) else analyze_cp_run(run))
                                     for run in live_runs]
                        include = self.controls["include_holds"].isChecked()
                        key = (quantity.currentData(), normalization, include,
                               tuple((run.run_id, id(summary)) for run, summary in summaries))
                        if key not in auto_unit_cache:
                            auto_unit_cache.clear()
                            auto_unit_cache[key] = cp_automatic_unit(summaries, quantity.currentData(), normalization, include)
                        return auto_unit_cache[key]
                    return unit_combo.currentData()
                selected_unit = current_physical_unit()
                saved_reference_unit = canonical_unit(spec.analysis_options.get("capacity_percent_reference_unit") or selected_unit)
                reference_state = {"unit": saved_reference_unit}
                self._cp_reference_unit_state = reference_state
                if saved_reference_unit not in dict(cp_plot_units(quantity.currentData(), normalization)):
                    self._cp_reference_needs_confirmation = True
                def update_reference_unit():
                    selected = current_physical_unit()
                    unit_combo.setItemText(0, f"自动（当前：{selected}）" if unit_combo.currentData() == "auto" else "自动")
                    hint_role = (
                        "warning"
                        if self._cp_reference_needs_confirmation
                        and mode.currentData() == "manual"
                        else "hint"
                    )
                    if unit_hint.property("themeRole") != hint_role:
                        apply_theme_role(unit_hint, hint_role)
                    if mode.currentData() == "unified":
                        unit_hint.setText(
                            "统一参考循环从本图所选 CP 文件的当前显示范围中读取；"
                            "充放电和平均曲线共用同一组参考值。"
                        )
                        return
                    if self._cp_reference_needs_confirmation:
                        unit_hint.setText("容量类型或归一化方式已变化，请重新填写手动参考值。")
                        return
                    if mode.currentData() == "cycle":
                        if concat_enabled.isChecked():
                            unit_hint.setText(
                                "各文件按循环模式会为每个 CP 文件分别使用其参考循环作为 100%，"
                                "因此可能产生多个 100% 点；跨文件统一基准请选择“统一参考循环”。"
                            )
                        else:
                            unit_hint.setText("参考循环中，充电和放电各自为 100%；平均曲线使用该循环的平均值。")
                        return
                    if mode.currentData() == "absolute":
                        unit_hint.setText("可选择手动参考值或参考循环，以百分比显示。")
                        return
                    unit = selected
                    unit_hint.setText(f"手动参考值单位：{unit}。若图表使用科学计数法，请同时设置倍率。")
                def unit_changed():
                    factors = dict(cp_plot_units(quantity.currentData(), normalization))
                    new_unit = current_physical_unit()
                    new_factor = factors.get(new_unit, 1.0)
                    text = self.controls["capacity_percent_reference"].text().strip()
                    if text and mode.currentData() == "manual" and not self._cp_reference_needs_confirmation:
                        try:
                            scaled = float(text) * 10.0 ** int(exponent.currentData()) * new_factor / factors[reference_state["unit"]]
                            if math.isfinite(scaled):
                                self.controls["capacity_percent_reference"].setText(f"{scaled:.12g}")
                                exponent.setCurrentIndex(exponent.findData(0))
                                reference_state["unit"] = new_unit
                            else:
                                self._cp_reference_needs_confirmation = True
                        except (ValueError, TypeError, OverflowError, ZeroDivisionError, KeyError):
                            self._cp_reference_needs_confirmation = True
                    elif not text:
                        reference_state["unit"] = new_unit
                    update_reference_unit()
                    update_unified_preview()
                def quantity_changed():
                    self._cp_reference_needs_confirmation = True
                    with QSignalBlocker(unit_combo):
                        unit_combo.clear()
                        unit_combo.addItem("自动", "auto")
                        for name, factor in cp_plot_units(quantity.currentData(), normalization):
                            unit_combo.addItem(name, name)
                    reference_state["unit"] = current_physical_unit()
                    update_reference_unit()
                unit_combo.currentIndexChanged.connect(unit_changed)
                quantity.currentIndexChanged.connect(quantity_changed)
                mode.currentIndexChanged.connect(unit_changed)
                self.controls["include_holds"].toggled.connect(lambda: unit_changed() if unit_combo.currentData() == "auto" else None)
                concat_enabled.toggled.connect(update_concat_summary)
                concat_enabled.toggled.connect(refresh_unified_cycles)
                concat_mode.currentIndexChanged.connect(update_concat_summary)
                ref_run_combo.currentIndexChanged.connect(refresh_unified_cycles)
                ref_cycle_combo.currentIndexChanged.connect(update_unified_preview)
                unit_combo.currentIndexChanged.connect(update_unified_preview)
                quantity.currentIndexChanged.connect(update_unified_preview)
                self.controls["include_holds"].toggled.connect(update_unified_preview)
                def refresh_cp_units():
                    nonlocal normalization
                    live_runs = [run for run in tab.dataset.cp_runs if run.run_id in tab.spec.run_ids]
                    new_normalization = tab.spec.normalization
                    if new_normalization == "area" and not all(run.params.has_area() for run in live_runs):
                        new_normalization = "none"
                    if new_normalization == "mass" and not all(run.params.has_mass() for run in live_runs):
                        new_normalization = "none"
                    if new_normalization != normalization:
                        previous_unit = unit_combo.currentData()
                        normalization = new_normalization
                        with QSignalBlocker(unit_combo):
                            unit_combo.clear()
                            unit_combo.addItem("自动", "auto")
                            for name, _factor in cp_plot_units(quantity.currentData(), normalization):
                                unit_combo.addItem(name, name)
                            suffix = "/cm²" if normalization == "area" else "/g" if normalization == "mass" else ""
                            base = str(previous_unit or "").split("/")[0]
                            selected = "auto" if previous_unit == "auto" else base + suffix
                            index = unit_combo.findData(selected)
                            unit_combo.setCurrentIndex(index if index >= 0 else 0)
                        if self.controls["capacity_percent_reference"].text().strip():
                            self._cp_reference_needs_confirmation = True
                        else:
                            reference_state["unit"] = current_physical_unit()
                    unit_changed()
                self._cp_refresh_unit_controls = refresh_cp_units
                unit_changed()
                update_reference_unit()
                update_concat_summary()
                refresh_unified_cycles()
                self.form.addRow(unit_hint)
        for label, key in (("显示图例", "show_legend"), ("显示坐标轴", "show_axes"), ("显示分析注释", "annotations")):
            cb = QCheckBox(label)
            cb.setChecked(getattr(spec, key))
            self.form.addRow(cb)
            self.controls[key] = cb
        if spec.kind == "cp_capacity":
            legend_group = QGroupBox("容量–循环图图例")
            legend_form = QFormLayout(legend_group)
            legend_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            hint = QLabel("留空使用默认内容；{label}、{name}、{quantity}、{unit} 可引用数据名、完整名称、量和单位；输入 { } 隐藏该项。" + r" 支持 $...$ 数学公式和公式外 \n 换行。")
            hint.setWordWrap(True)
            hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            legend_form.addRow(hint)
            cp_legend_preview = FormattedTextPreview()
            apply_theme_role(cp_legend_preview, "hint")
            for label, role in (("充电", "charge"), ("放电", "discharge"),
                                ("充放电平均", "mean"), ("库伦效率", "efficiency")):
                key = f"cp_legend_{role}"
                edit = QLineEdit(str(spec.analysis_options.get(key, "")))
                edit.setPlaceholderText("默认图例")
                def preview_cp_legend(text):
                    if text.strip() == "{ }":
                        cp_legend_preview.show_preview("不显示该图例")
                        return
                    try:
                        preview = format_template(text, {"label": "Sample", "name": "Sample", "quantity": "Capacity", "unit": "µAh"}, strict=True)
                        cp_legend_preview.show_preview(preview)
                    except TemplateError as exc:
                        cp_legend_preview.show_preview("格式无效：" + str(exc))
                edit.textChanged.connect(preview_cp_legend)
                legend_form.addRow(label, edit)
                self.controls[key] = edit
            legend_form.addRow(cp_legend_preview)
            self.form.addRow(legend_group)
            self.controls["show_legend"].toggled.connect(legend_group.setVisible)
            legend_group.setVisible(self.controls["show_legend"].isChecked())
        if spec.kind == "cv_overlay":
            try:
                legend_limit = int(
                    spec.analysis_options.get(
                        "legend_cycle_limit", DEFAULT_CYCLE_LEGEND_LIMIT
                    )
                )
            except (TypeError, ValueError, OverflowError):
                legend_limit = DEFAULT_CYCLE_LEGEND_LIMIT
            control = self.spin(0, 500, max(0, min(500, legend_limit)))
            control.setDecimals(0)
            control.setSingleStep(1)
            control.setToolTip(
                "单个 CV 数据的循环图例上限。超过上限时按连续循环范围合并；"
                "例如 500 个循环、上限 10 时显示 1-50、51-100……；0 表示不合并。"
            )
            self.form.addRow("循环图例上限", control)
            self.controls["legend_cycle_limit"] = control
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
    def _unit_family_specs(spec, figure=None):
        kind = spec.kind
        normalization = spec.normalization
        if figure is not None and figure.axes:
            index = 1 if kind == "eis_bode" and len(figure.axes) > 1 else 0
            dimension = axis_display_dimensions(figure.axes[index]).get("y")
            if dimension is not None:
                normalization = "area" if dimension.endswith("_area") else "mass" if dimension.endswith("_mass") else "none"
        if kind.startswith("eis_"):
            family = IMPEDANCE_AREA if normalization == "area" else IMPEDANCE
            return [("impedance", "阻抗单位", family)]
        if kind in {
            "cv_overlay",
            "cv_current_scan",
            "cv_bvalue",
            "cv_contribution",
        }:
            return [("current", "电流单位", current_family(normalization))]
        if kind in {"lsv_curve", "it_curve"}:
            prefix = "lsv" if kind == "lsv_curve" else "it"
            display_mode = spec.analysis_options.get(
                f"{prefix}_current_display", "follow"
            )
            cap_unit = canonical_unit(
                spec.analysis_options.get(
                    f"{prefix}_reference_capacitance_unit"
                )
                or "F"
            )
            if unit_factor(CAPACITANCE, cap_unit) is None:
                cap_unit = "F"
            return [
                (
                    "current",
                    "电流轴单位",
                    sweep_current_family(
                        display_mode, normalization, cap_unit
                    ),
                )
            ]
        if kind == "cv_cap_scan":
            return [("capacitance", "电容单位", capacitance_family(normalization))]
        if kind == "cv_trasatti":
            return [("charge", "电荷单位", charge_family(normalization))]
        if kind == "cp_gcd":
            return [("current", "电流单位", CURRENT)]
        return []

    def _clear_unit_controls(self) -> None:
        while self.unit_form.rowCount():
            self.unit_form.removeRow(0)

    def _rebuild_unit_controls(self, tab) -> None:
        pending_units = {
            key: combo.currentData()
            for key, combo in self.unit_controls.items()
        }
        self._clear_unit_controls()
        self.unit_controls = {}
        if tab is None:
            self._unit_controls_signature = ()
            self.unit_host.setVisible(False)
            return
        specs = self._unit_family_specs(tab.spec, tab.figure)
        self._unit_controls_signature = tuple((key, tuple(unit_labels(family))) for key, _, family in specs)
        overrides = tab.spec.analysis_options.get("unit_overrides")
        overrides = overrides if isinstance(overrides, dict) else {}
        for key, label, family in specs:
            combo = QComboBox()
            if tab.spec.kind in {"lsv_curve", "it_curve"}:
                combo.addItem("原始单位（兼容旧图）", "legacy")
            combo.addItem("自动", "auto")
            for unit in unit_labels(family):
                combo.addItem(unit, unit)
            pending = pending_units.get(key)
            selected = (
                pending
                if pending is not None and combo.findData(pending) >= 0
                else overrides.get(key)
            )
            index = combo.findData(selected) if selected else 0
            combo.setCurrentIndex(max(0, index))
            combo.setToolTip(
                "自动按数据量级选择显示单位；手动指定后点击“应用到当前图”生效，"
                "已有坐标范围会按物理值自动换算。"
            )
            self.unit_form.addRow(label + ":", combo)
            self.unit_controls[key] = combo
        self.unit_host.setVisible(bool(specs))

    def refresh_unit_choices(self) -> None:
        if self.tab is None:
            return
        specs = self._unit_family_specs(self.tab.spec, self.tab.figure)
        signature = tuple((key, tuple(unit_labels(family))) for key, _, family in specs)
        if signature != self._unit_controls_signature:
            self._rebuild_unit_controls(self.tab)

    def _sync_axis_limit_units(self, tab) -> None:
        """Keep stored limits displayed in the unit currently shown on screen."""
        if tab is None:
            return
        sync_axis_limit_units(tab.figure, tab.spec.kind, tab.spec.analysis_options)

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
            dimensions = axis_display_dimensions(ax)
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
                    if dimensions.get(side) is not None:
                        side_units[side]["dimension"] = dimensions[side]
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
        self._axis_unit_snapshots = {}
        self._axis_range_labels = {}
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
            dimensions = (axis_display_dimensions(tab.figure.axes[spec.index])
                          if spec.index < len(tab.figure.axes) else {})
            self._axis_unit_snapshots[spec.key] = {
                side: {"label": value[0], "factor": value[1], "dimension": dimensions.get(side)}
                for side, value in displayed.items()
            }
            labels = {}
            controls: dict[str, QLineEdit] = {}
            if spec.editable_x:
                row, low, high = self._axis_range_row(values, "x")
                unit = displayed.get("x")
                label = "X 轴范围" + (f" ({unit[0]})" if unit else "") + ":"
                labels["x"] = QLabel(label)
                form.addRow(labels["x"], row)
                controls["x_min"] = low
                controls["x_max"] = high
            else:
                note = QLabel("X 轴与左轴共享，仅设置 Y 范围。")
                apply_theme_role(note, "hint")
                form.addRow(note)
            if spec.editable_y:
                row, low, high = self._axis_range_row(values, "y")
                unit = displayed.get("y")
                label = "Y 轴范围" + (f" ({unit[0]})" if unit else "") + ":"
                labels["y"] = QLabel(label)
                form.addRow(labels["y"], row)
                controls["y_min"] = low
                controls["y_max"] = high
            else:
                note = QLabel("该轴范围由其他栏目控制。")
                apply_theme_role(note, "hint")
                form.addRow(note)
            self.axis_sections_layout.addWidget(group)
            self.axis_controls[spec.key] = controls
            self._axis_range_labels[spec.key] = labels
        self.axis_sections_layout.addStretch(1)

    def refresh_axis_units(self) -> None:
        """Reconcile unsaved range inputs when a redraw changes their units."""
        tab = self.tab
        if tab is None or not self.axis_controls:
            return
        current = {}
        for spec in self.axis_specs:
            if spec.index >= len(tab.figure.axes):
                continue
            ax = tab.figure.axes[spec.index]
            dims = axis_display_dimensions(ax)
            current[spec.key] = {
                side: {"label": unit[0], "factor": unit[1], "dimension": dims.get(side)}
                for side, unit in axis_display_units(ax).items()
            }
        if current == self._axis_unit_snapshots:
            return
        temporary = {
            "axis_limits": {key: {field: edit.text().strip() for field, edit in controls.items()
                                     if edit.text().strip()}
                            for key, controls in self.axis_controls.items()},
            "axis_limit_units": {key: dict(value) for key, value in self._axis_unit_snapshots.items()},
        }
        warnings = sync_axis_limit_units(tab.figure, tab.spec.kind, temporary)
        for key, controls in self.axis_controls.items():
            values = temporary.get("axis_limits", {}).get(key, {})
            for field, edit in controls.items():
                if not edit.text().strip():
                    continue
                value = values.get(field)
                if value is None:
                    edit.clear()
                elif isinstance(value, (int, float)):
                    edit.setText(f"{value:.12g}")
            for side, label in self._axis_range_labels.get(key, {}).items():
                info = current.get(key, {}).get(side)
                label.setText(f"{side.upper()} 轴范围" + (f" ({info['label']})" if info else "") + ":")
        self._axis_unit_snapshots = current
        if warnings:
            apply_theme_role(self.error, "error")
            self.error.setText("；".join(warnings))

    def refresh_dynamic_units(self) -> None:
        if self._cp_refresh_unit_controls is not None:
            self._cp_refresh_unit_controls()

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
                    percent_mode = self.controls.get("capacity_percent_mode")
                    if (
                        key
                        in (
                            "capacity_percent_reference_run_id",
                            "capacity_percent_reference_cycle",
                        )
                        and percent_mode is not None
                        and percent_mode.currentData() != "unified"
                    ):
                        continue
                    analysis[key] = control.currentData()
                elif key in (
                    "fit_line",
                    "error_bars",
                    "complete_holds",
                    "include_holds",
                    "show_charge",
                    "show_efficiency",
                    "lsv_clip_negative",
                    "cp_concat_enabled",
                ):
                    analysis[key] = control.isChecked()
                elif key == "legend_cycle_limit":
                    analysis[key] = int(round(control.value()))
                elif key == "it_reference_digits":
                    analysis[key] = int(control.value())
                elif key in ("it_reference_leader", "it_reference_show_labels"):
                    analysis[key] = control.isChecked()
                elif isinstance(control, QCheckBox):
                    changes[key] = control.isChecked()
                elif key == "it_reference_label_text" or key.startswith("cp_legend_"):
                    context = ({"time": 1.2, "current": 2.0, "unit": "µA", "name": "示例"}
                               if key == "it_reference_label_text" else
                               {"label": "示例", "name": "示例", "quantity": "Capacity", "unit": "µAh"})
                    validate = (key != "it_reference_label_text" or
                                self.controls["it_reference_show_labels"].isChecked())
                    if validate and control.text().strip() != "{ }":
                        format_template(control.text(), context, strict=True)
                    analysis[key] = control.text()
                elif key in ("lsv_window_low", "lsv_window_high", "it_reference_time"):
                    value = float(control.text()) if control.text().strip() else None
                    if value is not None and not math.isfinite(value):
                        raise ValueError("窗口端点及参考值必须为有限数值")
                    analysis[key] = value
                elif key.endswith("_reference_area_cm2") or key.endswith("_reference_capacitance"):
                    prefix = key.rsplit("_reference_", 1)[0]
                    mode_control = self.controls.get(
                        f"{prefix}_current_display"
                    )
                    active_mode = (
                        mode_control.currentData()
                        if isinstance(mode_control, QComboBox)
                        else "follow"
                    )
                    is_area = key.endswith("_reference_area_cm2")
                    active = active_mode == (
                        "reference_area" if is_area else "reference_capacitance"
                    )
                    text = control.text().strip()
                    try:
                        value = float(text) if text else None
                    except (TypeError, ValueError, OverflowError):
                        value = None
                        if active:
                            raise ValueError(
                                "请填写正的参考面积"
                                if is_area
                                else "请填写正的参考电容"
                            ) from None
                    if value is not None and (
                        not math.isfinite(value) or value <= 0
                    ):
                        if active:
                            raise ValueError(
                                "请填写正的参考面积"
                                if is_area
                                else "请填写正的参考电容"
                            )
                        value = None
                    if is_area:
                        if value is not None:
                            analysis[key] = value
                        elif active:
                            raise ValueError("请填写正的参考面积")
                    else:
                        unit_control = self.controls.get(
                            f"{prefix}_reference_capacitance_unit"
                        )
                        unit = (
                            unit_control.currentData()
                            if isinstance(unit_control, QComboBox)
                            else "F"
                        ) or "F"
                        factor = unit_factor(CAPACITANCE, unit) or 1.0
                        if value is not None:
                            analysis[f"{prefix}_reference_capacitance_f"] = (
                                value / factor
                            )
                            analysis[
                                f"{prefix}_reference_capacitance_unit"
                            ] = unit
                        elif active:
                            raise ValueError("请填写正的参考电容")
                elif key in ("capacity_percent_reference", "capacity_percent_cycle"):
                    if not control.isEnabled():
                        continue
                    value = float(control.text()) if control.text().strip() else None
                    if value is not None and (not math.isfinite(value) or value <= 0):
                        raise ValueError("容量参考值和参考循环必须为有限正数")
                    if key == "capacity_percent_cycle" and value is not None:
                        if not value.is_integer():
                            raise ValueError("参考循环编号必须为正整数")
                        value = int(value)
                    analysis[key] = value
                elif isinstance(control, QLineEdit):
                    value = float(control.text()) if control.text().strip() else None
                    if value is not None and (not math.isfinite(value) or value <= 0):
                        raise ValueError("频率必须为有限正数或留空")
                    changes[key] = value
                else:
                    changes[key] = control.value()
            if self.tab.spec.kind == "cp_capacity":
                concat_runs = [
                    run
                    for run in self.tab.dataset.cp_runs
                    if run.run_id in set(self.tab.spec.run_ids)
                ]
                concat_summaries = {
                    run.run_id: (
                        run.summary
                        if isinstance(run.summary, CPRunSummary)
                        else analyze_cp_run(run)
                    )
                    for run in concat_runs
                }
                concat_order, concat_ranges = normalize_cp_concat_config(
                    concat_runs,
                    concat_summaries,
                    order=self.tab.spec.analysis_options.get("cp_concat_order"),
                    ranges=self.tab.spec.analysis_options.get("cp_concat_ranges"),
                )
                saved = self.tab.spec.analysis_options
                valid_cp = {run.run_id for run in self.tab.dataset.cp_runs}
                saved_order = saved.get("cp_concat_order") or []
                saved_ranges = saved.get("cp_concat_ranges") or {}
                analysis["cp_concat_order"] = list(dict.fromkeys(
                    [run_id for run_id in saved_order if run_id in valid_cp] + concat_order
                ))
                analysis["cp_concat_ranges"] = {
                    **{run_id: bounds for run_id, bounds in saved_ranges.items() if run_id in valid_cp},
                    **concat_ranges,
                }
                saved_reference = saved.get("capacity_percent_reference_run_id")
                hidden_reference = (
                    not analysis.get("capacity_percent_reference_run_id")
                    and saved_reference in valid_cp
                    and saved_reference not in concat_summaries
                )
                if hidden_reference:
                    analysis["capacity_percent_reference_run_id"] = saved_reference
                    analysis["capacity_percent_reference_cycle"] = saved.get("capacity_percent_reference_cycle")
                if analysis.get("capacity_percent_mode") == "unified" and not hidden_reference:
                    reference_run_id = analysis.get(
                        "capacity_percent_reference_run_id"
                    )
                    reference_cycle = analysis.get(
                        "capacity_percent_reference_cycle"
                    )
                    if not reference_run_id:
                        raise ValueError("请选择统一 100% 参考文件")
                    if reference_cycle is None:
                        raise ValueError("请选择统一 100% 参考循环")
                    try:
                        reference_cycle = int(reference_cycle)
                    except (TypeError, ValueError, OverflowError):
                        raise ValueError("统一 100% 参考循环必须为整数") from None
                    if analysis.get("cp_concat_enabled"):
                        displayed_order = concat_order
                        displayed_ranges = concat_ranges
                    else:
                        summaries = concat_summaries
                        displayed_order = [
                            run.run_id for run in concat_runs
                        ]
                        displayed_ranges = {
                            run.run_id: {
                                "start": 1,
                                "end": len(
                                    summaries.get(run.run_id).cycles
                                    if summaries.get(run.run_id) is not None
                                    else ()
                                ),
                            }
                            for run in concat_runs
                        }
                    entries = cp_concat_entries(
                        concat_runs,
                        concat_summaries,
                        order=displayed_order,
                        ranges=displayed_ranges,
                    )
                    effective_normalization = self.tab.spec.normalization
                    if effective_normalization in {"mass", "area"}:
                        available = all(
                            (
                                run.params.has_mass()
                                if effective_normalization == "mass"
                                else run.params.has_area()
                            )
                            for run in concat_runs
                        )
                        if not available:
                            effective_normalization = "none"
                    values_by_run = {
                        run.run_id: cp_cycle_values(
                            run,
                            concat_summaries[run.run_id],
                            quantity=analysis.get("cp_quantity", "capacity"),
                            normalization=effective_normalization,
                            include_holds=bool(
                                analysis.get("include_holds", False)
                            ),
                        )
                        for run in concat_runs
                    }
                    _reference, reference_error = resolve_cp_unified_reference(
                        entries,
                        values_by_run,
                        reference_run_id,
                        reference_cycle,
                    )
                    if reference_error:
                        raise ValueError(reference_error)
                    required_reference = {
                        "charge": (_reference.charge,),
                        "discharge": (_reference.discharge,),
                        "both": (_reference.charge, _reference.discharge),
                        "mean": (_reference.mean,),
                    }[analysis.get("capacity_series", "both")]
                    if any(
                        not math.isfinite(value) or value <= 0
                        for value in required_reference
                    ):
                        raise ValueError(
                            "统一 100% 参考 Cycle 的容量/电容值无效，"
                            "请选择其他循环"
                        )
                    analysis["capacity_percent_reference_cycle"] = (
                        reference_cycle
                    )
            if analysis.get("capacity_percent_mode") == "manual" and analysis.get("capacity_percent_reference") is None:
                raise ValueError("请填写作为 100% 的容量参考值")
            if analysis.get("capacity_percent_mode") == "manual" and self._cp_reference_needs_confirmation:
                raise ValueError("容量类型或归一化方式已变化，请重新填写手动参考值")
            if self._cp_reference_unit_state is not None:
                analysis["capacity_percent_reference_unit"] = self._cp_reference_unit_state["unit"]
            if self._cp_reference_needs_confirmation and analysis.get("capacity_percent_mode") in {"absolute", "cycle"}:
                old_reference = self.tab.spec.analysis_options.get("capacity_percent_reference")
                if old_reference is not None:
                    analysis["capacity_percent_previous_reference"] = {
                        "value": old_reference,
                        "exponent": self.tab.spec.analysis_options.get("capacity_percent_reference_exponent", 0),
                        "unit": self.tab.spec.analysis_options.get("cp_display_unit"),
                        "quantity": self.tab.spec.analysis_options.get("cp_quantity", "capacity"),
                    }
                analysis["capacity_percent_reference"] = None
            if analysis.get("capacity_percent_mode") == "cycle" and analysis.get("capacity_percent_cycle") is None:
                raise ValueError("请填写参考循环编号")
            if "lsv_window_low" in analysis:
                low, high = analysis["lsv_window_low"], analysis["lsv_window_high"]
                if (low is None) != (high is None) or (low is not None and low == high):
                    raise ValueError("电压窗口需填写两个不同的端点，或均留空")
            if self._it_position_controls:
                positions = self.tab.spec.analysis_options.get("it_reference_positions", {})
                positions = dict(positions) if isinstance(positions, dict) else {}
                positions.update({run_id: [x.value(), y.value()]
                                  for run_id, (x, y) in self._it_position_controls.items()})
                analysis["it_reference_positions"] = positions
            if self._it_label_visibility_items:
                visibility = self.tab.spec.analysis_options.get("it_reference_label_visibility", {})
                visibility = dict(visibility) if isinstance(visibility, dict) else {}
                visibility.update({run_id: item.checkState() == Qt.Checked
                                   for run_id, item in self._it_label_visibility_items.items()})
                analysis["it_reference_label_visibility"] = visibility
            if changes.get("frequency_low") is not None and changes.get("frequency_high") is not None and changes["frequency_low"] > changes["frequency_high"]:
                raise ValueError("最低频率不能大于最高频率")
            axis_limits = self._collect_axis_limits()
            axis_limit_units = self._collect_axis_limit_units(axis_limits)
            unit_overrides = {
                key: control.currentData()
                for key, control in self.unit_controls.items()
                if control.currentData() not in (None, "", "legacy")
                and (control.currentData() != "auto" or self.tab.spec.kind in {"lsv_curve", "it_curve"})
            }
            if self.tab.spec.kind in {"lsv_curve", "it_curve"}:
                prefix = (
                    "lsv" if self.tab.spec.kind == "lsv_curve" else "it"
                )
                cap_unit = canonical_unit(
                    analysis.get(
                        f"{prefix}_reference_capacitance_unit"
                    )
                    or self.tab.spec.analysis_options.get(
                        f"{prefix}_reference_capacitance_unit"
                    )
                    or "F"
                )
                if unit_factor(CAPACITANCE, cap_unit) is None:
                    cap_unit = "F"
                active_family = sweep_current_family(
                    analysis.get(
                        f"{prefix}_current_display", "follow"
                    ),
                    self.tab.spec.normalization,
                    cap_unit,
                )
                current_override = unit_overrides.get("current")
                if (
                    current_override
                    and current_override not in {"auto", "legacy"}
                    and unit_factor(active_family, current_override) is None
                ):
                    prefix_unit = str(current_override).split("/", 1)[0]
                    candidate = f"{prefix_unit}/{cap_unit}"
                    unit_overrides["current"] = (
                        candidate
                        if unit_factor(active_family, candidate) is not None
                        else "auto"
                    )
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
            apply_theme_role(self.error, "error")
            self.error.setText(str(exc))
            return
        for key, value in changes.items():
            setattr(self.tab.spec, key, value)
        old_basis = self.tab.spec.analysis_options.get("dunn_fraction_basis", "fitted")
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
        apply_theme_role(self.error, "success")
        self.error.setText("已应用")
        if analysis.get("dunn_fraction_basis", old_basis) != old_basis:
            show_dunn_basis(self, analysis["dunn_fraction_basis"])
