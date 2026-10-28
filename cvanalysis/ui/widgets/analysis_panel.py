# -*- coding: utf-8 -*-
"""Context-sensitive analysis controls."""

from __future__ import annotations

from typing import Iterable
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.analysis.fitting import available_models
from cvanalysis.domain.models import CPRun, CVRun, Dataset, EISRun


class AnalysisPanel(QWidget):
    plot_requested = Signal(str)
    fit_requested = Signal()
    options_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_run_ids: list[str] = []
        self._visible_run_ids: list[str] | None = None
        self._current_dataset = Dataset()
        self._display_kind = None
        self._loading = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.info_label = QLabel("尚未导入数据")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #546e7a;")
        layout.addWidget(self.info_label)

        self.normalization_combo = QComboBox()
        self.normalization_combo.addItem("原始值", "none")
        self.normalization_combo.addItem("按电极面积", "area")
        self.normalization_combo.addItem("按活性物质质量", "mass")
        normalization_form = QFormLayout()
        normalization_form.addRow("归一化:", self.normalization_combo)
        layout.addLayout(normalization_form)
        self.normalization_combo.currentIndexChanged.connect(self._emit_options)

        self.target_spin = QDoubleSpinBox()
        self.target_spin.setRange(-1000.0, 1000.0)
        self.target_spin.setDecimals(4)
        self.target_spin.setSingleStep(0.1)
        self.target_spin.setSuffix(" V")
        self.target_spin.setMinimumWidth(80)
        self.target_spin.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.target_spin.valueChanged.connect(self._emit_options)

        self.scan_rate_spin = QDoubleSpinBox()
        self.scan_rate_spin.setRange(1e-9, 1e9)
        self.scan_rate_spin.setDecimals(6)
        self.scan_rate_spin.setSuffix(" V/s")
        self.scan_rate_spin.setMinimumWidth(80)
        self.scan_rate_spin.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.scan_rate_spin.valueChanged.connect(self._emit_options)

        self.renumber_cycles_cb = QCheckBox("显示时重编号循环")
        self.renumber_cycles_cb.setToolTip("勾选后，每个数据内当前显示的有效循环按 1..N 连续编号")
        self.renumber_cycles_cb.stateChanged.connect(self._emit_options)
        self.show_legend_cb = QCheckBox("显示图例")
        self.show_legend_cb.setChecked(True)
        self.show_legend_cb.stateChanged.connect(self._emit_options)
        self.show_axes_cb = QCheckBox("显示坐标轴")
        self.show_axes_cb.setChecked(True)
        self.show_axes_cb.stateChanged.connect(self._emit_options)
        self.show_annotations_cb = QCheckBox("显示统计注释")
        self.show_annotations_cb.setChecked(True)
        self.show_annotations_cb.stateChanged.connect(self._emit_options)

        form = QFormLayout()
        form.addRow(self.renumber_cycles_cb)
        form.addRow(self.show_legend_cb)
        form.addRow(self.show_axes_cb)
        form.addRow(self.show_annotations_cb)

        common_group = QGroupBox("通用分析选项")
        common_group.setLayout(form)

        cv_group = QGroupBox("CV 快速分析")
        cv_layout = QVBoxLayout(cv_group)
        cv_layout.setSpacing(6)
        cv_form = QFormLayout()
        cv_form.addRow("目标电位:", self.target_spin)
        cv_form.addRow("分解扫速:", self.scan_rate_spin)
        cv_layout.addLayout(cv_form)
        cv_buttons = [
            ("CV 叠加", "cv_overlay", "CV 叠加图"),
            ("电容-扫速", "cv_cap_scan", "电容-扫速"),
            ("i@V-扫速", "cv_current_scan", "固定电位电流-扫速"),
            ("b 值", "cv_bvalue", "b 值分析"),
            ("Dunn 分解", "cv_contribution", "Dunn 电流分解（电位）"),
            ("贡献-扫速", "cv_contribution_vs_rate", "贡献占比-扫速（柱状图）"),
            ("Trasatti", "cv_trasatti", "Trasatti 电荷分解"),
        ]
        for label, kind, tooltip in cv_buttons:
            button = QPushButton(label)
            button.setProperty("secondary", True)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, k=kind: self.plot_requested.emit(k))
            cv_layout.addWidget(button)
        cv_layout.addStretch(1)

        eis_group = QGroupBox("EIS 快捷分析")
        eis_layout = QVBoxLayout(eis_group)
        freq_row = QHBoxLayout()
        self.freq_low_edit = QLineEdit()
        self.freq_low_edit.setPlaceholderText("低频，如 0.01")
        self.freq_low_edit.setMinimumWidth(50)
        self.freq_low_edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.freq_high_edit = QLineEdit()
        self.freq_high_edit.setPlaceholderText("高频，如 1e6")
        self.freq_high_edit.setMinimumWidth(50)
        self.freq_high_edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        freq_row.addWidget(QLabel("频率:"))
        freq_row.addWidget(self.freq_low_edit, 1)
        freq_row.addWidget(QLabel("–"))
        freq_row.addWidget(self.freq_high_edit, 1)
        reset_freq_btn = QPushButton("重置")
        reset_freq_btn.setProperty("secondary", True)
        reset_freq_btn.setToolTip("清空频率范围")
        reset_freq_btn.setMinimumWidth(36)
        reset_freq_btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        reset_freq_btn.clicked.connect(self._reset_frequency)
        freq_row.addWidget(reset_freq_btn)
        eis_layout.addLayout(freq_row)
        self.frequency_error = QLabel()
        self.frequency_error.setWordWrap(True)
        self.frequency_error.setStyleSheet("color: #a33")
        eis_layout.addWidget(self.frequency_error)

        self.fit_model_combo = QComboBox()
        self.fit_model_combo.addItem("自动（按谱形）", "auto")
        self.fit_model_combo.setToolTip("自动检测完整半圆推荐 Rs-(Rct||CPE)，否则推荐 Rs-CPE")
        self.fit_model_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.fit_model_combo.setMinimumContentsLength(8)
        self.fit_model_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        ui_labels = {
            "rct_cpe": "Rs-(Rct||CPE)",
            "rct_c": "Rs-(Rct||C)",
            "rs_cpe": "Rs-CPE",
            "rs_c": "Rs-C",
        }
        model_tooltips = {
            "rct_cpe": "Rs-(Rct||CPE)：完整半圆的阻塞/界面电荷转移模型",
            "rct_c": "Rs-(Rct||C)：理想电容并联电荷转移电阻",
            "rs_cpe": "Rs-CPE：阻塞/超电容 CPE 模型",
            "rs_c": "Rs-C：理想电容串联 Rs",
        }
        for key in available_models():
            self.fit_model_combo.addItem(ui_labels.get(key, key), key)
            index = self.fit_model_combo.count() - 1
            self.fit_model_combo.setItemData(
                index, model_tooltips.get(key, key), Qt.ToolTipRole
            )
        eis_layout.addWidget(QLabel("拟合模型:"))
        eis_layout.addWidget(self.fit_model_combo)

        eis_buttons = [
            ("Nyquist 图", "eis_nyquist"),
            ("Bode 图", "eis_bode"),
            ("拟合当前 EIS", "fit"),
        ]
        for label, kind in eis_buttons:
            button = QPushButton(label)
            button.setProperty("secondary", True)
            if kind == "fit":
                button.clicked.connect(self.fit_requested)
            else:
                button.clicked.connect(lambda checked=False, k=kind: self.plot_requested.emit(k))
            eis_layout.addWidget(button)
        eis_layout.addStretch(1)

        cp_group = QGroupBox("CP / GCD 快捷分析")
        cp_layout = QVBoxLayout(cp_group)
        cp_hint = QLabel("恒流充放电：GCD 曲线可按文件中的保持段电流自动补全高/低电位平台。")
        cp_hint.setWordWrap(True)
        cp_hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        cp_hint.setStyleSheet("color: #607d8b;")
        cp_layout.addWidget(cp_hint)
        self.complete_holds_cb = QCheckBox("电位-时间自动补全保持区间")
        self.complete_holds_cb.setChecked(True)
        self.complete_holds_cb.setToolTip(
            "文件包含 Hold Time/Current 块时，在每个活动电流段后插入高/低电位保持平台；"
            "保持段电流仍用于容量分解。"
        )
        self.complete_holds_cb.stateChanged.connect(self._emit_options)
        cp_layout.addWidget(self.complete_holds_cb)
        self.include_holds_cb = QCheckBox("容量计入恒压保持段")
        self.include_holds_cb.setToolTip(
            "关闭时只用恒流活动段计算容量；开启时把保持段电流积分计入充电/放电容量。"
        )
        self.include_holds_cb.stateChanged.connect(self._emit_options)
        cp_layout.addWidget(self.include_holds_cb)
        cp_buttons = [
            ("GCD 电位-时间", "cp_gcd", "GCD 电位-时间曲线（可补全保持段）"),
            ("GCD 容量-循环", "cp_capacity", "GCD 容量-循环和库伦效率"),
        ]
        for label, kind, tooltip in cp_buttons:
            button = QPushButton(label)
            button.setProperty("secondary", True)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, k=kind: self.plot_requested.emit(k))
            cp_layout.addWidget(button)
        cp_layout.addStretch(1)

        options_widget = QWidget()
        options_layout = QVBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(6)
        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setDocumentMode(True)
        self.analysis_tabs.setElideMode(Qt.ElideRight)
        self.analysis_tabs.setUsesScrollButtons(True)
        for label, tooltip, page in (
            ("CV", "CV 快速分析：叠加、扫速、b 值、Dunn/Trasatti", cv_group),
            ("EIS", "EIS 快速分析：Nyquist、Bode 与拟合", eis_group),
            ("CP", "CP/GCD 恒流充放电：GCD 曲线与容量-循环", cp_group),
            ("显示", "通用显示选项", common_group),
        ):
            index = self.analysis_tabs.addTab(page, label)
            self.analysis_tabs.setTabToolTip(index, tooltip)
        options_layout.addWidget(self.analysis_tabs)
        options_layout.addStretch(1)

        self.options_scroll = QScrollArea()
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setFrameShape(QFrame.NoFrame)
        self.options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.options_scroll.setWidget(options_widget)

        layout.addWidget(self.options_scroll, stretch=1)

        self.freq_low_edit.textChanged.connect(self._emit_options)
        self.freq_high_edit.textChanged.connect(self._emit_options)
        self.fit_model_combo.currentIndexChanged.connect(self._emit_options)

    def _reset_frequency(self) -> None:
        self.freq_low_edit.clear()
        self.freq_high_edit.clear()

    def _emit_options(self, *args) -> None:
        if not self._loading and self.validate_frequency():
            self.options_changed.emit()

    def validate_frequency(self):
        try:
            low = self._parse_positive(self.freq_low_edit.text())
            high = self._parse_positive(self.freq_high_edit.text())
            if low is not None and high is not None and low > high:
                raise ValueError("最低频率不能大于最高频率")
        except ValueError as exc:
            self.frequency_error.setText(str(exc))
            return False
        self.frequency_error.clear()
        return True

    # -- dataset / options ------------------------------------------------
    def update_dataset(
        self,
        dataset: Dataset,
        *,
        selected_run_ids: Iterable[str] | None = None,
        visible_run_ids: Iterable[str] | None = None,
    ) -> None:
        self._current_dataset = dataset
        self._selected_run_ids = list(selected_run_ids or [])
        self._visible_run_ids = None if visible_run_ids is None else list(visible_run_ids)
        cv_runs = self._runs_for_display(dataset, CVRun)
        eis_runs = self._runs_for_display(dataset, EISRun)
        cp_runs = self._runs_for_display(dataset, CPRun)
        self.info_label.setText(
            f"已选 {len(cv_runs)} 个 CV / {len(eis_runs)} 个 EIS / {len(cp_runs)} 个 CP"
        )
        self._update_ranges(cv_runs, eis_runs)
        selected_types = {
            "cv"
            if isinstance(run, CVRun)
            else "cp"
            if isinstance(run, CPRun)
            else "eis"
            for run in dataset.all_runs()
            if run.run_id in self._selected_run_ids
        }
        kind = next(iter(selected_types)) if len(selected_types) == 1 else (
            "eis"
            if eis_runs and not cv_runs and not cp_runs
            else "cv"
            if cv_runs and not eis_runs and not cp_runs
            else "cp"
            if cp_runs and not cv_runs and not eis_runs
            else None
        )
        if kind and kind != self._display_kind:
            self.analysis_tabs.setCurrentIndex({"cv": 0, "eis": 1, "cp": 2}[kind])
        self._display_kind = kind

    def _runs_for_display(self, dataset: Dataset, run_type):
        selected = [run for run in dataset.all_runs() if run.run_id in set(self._selected_run_ids) and isinstance(run, run_type)]
        if selected:
            return selected
        if self._visible_run_ids is not None:
            visible = set(self._visible_run_ids)
            return [run for run in dataset.all_runs() if run.run_id in visible and isinstance(run, run_type)]
        return [run for run in dataset.all_runs() if isinstance(run, run_type)]

    def _update_ranges(self, cv_runs: list[CVRun], eis_runs: list[EISRun]) -> None:
        if cv_runs:
            lows = [float(min(run.potential)) for run in cv_runs if len(run.potential)]
            highs = [float(max(run.potential)) for run in cv_runs if len(run.potential)]
            if lows and highs:
                low = max(lows)
                high = min(highs)
                if high > low:
                    self.target_spin.blockSignals(True)
                    self.target_spin.setRange(low, high)
                    if not (low <= self.target_spin.value() <= high):
                        self.target_spin.setValue((low + high) / 2.0)
                    self.target_spin.blockSignals(False)
            rates = sorted({run.scan_rate for run in cv_runs if run.scan_rate and run.scan_rate > 0})
            if rates:
                previous_rate = self.scan_rate_spin.value()
                self.scan_rate_spin.blockSignals(True)
                self.scan_rate_spin.setRange(min(rates), max(rates))
                self.scan_rate_spin.setValue(
                    previous_rate if min(rates) <= previous_rate <= max(rates) else rates[len(rates) // 2]
                )
                self.scan_rate_spin.blockSignals(False)
        if eis_runs:
            lows = [run.metadata.low_freq for run in eis_runs if run.metadata.low_freq]
            highs = [run.metadata.high_freq for run in eis_runs if run.metadata.high_freq]
            if lows and highs:
                self.freq_low_edit.setPlaceholderText(f"{min(lows):.4g}")
                self.freq_high_edit.setPlaceholderText(f"{max(highs):.4g}")

    def options(self) -> dict:
        return {
            "normalization": self.normalization_combo.currentData() or "none",
            "target_voltage": self.target_spin.value(),
            "selected_scan_rate": self.scan_rate_spin.value(),
            "frequency_low": self._parse_positive(self.freq_low_edit.text()),
            "frequency_high": self._parse_positive(self.freq_high_edit.text()),
            "fit_model": self.fit_model_combo.currentData() or "rct_cpe",
            "renumber_cycles": self.renumber_cycles_cb.isChecked(),
            "show_legend": self.show_legend_cb.isChecked(),
            "show_axes": self.show_axes_cb.isChecked(),
            "annotations": self.show_annotations_cb.isChecked(),
            "complete_holds": self.complete_holds_cb.isChecked(),
            "include_holds": self.include_holds_cb.isChecked(),
        }

    def set_options(self, options: dict) -> None:
        self._loading = True
        try:
            normalization = options.get("normalization", "none")
            index = self.normalization_combo.findData(normalization)
            if index >= 0:
                self.normalization_combo.setCurrentIndex(index)
            target = options.get("target_voltage")
            if target is not None:
                target = float(target)
                low = min(self.target_spin.minimum(), target)
                high = max(self.target_spin.maximum(), target)
                self.target_spin.setRange(low, high)
                self.target_spin.setValue(target)
            scan_rate = options.get("selected_scan_rate")
            if scan_rate is not None:
                scan_rate = float(scan_rate)
                low = min(self.scan_rate_spin.minimum(), scan_rate)
                high = max(self.scan_rate_spin.maximum(), scan_rate)
                self.scan_rate_spin.setRange(low, high)
                self.scan_rate_spin.setValue(scan_rate)
            if "frequency_low" in options:
                value = options["frequency_low"]
                self.freq_low_edit.setText("" if value is None else str(value))
            if "frequency_high" in options:
                value = options["frequency_high"]
                self.freq_high_edit.setText("" if value is None else str(value))
            model = options.get("fit_model")
            if model:
                index = self.fit_model_combo.findData(model)
                if index >= 0:
                    self.fit_model_combo.setCurrentIndex(index)
            if options.get("renumber_cycles") is not None:
                self.renumber_cycles_cb.setChecked(bool(options["renumber_cycles"]))
            if options.get("show_legend") is not None:
                self.show_legend_cb.setChecked(bool(options["show_legend"]))
            if options.get("show_axes") is not None:
                self.show_axes_cb.setChecked(bool(options["show_axes"]))
            if options.get("annotations") is not None:
                self.show_annotations_cb.setChecked(bool(options["annotations"]))
            if options.get("complete_holds") is not None:
                self.complete_holds_cb.setChecked(bool(options["complete_holds"]))
            if options.get("include_holds") is not None:
                self.include_holds_cb.setChecked(bool(options["include_holds"]))
        finally:
            self._loading = False

    @staticmethod
    def _parse_positive(text: str) -> float | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            raise ValueError("频率须为有限正数，留空表示不限制") from None
        if not math.isfinite(value) or value <= 0:
            raise ValueError("频率须为有限正数，留空表示不限制")
        return value
