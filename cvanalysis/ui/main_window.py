# -*- coding: utf-8 -*-
"""Main v2 workspace window."""

from __future__ import annotations

import copy
import logging
import math
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.analysis.eis import metrics_from_fit
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import CPRun, CVRun, Dataset, EISRun, ElectrodeParams
from cvanalysis.domain.units import CURRENT, format_with_unit
from cvanalysis.plotting.legend import dataset_file_numbers, preview_label
from cvanalysis.plotting.presets import BUILTIN_PRESETS, DEFAULT_PRESET_NAME, preset_label, preset_names
from cvanalysis.plotting.spec import PLOT_KINDS, PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, fit_eis_runs, refresh_analysis
from cvanalysis.services.export_service import export_analysis_csv
from cvanalysis.services.project_service import load_project, save_project as save_project_file
from cvanalysis.services.settings_service import (
    BOTTOM_LAYOUT_VERSION,
    SettingsService,
    app_data_dir,
)
from cvanalysis.ui.dialogs.legend_dialog import LegendTemplateDialog
from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog
from cvanalysis.ui.dialogs.preset_manager_dialog import PresetManagerDialog
from cvanalysis.ui.dialogs.quick_style_dialog import QuickStyleDialog
from cvanalysis.ui.dialogs.settings_dialog import SettingsDialog
from cvanalysis.ui.dialogs.style_dialog import StyleEditorDialog
from cvanalysis.ui.logging_utils import QtLogHandler, configure_logging
from cvanalysis.ui.models.dataset_model import DatasetTreeModel
from cvanalysis.ui.theme import application_stylesheet
from cvanalysis.ui.widgets.analysis_panel import AnalysisPanel
from cvanalysis.ui.widgets.plot_tab import PlotTab
from cvanalysis.ui.widgets.view_columns import ViewColumns
from cvanalysis.ui.workers import ImportThread, TaskThread
from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
from cvanalysis.ui.widgets.results_panel import ResultsPanel
from cvanalysis.ui.widgets.wheel_guard import install_wheel_guard


BASE_WINDOW_TITLE = "CVAnalysis v2 — 电化学数据分析工作区"


def _safe_ui_scale(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(number):
        return 1.0
    return max(0.8, min(1.6, number))


class MainWindow(QMainWindow):
    def __init__(self, *, settings_path: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.settings_service = SettingsService(settings_path)
        self._project_analysis = None
        self._dirty = False
        self._loading_project = False
        self._ui_scale = _safe_ui_scale(self.settings_service.ui_state.get("scale", 1.0))
        self.dataset = Dataset()
        self.dataset_model = DatasetTreeModel(self)
        self.fits: dict[str, EISFitResult] = {}
        self.metrics: dict = {}
        self._tasks = []
        self.import_thread: ImportThread | None = None
        self._progress: QProgressDialog | None = None
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(80)
        self._redraw_timer.timeout.connect(self._redraw_all_tabs)

        self._apply_ui_scale()
        install_wheel_guard(QApplication.instance())
        self.logger, self.log_handler = self._setup_logging()
        if self.settings_service.migrated_from_v1:
            self.logger.info("已迁移 v1 config.json，旧版备份为 config.json.v1.bak")
        for warning in self.settings_service.load_warnings:
            self.logger.warning("配置: %s", warning)
        self._build_ui()
        self._build_actions()
        self._connect_signals()
        self._restore_ui_state()
        ui = self.settings_service.ui_state
        if not ui.get("dataset_splitter"):
            QTimer.singleShot(0, self._apply_default_splitters)
        self._refresh_preset_combo()
        self.analysis_panel.set_options(
            {
                "normalization": self.active_analysis.get("default_normalization", "none"),
                "fit_model": self.settings_service.eis.get("fit_model", "auto"),
                "frequency_low": None,
                "frequency_high": None,
            }
        )
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_logging(self):
        logger = logging.getLogger("cvanalysis")
        handler = next((item for item in logger.handlers if isinstance(item, QtLogHandler)), None)
        if handler is not None:
            return logger, handler
        try:
            handler = configure_logging(app_data_dir() / "logs" / "cvanalysis.log")
        except Exception:
            handler = QtLogHandler()
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)
        return logger, handler

    @property
    def active_analysis(self):
        if isinstance(self._project_analysis, dict):
            return self._project_analysis
        return self.settings_service.analysis

    def _apply_ui_scale(self) -> None:
        app = QApplication.instance()
        if app is not None:
            font = app.font()
            font.setPointSizeF(11.0 * self._ui_scale)
            app.setFont(font)
            app.setStyleSheet(application_stylesheet(self._ui_scale))

    def _build_ui(self) -> None:
        self.setWindowTitle(BASE_WINDOW_TITLE)
        self.setStyleSheet(application_stylesheet(self._ui_scale))
        self.resize(1560, 960)
        self.setDockNestingEnabled(True)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self.tree = QTreeView()
        self.tree.setModel(self.dataset_model)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setDragDropOverwriteMode(False)
        self.tree.setDropIndicatorShown(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setUniformRowHeights(True)
        self.dataset_columns = ViewColumns(self.tree)
        self.tree.doubleClicked.connect(self._on_tree_double_clicked)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)

        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        tree_layout.setSpacing(4)
        hint = QLabel("勾选更新跟随图；拖动文件调整分组内顺序。“数据...”自定义当前图；右键文件设置面积/图例并快速绘图。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #607d8b;")
        tree_layout.addWidget(hint)
        action_row = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.setProperty("secondary", True)
        select_all_btn.setToolTip("选中所有文件；Ctrl/Shift 可继续多选")
        select_all_btn.clicked.connect(self._select_all_runs)
        clear_selection_btn = QPushButton("取消选择")
        clear_selection_btn.setProperty("secondary", True)
        clear_selection_btn.clicked.connect(self._clear_tree_selection)
        delete_selected_btn = QPushButton("删除选中")
        delete_selected_btn.setProperty("secondary", True)
        delete_selected_btn.clicked.connect(self._delete_selected_runs)
        clear_all_btn = QPushButton("清空数据")
        clear_all_btn.setProperty("secondary", True)
        clear_all_btn.clicked.connect(self.clear_dataset)
        for button in (select_all_btn, clear_selection_btn, delete_selected_btn, clear_all_btn):
            action_row.addWidget(button)
        tree_layout.addLayout(action_row)
        self.file_detail_label = QLabel("未选择文件")
        self.file_detail_label.setWordWrap(True)
        self.file_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_detail_label.setStyleSheet("color: #546e7a;")
        self.file_detail_label.setMinimumHeight(54)
        self.dataset_splitter = QSplitter(Qt.Vertical)
        self.dataset_splitter.setChildrenCollapsible(False)
        self.dataset_splitter.addWidget(self.tree)
        self.dataset_splitter.addWidget(self.file_detail_label)
        self.dataset_splitter.setStretchFactor(0, 1)
        self.dataset_splitter.setStretchFactor(1, 0)
        self.dataset_splitter.setSizes([640, 120])
        tree_layout.addWidget(self.dataset_splitter, 1)
        self.dataset_dock = QDockWidget("数据集", self)
        self.dataset_dock.setObjectName("dataset_dock")
        self.dataset_dock.setWidget(tree_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dataset_dock)

        self.analysis_panel = AnalysisPanel()
        self.analysis_dock = QDockWidget("分析与参数", self)
        self.analysis_dock.setObjectName("analysis_dock")
        self.analysis_dock.setWidget(self.analysis_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.analysis_dock)

        self.results_panel = ResultsPanel()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_title = QLabel("日志")
        self.log_title.setStyleSheet(
            "background: #eef2f5; padding: 6px; "
            "border-bottom: 1px solid #d9e0e6; font-weight: 600;"
        )
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(3)
        log_layout.addWidget(self.log_title)
        log_layout.addWidget(self.log_view, 1)

        self.log_dock = QDockWidget("结果、日志与当前图设置", self)
        self.log_dock.setObjectName("log_dock")
        self.options_panel = AnalysisOptionsPanel()
        self.options_panel.applied.connect(self._on_analysis_options_applied)
        self.options_panel.setMinimumWidth(450)
        self.bottom_splitter = QSplitter(Qt.Horizontal)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.bottom_splitter.addWidget(self.results_panel)
        self.bottom_splitter.addWidget(log_container)
        self.bottom_splitter.addWidget(self.options_panel)
        self.bottom_splitter.setStretchFactor(0, 0)
        self.bottom_splitter.setStretchFactor(1, 1)
        self.bottom_splitter.setStretchFactor(2, 0)
        self.bottom_splitter.setSizes([430, 900, 520])
        self.log_dock.setWidget(self.bottom_splitter)
        self.log_dock.setTitleBarWidget(QWidget(self))
        self.log_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.resizeDocks([self.dataset_dock, self.analysis_dock], [380, 380], Qt.Horizontal)
        self.resizeDocks([self.log_dock], [400], Qt.Vertical)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self.apply_preset_all_btn = QPushButton("应用到全部")
        self.apply_preset_all_btn.setProperty("secondary", True)
        self.edit_style_btn = QPushButton("编辑样式")
        self.edit_style_btn.setProperty("secondary", True)

    def _build_actions(self) -> None:
        self.open_action = QAction("导入数据文件...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.import_files)
        self.clear_action = QAction("清空数据", self)
        self.clear_action.triggered.connect(self.clear_dataset)
        self.open_project_action = QAction("打开项目...", self)
        self.open_project_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.open_project_action.triggered.connect(self.open_project)
        self.save_project_action = QAction("保存", self)
        self.save_project_action.setShortcut(QKeySequence.Save)
        self.save_project_action.setToolTip("保存当前项目（Ctrl+S）；新项目首次保存会打开另存为")
        self.save_project_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.save_project_action.triggered.connect(self.save_project)
        self.save_project_as_action = QAction("项目另存为...", self)
        self.save_project_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_project_as_action.setToolTip("将当前项目保存到新文件（Ctrl+Shift+S）")
        self.save_project_as_action.triggered.connect(self.save_project_as)
        self.export_action = QAction("导出当前图...", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.triggered.connect(self.export_current_plot)
        self.export_csv_action = QAction("导出分析数据 CSV...", self)
        self.export_csv_action.triggered.connect(self.export_analysis_csv)
        self.quit_action = QAction("退出", self)
        self.quit_action.setShortcut(QKeySequence.Quit)
        self.quit_action.triggered.connect(self.close)

        self.settings_action = QAction("设置...", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.preset_manager_action = QAction("预设管理...", self)
        self.preset_manager_action.triggered.connect(self.open_preset_manager)
        self.edit_legend_action = QAction("设置数据图例模板...", self)
        self.edit_legend_action.setToolTip("为选中数据设置默认图例模板，例如 {CV_Voltage}-{Cycle_Number}")
        self.edit_legend_action.triggered.connect(self._edit_legend_template_for_selection)
        self.about_action = QAction("关于", self)
        self.about_action.triggered.connect(self.show_about)

        self.cv_overlay_action = QAction("CV 叠加图", self)
        self.cv_overlay_action.triggered.connect(lambda: self._request_plot("cv_overlay"))
        self.cv_cap_scan_action = QAction("电容-扫速", self)
        self.cv_cap_scan_action.triggered.connect(lambda: self._request_plot("cv_cap_scan"))
        self.cv_current_scan_action = QAction("固定电位电流-扫速", self)
        self.cv_current_scan_action.triggered.connect(lambda: self._request_plot("cv_current_scan"))
        self.cv_bvalue_action = QAction("b 值分析", self)
        self.cv_bvalue_action.triggered.connect(lambda: self._request_plot("cv_bvalue"))
        self.cv_contribution_action = QAction("Dunn 电流分解", self)
        self.cv_contribution_action.triggered.connect(lambda: self._request_plot("cv_contribution"))
        self.cv_contribution_vs_rate_action = QAction("贡献占比-扫速", self)
        self.cv_contribution_vs_rate_action.triggered.connect(
            lambda: self._request_plot("cv_contribution_vs_rate")
        )
        self.cv_trasatti_action = QAction("Trasatti 电荷分解", self)
        self.cv_trasatti_action.triggered.connect(lambda: self._request_plot("cv_trasatti"))
        self.eis_nyquist_action = QAction("EIS Nyquist", self)
        self.eis_nyquist_action.triggered.connect(lambda: self._request_plot("eis_nyquist"))
        self.eis_bode_action = QAction("EIS Bode", self)
        self.eis_bode_action.triggered.connect(lambda: self._request_plot("eis_bode"))
        self.eis_fit_action = QAction("EIS 拟合", self)
        self.eis_fit_action.triggered.connect(self.fit_selected_eis)
        self.cp_gcd_action = QAction("GCD 电位-时间曲线", self)
        self.cp_gcd_action.triggered.connect(lambda: self._request_plot("cp_gcd"))
        self.cp_capacity_action = QAction("GCD 容量-循环 + 库伦效率", self)
        self.cp_capacity_action.triggered.connect(lambda: self._request_plot("cp_capacity"))
        self.close_plots_action = QAction("关闭所有图", self)
        self.close_plots_action.triggered.connect(self.close_all_plots)
        self.reset_layout_action = QAction("重置布局", self)
        self.reset_layout_action.triggered.connect(self.reset_layout)

        cv_actions = (
            self.cv_overlay_action,
            self.cv_cap_scan_action,
            self.cv_current_scan_action,
            self.cv_bvalue_action,
            self.cv_contribution_action,
            self.cv_contribution_vs_rate_action,
            self.cv_trasatti_action,
        )
        eis_actions = (self.eis_nyquist_action, self.eis_bode_action, self.eis_fit_action)
        cp_actions = (self.cp_gcd_action, self.cp_capacity_action)

        def make_submenu(title: str, actions) -> QMenu:
            submenu = QMenu(title, self)
            for action in actions:
                submenu.addAction(action)
            return submenu

        menu = self.menuBar()
        file_menu = menu.addMenu("文件(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.save_project_action)
        file_menu.addAction(self.save_project_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.export_csv_action)
        file_menu.addAction(self.clear_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        analysis_menu = menu.addMenu("分析(&A)")
        analysis_menu.addMenu(make_submenu("CV 分析", cv_actions))
        analysis_menu.addMenu(make_submenu("EIS 分析", eis_actions))
        analysis_menu.addMenu(make_submenu("CP / GCD 分析", cp_actions))

        view_menu = menu.addMenu("视图(&V)")
        view_menu.addAction(self.dataset_dock.toggleViewAction())
        view_menu.addAction(self.analysis_dock.toggleViewAction())
        view_menu.addAction(self.log_dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(self.close_plots_action)
        view_menu.addAction(self.reset_layout_action)

        tools_menu = menu.addMenu("工具(&T)")
        tools_menu.addAction(self.settings_action)
        tools_menu.addAction(self.preset_manager_action)
        tools_menu.addAction(self.edit_legend_action)

        help_menu = menu.addMenu("帮助(&H)")
        help_menu.addAction(self.about_action)

        toolbar = QToolBar("主工具栏")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(int(18 * self._ui_scale), int(18 * self._ui_scale)))
        self.addToolBar(toolbar)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.open_project_action)
        toolbar.addAction(self.save_project_action)
        toolbar.addSeparator()
        self.quick_analysis_buttons = {}
        for title, actions, tooltip in (
            ("CV 分析", cv_actions, "CV 叠加、扫速、b 值、Dunn/Trasatti 分析"),
            ("EIS 分析", eis_actions, "EIS Nyquist/Bode 与等效电路拟合"),
            ("CP / GCD 分析", cp_actions, "恒流充放电 GCD 曲线与容量-循环分析"),
        ):
            button = QToolButton(toolbar)
            button.setText(title)
            button.setMenu(make_submenu(title, actions))
            button.setPopupMode(QToolButton.InstantPopup)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setToolTip(tooltip)
            button.setObjectName("quick_" + title.split()[0].lower())
            toolbar.addWidget(button)
            self.quick_analysis_buttons[title] = button
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("预设:"))
        toolbar.addWidget(self.preset_combo)
        toolbar.addWidget(self.apply_preset_all_btn)
        toolbar.addWidget(self.edit_style_btn)
        toolbar.addSeparator()
        toolbar.addAction(self.export_action)
        toolbar.addAction(self.clear_action)

    def _connect_signals(self) -> None:
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.dataset_model.selection_changed.connect(self._on_dataset_visibility_changed)
        self.dataset_model.order_changed.connect(self._on_dataset_order_changed)
        self.tree.selectionModel().selectionChanged.connect(self._on_tree_selection_changed)
        self.analysis_panel.plot_requested.connect(self._request_plot)
        self.analysis_panel.fit_requested.connect(self.fit_selected_eis)
        self.analysis_panel.options_changed.connect(self._on_options_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_toolbar_preset_changed)
        self.apply_preset_all_btn.clicked.connect(self._apply_preset_to_all)
        self.edit_style_btn.clicked.connect(self.edit_current_style)
        self.log_handler.emitter.message.connect(self._append_log)

    # ------------------------------------------------------------------
    # Import / dataset lifecycle
    # ------------------------------------------------------------------
    def import_files(self) -> None:
        start_dir = self.settings_service.settings.get("app", {}).get("last_directory", "")
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入电化学数据文件（可多选）",
            start_dir,
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not paths:
            return
        self.settings_service.settings.setdefault("app", {})["last_directory"] = str(Path(paths[0]).parent)
        self.settings_service.save()
        self._start_import(paths)

    def _start_import(self, paths: list[str]) -> None:
        if self.import_thread is not None and self.import_thread.isRunning():
            QMessageBox.information(self, "正在导入", "请等待当前导入任务完成")
            return
        self.open_action.setEnabled(False)
        self._progress = QProgressDialog("正在读取数据文件...", None, 0, 0, self)
        self._progress.setWindowTitle("导入数据")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()
        self.import_thread = ImportThread(paths, self, AnalysisSettings(**{k: v for k, v in self.active_analysis.items() if k in AnalysisSettings.__dataclass_fields__}))
        self.import_thread.completed.connect(self._on_import_complete)
        self.import_thread.failed.connect(self._on_import_failed)
        self.import_thread.finished.connect(self._on_import_thread_finished)
        self.import_thread.start()

    def _on_import_thread_finished(self) -> None:
        self.open_action.setEnabled(True)
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        thread = self.import_thread
        if thread is not None:
            self.import_thread = None
            thread.deleteLater()

    def _on_import_failed(self, message: str) -> None:
        self.logger.error("导入失败: %s", message)
        QMessageBox.critical(self, "导入失败", message)

    def _on_import_complete(self, new_dataset: Dataset, issues) -> None:
        try:
            self._handle_import_complete(new_dataset, issues)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("导入后处理失败")
            QMessageBox.critical(self, "导入后处理失败", str(exc))

    def _handle_import_complete(self, new_dataset: Dataset, issues) -> None:
        for issue in issues:
            self.logger.warning("跳过 %s: %s", issue.path, issue.message)
        for warning in new_dataset.warnings:
            self.logger.warning("导入警告: %s", warning)
        if new_dataset.is_empty:
            details = "\n".join(f"{issue.path.name}: {issue.message}" for issue in issues[:8])
            QMessageBox.warning(self, "没有数据", "选中的文件没有可用的 CV/EIS/CP 数据\n" + details)
            return
        was_empty = self.dataset.is_empty
        self.dataset.merge(new_dataset)
        if was_empty:
            self.dataset.name = new_dataset.name
        defaults = self.active_analysis
        default_params = ElectrodeParams(defaults.get("area_cm2"), defaults.get("mass_mg"))
        for run in new_dataset.all_runs():
            if run.params.area_cm2 is None and run.params.mass_mg is None:
                run.params = default_params.copy()
                if isinstance(run, CVRun) and run.summary is not None:
                    from cvanalysis.analysis.cv import summarize_run
                    run.summary = summarize_run(
                        run,
                        outlier_count=int(defaults.get("outlier_count", 1)),
                        outlier_z=(
                            float(defaults.get("outlier_z", 3.0))
                            if str(defaults.get("outlier_method", "trim")) == "zscore"
                            else None
                        ),
                    )
        analysis_settings = AnalysisSettings(
            outlier_count=int(defaults.get("outlier_count", 1)),
            sensitivity_factor=float(defaults.get("sensitivity_factor", 10.0)),
            segmentation=str(defaults.get("segmentation", "robust")),
            outlier_method=str(defaults.get("outlier_method", "trim")),
            outlier_z=float(defaults.get("outlier_z", 3.0)),
        )
        pending = Dataset(
            cv_runs=[r for r in self.dataset.cv_runs if r.summary is None],
            eis_runs=[r for r in self.dataset.eis_runs if r.summary is None],
            cp_runs=[r for r in self.dataset.cp_runs if r.summary is None],
        )
        warnings = refresh_analysis(pending, analysis_settings)
        self.metrics = {run.run_id: run.summary for run in self.dataset.eis_runs if run.summary is not None}
        for warning in warnings:
            self.logger.warning(warning)
        analysis_failures = list(dict.fromkeys(
            [message for message in new_dataset.warnings if "分析失败" in message]
            + [message for message in warnings if "分析失败" in message]
        ))
        self._refresh_model_and_panel()
        if self.tabs.count() == 0:
            if self.dataset.cv_runs:
                self._request_plot("cv_overlay")
            if self.dataset.eis_runs:
                self._request_plot("eis_nyquist")
            if self.dataset.cp_runs:
                self._request_plot("cp_gcd")
        else:
            self._prune_tab_specs()
            self._redraw_all_tabs()
        self.statusBar().showMessage(
            f"导入完成：{len(self.dataset.cv_runs)} 个 CV，"
            f"{len(self.dataset.eis_runs)} 个 EIS，{len(self.dataset.cp_runs)} 个 CP"
        )
        self.logger.info(
            "导入完成: %s 个 CV, %s 个 EIS, %s 个 CP",
            len(self.dataset.cv_runs),
            len(self.dataset.eis_runs),
            len(self.dataset.cp_runs),
        )
        self._mark_dirty()
        if issues or analysis_failures:
            self._show_import_issues(issues, analysis_failures)

    def _show_import_issues(self, issues, analysis_failures=()) -> None:
        lines = [f"{issue.path}: {issue.message}" for issue in issues[:12]]
        lines.extend(analysis_failures[:12])
        if len(issues) + len(analysis_failures) > 12:
            lines.append(f"…… 共 {len(issues) + len(analysis_failures)} 个文件/数据失败")
        QMessageBox.warning(
            self,
            "部分文件导入或分析失败",
            "以下文件未能导入或分析，其他有效文件已正常载入：\n\n" + "\n".join(lines),
        )

    def _refresh_model_and_panel(self) -> None:
        visible = dict(self.dataset_model.visible_runs)
        cycles = dict(self.dataset_model.cycle_selection)
        for run in self.dataset.all_runs():
            visible.setdefault(run.run_id, True)
        self.dataset_model.set_dataset(self.dataset, visible, cycles)
        self.tree.expandAll()
        selected = self._selected_run_ids()
        visible_ids = self.dataset_model.visible_run_ids()
        self.analysis_panel.update_dataset(
            self.dataset,
            selected_run_ids=selected,
            visible_run_ids=visible_ids,
        )
        self.results_panel.update_dataset(
            self.dataset,
            selected_run_ids=selected,
            visible_run_ids=visible_ids,
        )
        self._update_plot_contexts()

    def clear_dataset(self) -> None:
        if self.dataset.is_empty:
            return
        if self._background_busy():
            QMessageBox.information(self, "任务进行中", "请等待当前后台任务结束后再清空数据")
            return
        if not self._confirm_discard_changes("清空数据"):
            return
        if QMessageBox.question(self, "确认", "清空当前所有数据？") != QMessageBox.Yes:
            return
        self.dataset.clear()
        self.fits.clear()
        self.metrics.clear()
        self._close_all_tabs_silent()
        self.dataset_model.set_dataset(self.dataset, {}, {})
        self.analysis_panel.update_dataset(self.dataset)
        self.results_panel.update_dataset(self.dataset)
        self._mark_dirty()
        self.statusBar().showMessage("数据已清空")

    # ------------------------------------------------------------------
    # Tree interactions
    # ------------------------------------------------------------------
    def _selected_run_ids(self) -> list[str]:
        selection = self.tree.selectionModel().selection()
        run_ids: list[str] = []
        for index in selection.indexes():
            if index.column() != 0:
                continue
            for run_id in self.dataset_model.run_ids_for_index(index):
                if run_id not in run_ids:
                    run_ids.append(run_id)
        return run_ids

    def _select_all_runs(self) -> None:
        selection = self.tree.selectionModel()
        if selection is None:
            return
        selection.clearSelection()
        self.tree.expandAll()
        for run in self.dataset.all_runs():
            index = self.dataset_model.index_for_run(run.run_id)
            if index.isValid():
                selection.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _clear_tree_selection(self) -> None:
        selection = self.tree.selectionModel()
        if selection is not None:
            selection.clearSelection()

    def _delete_selected_runs(self) -> None:
        run_ids = self._selected_run_ids()
        if not run_ids:
            QMessageBox.information(self, "没有选择", "请先在数据集树中选择要删除的文件")
            return
        self._remove_runs(run_ids)

    def _on_dataset_visibility_changed(self, *args) -> None:
        self._on_tree_selection_changed()
        self._sync_following_tabs()
        self._mark_dirty()

    def _on_dataset_order_changed(self) -> None:
        ordered_ids = [run.run_id for run in self.dataset.all_runs()]
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab):
                selected = set(tab.spec.run_ids)
                tab.spec.run_ids = [run_id for run_id in ordered_ids if run_id in selected]
        self._on_tree_selection_changed()
        self._redraw_all_tabs()
        self._mark_dirty()
        self.statusBar().showMessage("文件顺序已更新，图例文件序号已同步")

    def _on_tree_selection_changed(self, *args) -> None:
        selected = self._selected_run_ids()
        self._update_file_details(selected)
        visible_ids = self.dataset_model.visible_run_ids()
        self.analysis_panel.update_dataset(
            self.dataset,
            selected_run_ids=selected,
            visible_run_ids=visible_ids,
        )
        self.results_panel.update_dataset(
            self.dataset,
            selected_run_ids=selected,
            visible_run_ids=visible_ids,
        )

    def _sync_following_tabs(self) -> None:
        cv_visible = list(self.dataset_model.visible_run_ids("cv"))
        eis_visible = list(self.dataset_model.visible_run_ids("eis"))
        cp_visible = list(self.dataset_model.visible_run_ids("cp"))
        cv_visible_set = set(cv_visible)
        cv_cycles = {
            run_id: list(cycles)
            for run_id, cycles in self.dataset_model.cycle_selection.items()
            if run_id in cv_visible_set
        }
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if not isinstance(tab, PlotTab) or not tab.spec.follow_dataset:
                continue
            if tab.spec.kind.startswith("cv_"):
                if tab.spec.run_ids == cv_visible and tab.spec.cycle_selection == cv_cycles:
                    continue
                tab.spec.run_ids = list(cv_visible)
                tab.spec.cycle_selection = {
                    run_id: list(cycles) for run_id, cycles in cv_cycles.items()
                }
            elif tab.spec.kind.startswith("cp_"):
                if tab.spec.run_ids == cp_visible:
                    continue
                tab.spec.run_ids = list(cp_visible)
            else:
                if tab.spec.run_ids == eis_visible:
                    continue
                tab.spec.run_ids = list(eis_visible)
            tab.redraw()

    def _update_file_details(self, selected_run_ids: list[str]) -> None:
        if not selected_run_ids:
            cv_count = len(self.dataset.cv_runs)
            eis_count = len(self.dataset.eis_runs)
            cp_count = len(self.dataset.cp_runs)
            if cv_count or eis_count or cp_count:
                self.file_detail_label.setText(
                    f"已加载 {cv_count} 个 CV / {eis_count} 个 EIS / {cp_count} 个 CP 文件"
                )
            else:
                self.file_detail_label.setText("未选择文件")
            return
        if len(selected_run_ids) > 1:
            names = []
            for run_id in selected_run_ids[:4]:
                run = self.dataset.find_run(run_id)
                if run is not None:
                    names.append(run.display_short_name)
            suffix = " …" if len(selected_run_ids) > 4 else ""
            self.file_detail_label.setText(f"已选择 {len(selected_run_ids)} 个文件：" + "；".join(names) + suffix)
            return
        run = self.dataset.find_run(selected_run_ids[0])
        if run is None:
            self.file_detail_label.setText("未选择文件")
            return
        lines = [f"<b>{run.display_name}</b>"]
        if run.source:
            lines.append(str(run.source))
        if isinstance(run, CVRun):
            if run.scan_rate and run.voltage_window:
                lines.append(f"扫速 {run.scan_rate:g} V/s · 窗口 {run.voltage_window:g} V · {len(run.cycles)} 循环")
            else:
                lines.append(f"{len(run.cycles)} 循环")
        elif isinstance(run, EISRun):
            if run.metadata.low_freq and run.metadata.high_freq:
                lines.append(f"{run.metadata.low_freq:.3g}–{run.metadata.high_freq:.3g} Hz · {len(run.freq)} 点")
            else:
                lines.append(f"{len(run.freq)} 点")
        elif isinstance(run, CPRun):
            current_text = format_with_unit(run.applied_current_A, CURRENT, digits=3)
            hold_text = "含保持段" if run.has_hold_data else "无保持段"
            lines.append(f"CP · 电流 {current_text} · 窗口 {run.voltage_window or 0:.3g} V · {hold_text}")
        params = []
        if run.params.area_cm2:
            params.append(f"面积 {run.params.area_cm2:g} cm²")
        if run.params.mass_mg:
            params.append(f"质量 {run.params.mass_mg:g} mg")
        if params:
            lines.append(" · ".join(params))
        template = (run.legend_template or "").strip()
        if template:
            cycle = run.cycles[0] if isinstance(run, CVRun) and run.cycles else None
            label, unknown = preview_label(
                run,
                template,
                cycle=cycle,
                cycle_number=cycle.index if cycle is not None else None,
                file_number=dataset_file_numbers(self.dataset).get(run.run_id),
            )
            legend_text = f"图例: {label or run.legend_name}"
            if unknown:
                legend_text += "（未知字段: " + "、".join("{" + token + "}" for token in unknown) + "）"
            lines.append(legend_text)
        else:
            default_text = (
                "图例: 默认（文件名 / Cycle）"
                if isinstance(run, CVRun)
                else "图例: 默认（文件名）"
            )
            lines.append(default_text)
        self.file_detail_label.setText("<br>".join(lines))

    def _on_tree_double_clicked(self, index: QModelIndex) -> None:
        node = self.dataset_model._node(index)
        if node is None:
            return
        run = node.run
        if isinstance(run, CVRun):
            self.tree.selectionModel().select(
                index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            self._request_plot("cv_overlay", run_ids=[run.run_id])
        elif isinstance(run, EISRun):
            self.tree.selectionModel().select(
                index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            self._request_plot("eis_nyquist", run_ids=[run.run_id])
        elif isinstance(run, CPRun):
            self.tree.selectionModel().select(
                index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            self._request_plot("cp_gcd", run_ids=[run.run_id])

    def _on_tree_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if not index.isValid():
            return
        run_ids = self.dataset_model.run_ids_for_index(index)
        runs = [self.dataset.find_run(run_id) for run_id in run_ids]
        menu = QMenu(self)
        params_action = menu.addAction("设置电极面积/质量...")
        legend_action = menu.addAction("设置数据图例模板...")
        plot_action = menu.addAction("绘制 CV 叠加图")
        eis_action = menu.addAction("绘制 EIS Nyquist")
        cp_action = menu.addAction("绘制 CP / GCD 曲线")
        plot_action.setEnabled(any(isinstance(run, CVRun) for run in runs))
        eis_action.setEnabled(any(isinstance(run, EISRun) for run in runs))
        cp_action.setEnabled(any(isinstance(run, CPRun) for run in runs))
        remove_action = menu.addAction("删除选中数据")
        action = menu.exec(self.tree.viewport().mapToGlobal(position))
        if action == params_action:
            self._edit_params(run_ids)
        elif action == legend_action:
            selected = self._selected_run_ids()
            legend_ids = selected if set(run_ids).issubset(set(selected)) else run_ids
            self._edit_legend_template(legend_ids or run_ids)
        elif action == plot_action:
            self._select_run_ids(run_ids)
            self._request_plot("cv_overlay", run_ids=run_ids)
        elif action == eis_action:
            self._select_run_ids(run_ids)
            self._request_plot("eis_nyquist", run_ids=run_ids)
        elif action == cp_action:
            self._select_run_ids(run_ids)
            self._request_plot("cp_gcd", run_ids=run_ids)
        elif action == remove_action:
            self._remove_runs(run_ids)

    def _select_run_ids(self, run_ids: list[str]) -> None:
        selection_model = self.tree.selectionModel()
        selection_model.clearSelection()
        for run_id in run_ids:
            index = self.dataset_model.index_for_run(run_id)
            if index.isValid():
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _edit_params(self, run_ids: list[str]) -> None:
        if not run_ids:
            return
        first = self.dataset.find_run(run_ids[0])
        dialog = QDialog(self)
        dialog.setWindowTitle("设置电极参数")
        from PySide6.QtWidgets import QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout

        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        area = QDoubleSpinBox()
        area.setRange(0, 1e9)
        area.setDecimals(6)
        area.setSuffix(" cm²")
        area.setSpecialValueText("未设置")
        initial_area = (first.params.area_cm2 or 0.0) if first else 0.0
        area.setValue(initial_area)
        mass = QDoubleSpinBox()
        mass.setRange(0, 1e12)
        mass.setDecimals(6)
        mass.setSuffix(" mg")
        mass.setSpecialValueText("未设置")
        initial_mass = (first.params.mass_mg or 0.0) if first else 0.0
        mass.setValue(initial_mass)
        form.addRow("电极面积:", area)
        form.addRow("活性物质质量:", mass)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        params = ElectrodeParams(area.value() or None, mass.value() or None)
        for run_id in run_ids:
            run = self.dataset.find_run(run_id)
            if run is not None:
                run.params = params.copy()
        # Normalized summaries depend on these parameters.
        refresh_analysis(
            self.dataset,
            AnalysisSettings(
                outlier_count=int(self.active_analysis.get("outlier_count", 1)),
                sensitivity_factor=float(self.active_analysis.get("sensitivity_factor", 10.0)),
                segmentation=str(self.active_analysis.get("segmentation", "robust")),
                outlier_method=str(self.active_analysis.get("outlier_method", "trim")),
                outlier_z=float(self.active_analysis.get("outlier_z", 3.0)),
            ),
        )
        self.metrics = {run.run_id: run.summary for run in self.dataset.eis_runs if run.summary is not None}
        self._refresh_model_and_panel()
        self._redraw_all_tabs()
        self._mark_dirty()
        self.statusBar().showMessage("电极参数已更新")

    def _edit_legend_template_for_selection(self) -> None:
        run_ids = self._selected_run_ids()
        if not run_ids:
            run_ids = self.dataset_model.visible_run_ids()
        if not run_ids:
            QMessageBox.information(
                self,
                "没有可用数据",
                "请先导入数据，或勾选/选择要设置图例模板的数据",
            )
            return
        self._edit_legend_template(run_ids)

    def _edit_legend_template(self, run_ids: list[str]) -> None:
        runs = [run for run in self.dataset.all_runs() if run.run_id in set(run_ids)]
        if not runs:
            return
        dialog = LegendTemplateDialog(runs, parent=self, file_numbers=dataset_file_numbers(self.dataset))
        if dialog.exec() != QDialog.Accepted:
            return
        template = dialog.template()
        for run in runs:
            run.legend_template = template
        self._update_file_details(self._selected_run_ids())
        self._redraw_all_tabs()
        self._mark_dirty()
        self.statusBar().showMessage(
            f"已更新 {len(runs)} 个数据的默认图例模板"
            + ("" if template else "（已恢复默认）")
        )

    def _on_tab_follow_changed(self, tab: PlotTab, checked: bool) -> None:
        if not isinstance(tab, PlotTab):
            return
        if checked:
            self._sync_following_tabs()
            self.statusBar().showMessage("当前图已跟随左侧数据集勾选")
        else:
            self.statusBar().showMessage("当前图已改为独立数据选择")
        self._mark_dirty()

    def _edit_plot_data(self, tab: PlotTab) -> None:
        if not isinstance(tab, PlotTab):
            return
        dialog = PlotDataDialog(self.dataset, tab.spec, tab.spec.kind, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        run_ids = dialog.selected_run_ids()
        cycle_selection = dialog.cycle_selection()
        was_following = tab.spec.follow_dataset
        selection_changed = (
            set(run_ids) != set(tab.spec.run_ids)
            or cycle_selection != tab.spec.cycle_selection
        )
        tab.spec.run_ids = run_ids
        tab.spec.cycle_selection = cycle_selection
        tab.spec.legend_templates = dialog.legend_templates()
        if selection_changed:
            tab.set_follow_dataset(False)
        tab.update_context(
            self.dataset,
            fits=self.fits,
            metrics=self.metrics,
            color_config=self.settings_service.color_config,
            user_presets=self.settings_service.user_presets,
        )
        tab.redraw()
        self._update_file_details(self._selected_run_ids())
        self._mark_dirty()
        suffix = "（已停止跟随勾选）" if selection_changed and was_following else ""
        self.statusBar().showMessage(
            f"当前图已选择 {len(tab.spec.run_ids)} 个数据{suffix}"
        )

    def _remove_runs(self, run_ids: list[str]) -> None:
        if not run_ids:
            return
        if QMessageBox.question(self, "确认", f"删除 {len(run_ids)} 个数据？") != QMessageBox.Yes:
            return
        for run_id in run_ids:
            self.dataset.remove_run(run_id)
            self.fits.pop(run_id, None)
            self.metrics.pop(run_id, None)
        self._refresh_model_and_panel()
        if self.dataset.is_empty:
            self._close_all_tabs_silent()
        else:
            self._prune_tab_specs()
            self._redraw_all_tabs()
        self._mark_dirty()
        self.statusBar().showMessage("数据已删除")

    # ------------------------------------------------------------------
    # Analysis / plotting
    # ------------------------------------------------------------------
    def _request_plot(self, kind: str, run_ids: list[str] | None = None) -> None:
        if kind.startswith("eis_") and not self.analysis_panel.validate_frequency():
            self.analysis_panel.analysis_tabs.setCurrentIndex(1)
            return
        if kind.startswith("cv_"):
            runs = self._cv_runs_for_plot(run_ids)
            if not runs:
                QMessageBox.information(
                    self,
                    "没有可绘制的 CV 数据",
                    "请先在左侧勾选 CV 数据，或右键选择具体文件",
                )
                return
        elif kind.startswith("cp_"):
            runs = self._cp_runs_for_plot(run_ids)
            if not runs:
                QMessageBox.information(
                    self,
                    "没有可绘制的 CP 数据",
                    "请先在左侧勾选 CP 数据，或右键选择具体文件",
                )
                return
        else:
            runs = self._eis_runs_for_plot(run_ids)
            if not runs:
                QMessageBox.information(
                    self,
                    "没有可绘制的 EIS 数据",
                    "请先在左侧勾选 EIS 数据，或右键选择具体文件",
                )
                return
        options = self.analysis_panel.options()
        selected_run_ids = [run.run_id for run in runs]
        cycle_selection = {}
        for run in runs:
            if isinstance(run, CVRun):
                selected = self.dataset_model.selected_cycle_indices(run.run_id)
                if selected is not None:
                    cycle_selection[run.run_id] = list(selected)
        spec = PlotSpec(
            kind=kind,
            run_ids=selected_run_ids,
            cycle_selection=cycle_selection,
            normalization=options["normalization"],
            target_voltage=options["target_voltage"],
            selected_scan_rate=options["selected_scan_rate"],
            fit_model=options["fit_model"],
            fit_enabled=bool(self.fits) and kind.startswith("eis_"),
            frequency_low=options["frequency_low"],
            frequency_high=options["frequency_high"],
            preset=self.settings_service.active_preset,
            renumber_cycles=options.get("renumber_cycles", False),
            show_legend=options.get("show_legend", True),
            show_axes=options.get("show_axes", True),
            annotations=options.get("annotations", True),
            follow_dataset=run_ids is None,
            analysis_options=(
                {
                    "complete_holds": bool(options.get("complete_holds", True)),
                    "include_holds": bool(options.get("include_holds", False)),
                }
                if kind.startswith("cp_")
                else {}
            ),
        )
        tab = self._add_plot_tab(spec)
        self._show_analysis_options(tab)

    def _show_analysis_options(self, tab):
        self.options_panel.bind(tab)
        self.log_dock.show()

    def _on_analysis_options_applied(self, tab):
        options = {
            key: getattr(tab.spec, key)
            for key in (
                "target_voltage",
                "selected_scan_rate",
                "frequency_low",
                "frequency_high",
                "show_legend",
                "show_axes",
                "annotations",
            )
        }
        for key in ("complete_holds", "include_holds"):
            if key in tab.spec.analysis_options:
                options[key] = tab.spec.analysis_options[key]
        self.analysis_panel.set_options(options)
        self._mark_dirty()

    def _cv_runs_for_plot(self, run_ids: list[str] | None = None) -> list[CVRun]:
        if run_ids is not None:
            selected = set(run_ids)
            return [run for run in self.dataset.cv_runs if run.run_id in selected]
        visible = set(self.dataset_model.visible_run_ids("cv"))
        return [run for run in self.dataset.cv_runs if run.run_id in visible]

    def _eis_runs_for_plot(self, run_ids: list[str] | None = None) -> list[EISRun]:
        if run_ids is not None:
            selected = set(run_ids)
            return [run for run in self.dataset.eis_runs if run.run_id in selected]
        visible = set(self.dataset_model.visible_run_ids("eis"))
        return [run for run in self.dataset.eis_runs if run.run_id in visible]

    def _cp_runs_for_plot(self, run_ids: list[str] | None = None) -> list[CPRun]:
        if run_ids is not None:
            selected = set(run_ids)
            return [run for run in self.dataset.cp_runs if run.run_id in selected]
        visible = set(self.dataset_model.visible_run_ids("cp"))
        return [run for run in self.dataset.cp_runs if run.run_id in visible]

    def _eis_runs_for_fit(self) -> list[EISRun]:
        selected = [run for run in self.dataset.eis_runs if run.run_id in set(self._selected_run_ids())]
        if selected:
            return selected
        return self._eis_runs_for_plot()

    def _add_plot_tab(self, spec: PlotSpec) -> PlotTab:
        style = self.settings_service.resolve_style(spec.preset)
        tab = PlotTab(
            spec,
            style,
            self.dataset,
            fits=self.fits,
            metrics=self.metrics,
            color_config=self.settings_service.color_config,
            user_presets=self.settings_service.user_presets,
        )
        tab.message.connect(self.statusBar().showMessage)
        tab.rendered.connect(self._on_plot_rendered)
        tab.preset_changed.connect(self._on_tab_preset_changed)
        tab.data_requested.connect(self._edit_plot_data)
        tab.follow_changed.connect(self._on_tab_follow_changed)
        tab.options_requested.connect(self._show_analysis_options)
        tab.plot_changed.connect(lambda *_: self._mark_dirty())
        index = self.tabs.addTab(tab, spec.label)
        self.tabs.setTabToolTip(index, spec.label)
        self.tabs.setCurrentIndex(index)
        self._update_plot_contexts()
        self._refresh_preset_combo()
        self._mark_dirty()
        return tab

    def _active_plot_tab(self) -> PlotTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, PlotTab) else None

    def _on_plot_rendered(self, tab: PlotTab) -> None:
        if tab is self._active_plot_tab():
            self.options_panel.refresh_axis_scale_labels()

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.options_panel.bind(self._active_plot_tab())
        if widget is not None:
            widget.deleteLater()
            self._mark_dirty()

    def _close_all_tabs_silent(self) -> None:
        self.options_panel.bind(None)
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()

    def close_all_plots(self) -> None:
        had_tabs = self.tabs.count() > 0
        self._close_all_tabs_silent()
        if had_tabs:
            self._mark_dirty()

    def _on_tab_changed(self, index: int) -> None:
        self.options_panel.bind(self._active_plot_tab())
        tab = self.tabs.widget(index)
        if not isinstance(tab, PlotTab):
            self._refresh_preset_combo()
            return
        self._refresh_preset_combo()
        self.analysis_panel.set_options(
            {
                "normalization": tab.spec.normalization,
                "target_voltage": tab.spec.target_voltage,
                "selected_scan_rate": tab.spec.selected_scan_rate,
                "frequency_low": tab.spec.frequency_low,
                "frequency_high": tab.spec.frequency_high,
                "fit_model": tab.spec.fit_model,
                "renumber_cycles": tab.spec.renumber_cycles,
                "show_legend": tab.spec.show_legend,
                "show_axes": tab.spec.show_axes,
                "annotations": tab.spec.annotations,
                "complete_holds": tab.spec.analysis_options.get("complete_holds", True),
                "include_holds": tab.spec.analysis_options.get("include_holds", False),
            }
        )

    def _redraw_all_tabs(self) -> None:
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab):
                tab.update_context(
                    self.dataset,
                    fits=self.fits,
                    metrics=self.metrics,
                    color_config=self.settings_service.color_config,
                    user_presets=self.settings_service.user_presets,
                )
                tab.redraw()

    def _update_plot_contexts(self) -> None:
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab):
                tab.update_context(
                    self.dataset,
                    fits=self.fits,
                    metrics=self.metrics,
                    color_config=self.settings_service.color_config,
                    user_presets=self.settings_service.user_presets,
                )

    def _prune_tab_specs(self) -> None:
        """Drop removed runs from existing plot tabs without changing selection."""
        valid = {run.run_id for run in self.dataset.all_runs()}
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if not isinstance(tab, PlotTab):
                continue
            tab.spec.run_ids = [run_id for run_id in tab.spec.run_ids if run_id in valid]
            tab.spec.cycle_selection = {
                run_id: list(cycles)
                for run_id, cycles in tab.spec.cycle_selection.items()
                if run_id in valid
            }
            tab.spec.legend_templates = {
                run_id: template
                for run_id, template in tab.spec.legend_templates.items()
                if run_id in valid
            }

    def _on_options_changed(self) -> None:
        tab = self._active_plot_tab()
        if tab is None:
            return
        options = self.analysis_panel.options()
        tab.spec.normalization = options["normalization"]
        tab.spec.target_voltage = options["target_voltage"]
        tab.spec.selected_scan_rate = options["selected_scan_rate"]
        tab.spec.frequency_low = options["frequency_low"]
        tab.spec.frequency_high = options["frequency_high"]
        tab.spec.fit_model = options["fit_model"]
        tab.spec.renumber_cycles = bool(options.get("renumber_cycles", False))
        tab.spec.show_legend = bool(options.get("show_legend", True))
        tab.spec.show_axes = bool(options.get("show_axes", True))
        tab.spec.annotations = bool(options.get("annotations", True))
        if tab.spec.kind.startswith("cp_"):
            tab.spec.analysis_options["complete_holds"] = bool(
                options.get("complete_holds", True)
            )
            tab.spec.analysis_options["include_holds"] = bool(
                options.get("include_holds", False)
            )
        if tab.spec.kind.startswith("eis_") and self.fits:
            tab.spec.fit_enabled = True
        self._mark_dirty()
        self._redraw_timer.start()

    def fit_selected_eis(self) -> None:
        if getattr(self, "_fitting", False) or not self.analysis_panel.validate_frequency():
            return
        runs = self._eis_runs_for_fit()
        if not runs:
            QMessageBox.information(self, "没有 EIS 数据", "请先导入或勾选 EIS 数据")
            return
        options = self.analysis_panel.options()
        snapshot = copy.deepcopy(self.dataset)
        self._fitting = True
        self.statusBar().showMessage("正在后台拟合，可继续查看图表…")
        run_ids = [run.run_id for run in runs]
        self.eis_fit_action.setEnabled(False)
        self._run_task(lambda: fit_eis_runs(snapshot, run_ids, model=options["fit_model"],
                       frequency_low=options["frequency_low"], frequency_high=options["frequency_high"]),
                       lambda computed: self._apply_fits(computed, run_ids, options),
                       cleanup=self._finish_fitting)

    def _finish_fitting(self):
        self._fitting = False
        self.eis_fit_action.setEnabled(True)

    def _apply_fits(self, computed, run_ids, options):
        runs = [run for run in self.dataset.eis_runs if run.run_id in run_ids]
        computed = {key: fit for key, fit in computed.items() if self.dataset.find_eis(key)}
        errors = []
        if not computed:
            QMessageBox.critical(self, "拟合失败", "\n".join(errors) or "没有可用的拟合结果")
            return
        for run_id, fit in computed.items():
            self.fits[run_id] = fit
            run = self.dataset.find_eis(run_id)
            if run is not None:
                run.summary = metrics_from_fit(run, fit, run.summary)
                self.metrics[run_id] = run.summary
            if fit.warnings:
                errors.extend(f"{run.display_name if run else run_id}: {w}" for w in fit.warnings)
        self._refresh_model_and_panel()
        self._update_plot_contexts()
        # Create or refresh a fit plot.
        fit_tab = next(
            (self.tabs.widget(i) for i in range(self.tabs.count())
             if isinstance(self.tabs.widget(i), PlotTab) and self.tabs.widget(i).spec.kind == "eis_fit"),
            None,
        )
        if fit_tab is None:
            spec = PlotSpec(
                kind="eis_fit",
                run_ids=[run.run_id for run in runs],
                normalization=options["normalization"],
                fit_model=options["fit_model"],
                fit_enabled=True,
                frequency_low=options["frequency_low"],
                frequency_high=options["frequency_high"],
                preset=self.settings_service.active_preset,
            )
            self._add_plot_tab(spec)
        else:
            fit_tab.spec.run_ids = [run.run_id for run in runs]
            fit_tab.spec.normalization = options["normalization"]
            fit_tab.spec.frequency_low = options["frequency_low"]
            fit_tab.spec.frequency_high = options["frequency_high"]
            fit_tab.redraw()
            self.tabs.setCurrentWidget(fit_tab)
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab) and tab.spec.kind.startswith("eis_"):
                tab.spec.fit_enabled = True
        self._redraw_all_tabs()
        for error in errors:
            self.logger.warning(error)
        self._mark_dirty()
        self.statusBar().showMessage(f"EIS 拟合完成：{len(computed)} 个数据")

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _refresh_preset_combo(self) -> None:
        self.preset_combo.blockSignals(True)
        current = self.settings_service.active_preset
        tab = self._active_plot_tab()
        if tab is not None:
            current = tab.spec.preset
        self.preset_combo.clear()
        for name in preset_names(self.settings_service.user_presets):
            self.preset_combo.addItem(preset_label(name, self.settings_service.user_presets), name)
        index = self.preset_combo.findData(current)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def _on_toolbar_preset_changed(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if not name:
            return
        style = self.settings_service.resolve_style(name)
        tab = self._active_plot_tab()
        self.settings_service.set_active_preset(name)
        if tab is not None:
            tab.set_style(style)
            self._maybe_quick_edit_style(tab, name)
            self._mark_dirty()
        applied_name = tab.spec.preset if tab is not None else name
        self.statusBar().showMessage(
            f"已应用预设: {preset_label(applied_name, self.settings_service.user_presets)}"
        )

    def _on_tab_preset_changed(self, tab: PlotTab, name: str) -> None:
        style = self.settings_service.resolve_style(name)
        tab.set_style(style)
        self.settings_service.set_active_preset(name)
        self._maybe_quick_edit_style(tab, name)
        self._refresh_preset_combo()
        self._mark_dirty()
        self.statusBar().showMessage(
            f"已应用预设: {preset_label(tab.spec.preset, self.settings_service.user_presets)}"
        )

    def _maybe_quick_edit_style(self, tab: PlotTab, name: str) -> None:
        """Open a compact per-plot style editor for non-default presets."""
        if name == DEFAULT_PRESET_NAME:
            return
        dialog = QuickStyleDialog(
            tab.style,
            preset_label(name, self.settings_service.user_presets),
            self,
        )
        if hasattr(dialog, "set_plot_flags"):
            dialog.set_plot_flags(tab.spec.show_legend, tab.spec.annotations)
        dialog.apply_requested.connect(
            lambda overrides, target=tab: self._apply_quick_overrides(target, overrides)
        )
        dialog.save_requested.connect(
            lambda overrides, target=tab, dlg=dialog: self._save_quick_overrides(target, overrides, dlg)
        )
        dialog.exec()

    def _apply_quick_overrides(self, tab: PlotTab, overrides: dict) -> None:
        tab.apply_overrides(overrides)
        self._mark_dirty()
        self.statusBar().showMessage("已应用到当前图（未写入配置）")

    def _save_quick_overrides(self, tab: PlotTab, overrides: dict, dialog: QuickStyleDialog) -> None:
        self._apply_quick_overrides(tab, overrides)
        style = tab.style
        current_name = tab.spec.preset
        current_label = preset_label(current_name, self.settings_service.user_presets)
        user_presets = self.settings_service.user_presets

        box = QMessageBox(self)
        box.setWindowTitle("保存绘图预设")
        box.setText(f"当前预设：{current_label}\n请选择覆盖当前预设，或另存为新预设。")
        overwrite_button = box.addButton("覆盖当前预设", QMessageBox.ButtonRole.AcceptRole)
        save_as_button = box.addButton("另存为新预设...", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or (clicked is not overwrite_button and clicked is not save_as_button):
            return

        if clicked is overwrite_button:
            if current_name in BUILTIN_PRESETS and current_name not in user_presets:
                answer = QMessageBox.question(
                    self,
                    "覆盖内置预设",
                    "这会创建一个同名用户覆盖，不会修改代码中的内置默认值。\n"
                    "删除该用户覆盖后会恢复内置样式，是否继续？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                label = f"{current_label}（用户覆盖）"
            else:
                answer = QMessageBox.question(
                    self,
                    "确认覆盖",
                    f"确定覆盖预设“{current_label}”？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                label = user_presets.get(current_name, {}).get("label", current_label)
            self.settings_service.save_preset(current_name, style, label)
            saved_name = current_name
        else:
            default_name = f"{current_name}-custom" if current_name in BUILTIN_PRESETS else f"{current_name}-copy"
            name, ok = QInputDialog.getText(self, "另存为新预设", "预设名称:", text=default_name)
            if not ok or not name.strip():
                return
            saved_name = name.strip()
            if saved_name in BUILTIN_PRESETS:
                QMessageBox.warning(self, "名称冲突", "内置预设名称不能占用，请使用其他名称。")
                return
            if saved_name in user_presets:
                answer = QMessageBox.question(
                    self,
                    "确认覆盖",
                    f"用户预设“{saved_name}”已存在，是否覆盖？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.settings_service.save_preset(saved_name, style, saved_name)

        saved_style = self.settings_service.resolve_style(saved_name)
        tab.set_style(saved_style, clear_overrides=True)
        self._refresh_preset_combo()
        self.settings_service.set_active_preset(saved_name)
        dialog.accept()
        self._mark_dirty()
        self.statusBar().showMessage(f"绘图预设已保存：{saved_name}")

    def _apply_preset_to_all(self) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        style = self.settings_service.resolve_style(name)
        active_tab = self._active_plot_tab()
        overrides = dict(active_tab.spec.overrides) if active_tab is not None else {}
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab):
                tab.set_style(style)
                if overrides:
                    tab.apply_overrides(overrides)
        self.settings_service.set_active_preset(name)
        if self.tabs.count():
            self._mark_dirty()
        self.statusBar().showMessage("预设已应用到全部图表")

    def edit_current_style(self) -> None:
        tab = self._active_plot_tab()
        style = tab.style if tab else self.settings_service.resolve_style()
        dialog = StyleEditorDialog(style, self)
        if dialog.exec() != QDialog.Accepted:
            return
        edited = dialog.edited_style()
        name, ok = QInputDialog.getText(
            self,
            "保存预设",
            "预设名称:",
            text=style.name if style.name not in BUILTIN_PRESETS else f"{style.name}-custom",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        edited.name = name
        self.settings_service.save_preset(name, edited, name)
        self._refresh_preset_combo()
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, PlotTab) and widget is self._active_plot_tab():
                widget.set_style(edited)
        if tab is not None:
            self._mark_dirty()
        self.statusBar().showMessage(f"预设已保存: {name}")

    def open_preset_manager(self) -> None:
        PresetManagerDialog(self.settings_service, self).exec()
        self._refresh_preset_combo()
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if not isinstance(tab, PlotTab):
                continue
            resolved = self.settings_service.resolve_style(tab.spec.preset)
            if tab.base_style.to_dict() != resolved.to_dict():
                tab.set_style(resolved, clear_overrides=False)
        self._update_plot_contexts()

    # ------------------------------------------------------------------
    # Settings / project / export
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings_service.settings, self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            self._project_analysis = None
            self.settings_service.settings["analysis"] = {
                **self.settings_service.settings.get("analysis", {}),
                **values["analysis"],
            }
            self.settings_service.settings["eis"] = {
                **self.settings_service.settings.get("eis", {}),
                **values["eis"],
            }
            self.settings_service.settings["colors"] = {
                **self.settings_service.settings.get("colors", {}),
                **values.get("colors", {}),
            }
            self.settings_service.settings["ui"] = {
                **self.settings_service.settings.get("ui", {}),
                **values.get("ui", {}),
            }
            self._ui_scale = _safe_ui_scale(self.settings_service.ui_state.get("scale", 1.0))
            self._apply_ui_scale()
            self.setStyleSheet(application_stylesheet(self._ui_scale))
            self.settings_service.save()
            self.analysis_panel.set_options(
                {
                    "normalization": self.active_analysis.get("default_normalization", "none"),
                    "fit_model": self.settings_service.eis.get("fit_model", "auto"),
                }
            )
            if not self.dataset.is_empty:
                refresh_analysis(
                    self.dataset,
                    AnalysisSettings(
                        outlier_count=int(self.active_analysis.get("outlier_count", 1)),
                        sensitivity_factor=float(self.active_analysis.get("sensitivity_factor", 10.0)),
                        segmentation=str(self.active_analysis.get("segmentation", "robust")),
                        outlier_method=str(self.active_analysis.get("outlier_method", "trim")),
                        outlier_z=float(self.active_analysis.get("outlier_z", 3.0)),
                    ),
                    force=True,
                )
                self.metrics = {run.run_id: run.summary for run in self.dataset.eis_runs if run.summary is not None}
                self._refresh_model_and_panel()
                self._redraw_all_tabs()
                self._mark_dirty()
            self.statusBar().showMessage("设置已保存")

    def save_project(self) -> bool:
        """Save to the current .cvproj path, or prompt for one on first save."""
        if self.dataset.is_empty:
            QMessageBox.information(self, "没有数据", "当前没有可保存的数据")
            return False
        if self._background_busy():
            QMessageBox.information(self, "任务进行中", "请等待当前后台任务结束后再保存项目")
            return False
        if self.dataset.path is None:
            return self.save_project_as()
        return self._write_project(Path(self.dataset.path))

    def save_project_as(self) -> bool:
        if self.dataset.is_empty:
            QMessageBox.information(self, "没有数据", "当前没有可保存的数据")
            return False
        if self._background_busy():
            QMessageBox.information(self, "任务进行中", "请等待当前后台任务结束后再保存项目")
            return False
        current = self.dataset.path
        if current is not None:
            default_name = str(current)
        else:
            directory = str(self.settings_service.settings.get("app", {}).get("last_directory", ""))
            filename = f"{self.dataset.name or 'cvanalysis'}.cvproj"
            default_name = str(Path(directory) / filename) if directory else filename
        path, _ = QFileDialog.getSaveFileName(
            self,
            "项目另存为",
            default_name,
            "CVAnalysis 项目 (*.cvproj);;JSON (*.json)",
        )
        if not path:
            return False
        output = Path(path)
        if not output.suffix:
            output = output.with_suffix(".cvproj")
        return self._write_project(output)

    def _write_project(self, path: Path) -> bool:
        specs = []
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PlotTab):
                specs.append(tab.spec)
        try:
            save_project_file(
                path,
                self.dataset,
                name=self.dataset.name,
                visible_runs=dict(self.dataset_model.visible_runs),
                cycle_selection=dict(self.dataset_model.cycle_selection),
                plots=specs,
                active_plot=max(0, self.tabs.currentIndex()),
                analysis_settings=self.active_analysis,
                fits=self.fits,
                styles={name: self.settings_service.resolve_style(name).to_dict() for name in {spec.preset for spec in specs}},
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        self.dataset.path = Path(path)
        self._remember_directory(path)
        self._mark_clean()
        self.statusBar().showMessage(f"项目已保存: {path}")
        return True

    def _remember_directory(self, path: Path) -> None:
        try:
            self.settings_service.settings.setdefault("app", {})["last_directory"] = str(path.parent)
            self.settings_service.save()
        except Exception:  # noqa: BLE001
            self.logger.exception("保存最近目录失败")

    def open_project(self) -> None:
        if self._background_busy():
            QMessageBox.information(self, "任务进行中", "请等待当前后台任务结束后再打开其他项目")
            return
        if not self._confirm_discard_changes("打开其他项目"):
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "CVAnalysis 项目 (*.cvproj);;JSON (*.json)")
        if not path:
            return
        analysis = copy.deepcopy(self.active_analysis)
        def prepare():
            state = load_project(path)
            settings = state.analysis_settings or analysis
            refresh_analysis(state.dataset, AnalysisSettings(**{k: v for k, v in settings.items() if k in AnalysisSettings.__dataclass_fields__}))
            return state

        def apply(state):
            try:
                self._apply_project(state, path)
            except Exception as exc:  # noqa: BLE001 - keep the running app alive
                self.logger.exception("应用项目失败")
                QMessageBox.critical(self, "打开项目失败", str(exc))

        self._run_task(prepare, apply)

    def _apply_project(self, state, path):
        self._loading_project = True
        try:
            self._project_analysis = state.analysis_settings or None
            if state.warnings:
                self.logger.warning("项目加载警告: %s", "; ".join(state.warnings))
                QMessageBox.warning(self, "项目加载警告", "\n".join(state.warnings[:10]))
            self.dataset = state.dataset
            self.dataset.path = Path(path)
            self.fits.clear()
            self.metrics.clear()
            self.metrics = {run.run_id: run.summary for run in self.dataset.eis_runs if run.summary is not None}
            self.fits = state.fits
            for run in self.dataset.eis_runs:
                if run.run_id in self.fits:
                    run.summary = metrics_from_fit(run, self.fits[run.run_id], run.summary)
                    self.metrics[run.run_id] = run.summary
            self._close_all_tabs_silent()
            self.dataset_model.set_dataset(self.dataset, state.visible_runs, state.cycle_selection)
            self.tree.expandAll()
            for spec in state.plots:
                if spec.preset in state.styles:
                    spec.overrides = {**state.styles[spec.preset], **spec.overrides}
                self._add_plot_tab(spec)
            self._sync_following_tabs()
            if state.active_plot < self.tabs.count():
                self.tabs.setCurrentIndex(state.active_plot)
            visible_ids = self.dataset_model.visible_run_ids()
            selected_ids = self._selected_run_ids()
            self.analysis_panel.update_dataset(
                self.dataset,
                selected_run_ids=selected_ids,
                visible_run_ids=visible_ids,
            )
            self.results_panel.update_dataset(
                self.dataset,
                selected_run_ids=selected_ids,
                visible_run_ids=visible_ids,
            )
            self._update_plot_contexts()
        finally:
            self._loading_project = False
            self._dirty = False
            self._update_window_title()
        self.statusBar().showMessage(f"项目已打开: {path}")

    def export_current_plot(self) -> None:
        tab = self._active_plot_tab()
        if tab is None:
            QMessageBox.information(self, "没有图表", "请先创建一个图")
            return
        tab.export_plot()

    def export_analysis_csv(self) -> None:
        if self.dataset.is_empty:
            QMessageBox.information(self, "没有数据", "当前没有可导出的数据")
            return
        directory = QFileDialog.getExistingDirectory(self, "选择 CSV 导出目录")
        if not directory:
            return
        specs = [
            self.tabs.widget(index).spec
            for index in range(self.tabs.count())
            if isinstance(self.tabs.widget(index), PlotTab)
        ]
        try:
            written = export_analysis_csv(self.dataset, directory, fits=self.fits, plots=specs)
            self.statusBar().showMessage(f"已导出 {len(written)} 个 CSV 文件")
            QMessageBox.information(self, "导出完成", "\n".join(str(path) for path in written))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _mark_dirty(self) -> None:
        if self._loading_project or self._dirty:
            return
        self._dirty = True
        self._update_window_title()

    def _mark_clean(self) -> None:
        self._dirty = False
        self._update_window_title()

    def _update_window_title(self) -> None:
        marker = "*" if self._dirty else ""
        if self.dataset.path is not None:
            self.setWindowTitle(f"{BASE_WINDOW_TITLE} — {marker}{self.dataset.path.name}")
        elif self._dirty:
            self.setWindowTitle(f"{BASE_WINDOW_TITLE} *")
        else:
            self.setWindowTitle(BASE_WINDOW_TITLE)

    def _confirm_discard_changes(self, action: str) -> bool:
        if not self._dirty:
            return True
        if os.environ.get("CVANALYSIS_DISABLE_SAVE_PROMPTS") == "1":
            return True
        answer = QMessageBox.question(
            self,
            "未保存的修改",
            f"当前项目有未保存的修改。\n是否在{action}前保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Save:
            return self.save_project()
        return answer == QMessageBox.Discard

    def _background_busy(self) -> bool:
        return bool(self._tasks) or (
            self.import_thread is not None and self.import_thread.isRunning()
        )

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _restore_ui_state(self) -> None:
        ui = self.settings_service.ui_state
        geometry = ui.get("geometry")
        # QMainWindow's saved dock graph is deliberately not restored: Qt6
        # can crash inside Qt6Widgets when a fixed/custom-title dock graph is
        # reapplied.  Window geometry, splitter sizes and column widths are
        # stored independently and preserve the useful workspace state.
        restore_enabled = not os.environ.get("CVANALYSIS_DISABLE_LAYOUT_RESTORE")
        if geometry and restore_enabled:
            try:
                if self.restoreGeometry(bytes.fromhex(geometry)):
                    self._ensure_window_visible()
            except Exception:
                pass
        self._restore_splitter_sizes(ui)
        self.log_dock.setFloating(False)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        if ui.get("bottom_layout_version") != BOTTOM_LAYOUT_VERSION:
            QTimer.singleShot(0, self._reset_bottom_layout)
        widths = ui.get("column_widths", {})
        if isinstance(widths, dict):
            for key, columns in self._column_views().items():
                columns.restore(widths.get(key))

    def _ensure_window_visible(self) -> None:
        screens = QApplication.screens()
        if not screens:
            return
        frame = self.geometry()
        for screen in screens:
            available = screen.availableGeometry()
            overlap = frame.intersected(available)
            if overlap.width() >= 80 and overlap.height() >= 60:
                return
        primary = QApplication.primaryScreen() or screens[0]
        available = primary.availableGeometry()
        width = min(max(480, frame.width()), available.width())
        height = min(max(320, frame.height()), available.height())
        self.resize(width, height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def _column_views(self) -> dict[str, ViewColumns]:
        return {
            "dataset": self.dataset_columns,
            "cv_results": self.results_panel.cv_columns,
            "eis_results": self.results_panel.eis_columns,
            "cp_results": self.results_panel.cp_columns,
        }

    def _apply_default_splitters(self, *, force: bool = False) -> None:
        ui = self.settings_service.ui_state
        if force or not ui.get("dataset_splitter"):
            dataset_height = self.dataset_splitter.height() or 760
            self.dataset_splitter.setSizes(
                [max(180, int(dataset_height * 0.82)), max(90, int(dataset_height * 0.18))]
            )

    def _restore_splitter_sizes(self, ui: dict) -> None:
        sizes = ui.get("bottom_splitter")
        if isinstance(sizes, list) and len(sizes) >= 3 and all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in sizes
        ):
            self.bottom_splitter.setSizes(sizes[:3])
        dataset_sizes = ui.get("dataset_splitter")
        if isinstance(dataset_sizes, list) and len(dataset_sizes) >= 2:
            try:
                self.dataset_splitter.setSizes([int(value) for value in dataset_sizes])
            except Exception:
                pass

    def _save_ui_state(self) -> None:
        try:
            ui = self.settings_service.settings.setdefault("ui", {})
            ui["geometry"] = bytes(self.saveGeometry()).hex()
            # Dock graphs are no longer serialized; explicit geometry,
            # splitter sizes and column widths are sufficient and stable.
            ui["window_state"] = None
            ui["dataset_splitter"] = list(self.dataset_splitter.sizes())
            ui["analysis_splitter"] = None
            ui["bottom_splitter"] = list(self.bottom_splitter.sizes())
            ui["bottom_layout_version"] = BOTTOM_LAYOUT_VERSION
            ui["column_widths"] = {key: columns.widths() for key, columns in self._column_views().items()}
            self.settings_service.save()
        except Exception:
            self.logger.exception("保存窗口状态失败")

    def reset_layout(self) -> None:
        for columns in self._column_views().values():
            columns.reset()
        self.dataset_dock.setFloating(False)
        self.analysis_dock.setFloating(False)
        self.log_dock.setFloating(False)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dataset_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.analysis_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.dataset_dock.show()
        self.analysis_dock.show()
        self.log_dock.show()
        self.resizeDocks([self.dataset_dock, self.analysis_dock], [380, 380], Qt.Horizontal)
        self._reset_bottom_layout()
        QTimer.singleShot(0, lambda: self._apply_default_splitters(force=True))

    def _reset_bottom_layout(self):
        self.log_dock.show()
        self.resizeDocks([self.log_dock], [400], Qt.Vertical)
        right = 520
        left_total = max(600, self.width() - right)
        results = max(330, min(int(left_total * 0.36), max(330, left_total - 260)))
        log = max(260, left_total - results)
        self.bottom_splitter.setSizes([results, log, right])

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 CVAnalysis v2",
            "CVAnalysis v2\n\n"
            "分层架构：解析 / 分析 / 绘图 / 工作区 UI\n"
            "支持多文件 CV、扫速分析、EIS 自动指标与等效电路拟合、"
            "CP/GCD 充电放电容量与效率分析，以及日常/IEEE 绘图预设。\n\n"
            "原始算法与 v1 保持兼容，旧 config.json 会自动迁移。",
        )

    def _run_task(self, task, apply, cleanup=None):
        worker = TaskThread(task, self)
        self._tasks.append(worker)
        worker.completed.connect(apply)
        worker.failed.connect(lambda message: QMessageBox.warning(self, "任务失败", message))
        def finished():
            self._tasks.remove(worker)
            if cleanup:
                cleanup()
            worker.deleteLater()
            if getattr(self, "_closing_tasks", False) and not self._tasks:
                self.close()
        worker.finished.connect(finished)
        worker.start()

    def closeEvent(self, event) -> None:
        if self._tasks:
            self._closing_tasks = True
            for worker in self._tasks:
                worker.requestInterruption()
            event.ignore()
            self.statusBar().showMessage("等待后台任务结束后关闭…")
            return
        if self.import_thread is not None and self.import_thread.isRunning():
            self.import_thread.requestInterruption()
            event.ignore()
            self.statusBar().showMessage("正在停止导入，任务结束后关闭窗口…")
            if not getattr(self, "_closing_after_import", False):
                self._closing_after_import = True
                self.import_thread.finished.connect(self.close)
            return
        if not self._confirm_discard_changes("退出"):
            event.ignore()
            return
        self._save_ui_state()
        super().closeEvent(event)
