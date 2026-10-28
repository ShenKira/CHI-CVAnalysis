# -*- coding: utf-8 -*-
"""A tab containing one matplotlib plot document."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.export import (
    export_figure,
    render_plot,
    render_svg_bytes,
    render_to_new_figure,
)
from cvanalysis.plotting.presets import preset_label, preset_names
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, canvas_size_for_ratio
from cvanalysis.plotting.paper import paper_overrides


class AutoResizeCanvas(FigureCanvasQTAgg):
    """Fit the widget while keeping the figure's logical dimensions fixed.

    The display DPI follows the canvas pixel size. The figure's inches remain
    unchanged, so layout and font proportions match the export figure.
    """

    def __init__(self, figure: Figure):
        super().__init__(figure)
        self._resizing = False
        self._logical_size_inches = tuple(float(value) for value in figure.get_size_inches())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_logical_size(self, size_inches: tuple[float, float]) -> None:
        self._logical_size_inches = tuple(float(value) for value in size_inches)
        self.figure.set_size_inches(*self._logical_size_inches, forward=False)
        width = self.width() * self.device_pixel_ratio
        height = self.height() * self.device_pixel_ratio
        if width >= 20 and height >= 20:
            dpi = min(
                width / self._logical_size_inches[0],
                height / self._logical_size_inches[1],
            )
            self.figure.set_dpi(dpi)

    def resizeEvent(self, event):
        if self._resizing:
            super().resizeEvent(event)
            return
        pixel_ratio = self.device_pixel_ratio
        width = event.size().width() * pixel_ratio
        height = event.size().height() * pixel_ratio
        if width < 20 or height < 20:
            super().resizeEvent(event)
            return
        self._resizing = True
        try:
            logical_width, logical_height = self._logical_size_inches
            dpi_x = width / logical_width
            dpi_y = height / logical_height
            self.figure.set_dpi(min(dpi_x, dpi_y))
            super().resizeEvent(event)
            # FigureCanvasQT derives inches from the widget size during its
            # resize event. Restore the shared logical size after updating DPI.
            self.figure.set_size_inches(*self._logical_size_inches, forward=False)
        finally:
            self._resizing = False


class CanvasHost(QWidget):
    def __init__(self, owner, canvas, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.canvas = canvas
        canvas.setParent(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.owner._update_canvas_geometry()


class PlotTab(QWidget):
    message = Signal(str)
    rendered = Signal(object)
    plot_changed = Signal(object)
    preset_changed = Signal(object, str)
    data_requested = Signal(object)
    follow_changed = Signal(object, bool)
    options_requested = Signal(object)

    def __init__(
        self,
        spec: PlotSpec,
        style: PlotStyle,
        dataset: Dataset,
        *,
        fits: dict[str, EISFitResult] | None = None,
        metrics: dict[str, EISMetrics] | None = None,
        color_config: dict | None = None,
        user_presets: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.spec = spec
        self.base_style = style
        self.style = style.with_overrides(spec.overrides)
        self.style = self.style.with_overrides(paper_overrides(spec.paper_layout, self.style))
        self.dataset = dataset
        self.fits = fits or {}
        self.metrics = metrics or {}
        self.color_config = color_config or {}
        self.user_presets = user_presets or {}
        self.warnings: list[str] = []
        self._fit_to_view = True
        self._build_ui()
        self.redraw()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.title_label = QLabel(self.spec.title or self.spec.label)
        self.title_label.setStyleSheet("font-weight: 600; color: #263238;")
        header.addWidget(self.title_label)
        header.addStretch()
        options_btn = QPushButton("分析 / 论文选项")
        options_btn.setProperty("secondary", True)
        options_btn.clicked.connect(lambda: self.options_requested.emit(self))
        header.addWidget(options_btn)

        self.follow_cb = QCheckBox("跟随勾选")
        self.follow_cb.setToolTip(
            "跟随左侧数据集勾选即时更新本图；用“数据...”自定义数据后会自动取消"
        )
        self.follow_cb.setChecked(self.spec.follow_dataset)
        self.follow_cb.toggled.connect(self._on_follow_toggled)
        header.addWidget(self.follow_cb)

        self.data_btn = QPushButton("数据...")
        self.data_btn.setProperty("secondary", True)
        self.data_btn.clicked.connect(lambda: self.data_requested.emit(self))
        header.addWidget(self.data_btn)
        self._refresh_data_button()

        header.addWidget(QLabel("预设:"))
        self.preset_combo = QComboBox()
        for name in preset_names(self.user_presets):
            self.preset_combo.addItem(preset_label(name, self.user_presets), name)
        index = self.preset_combo.findData(self.spec.preset)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo)
        header.addWidget(self.preset_combo)

        export_btn = QPushButton("导出")
        export_btn.setProperty("secondary", True)
        export_btn.clicked.connect(self.export_plot)
        header.addWidget(export_btn)

        copy_btn = QPushButton("复制")
        copy_btn.setProperty("secondary", True)
        copy_btn.clicked.connect(self.copy_plot)
        header.addWidget(copy_btn)
        layout.addLayout(header)

        self.figure = Figure(figsize=self.style.figure_size, dpi=self.style.dpi)
        self.canvas = AutoResizeCanvas(self.figure)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_context_menu)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        self.canvas_host = CanvasHost(self, self.canvas)
        layout.addWidget(self.canvas_host, stretch=1)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #a33;")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

    def _on_preset_combo(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if name and name != self.spec.preset:
            self.preset_changed.emit(self, name)

    def _show_context_menu(self, position) -> None:
        self._build_context_menu().exec(self.canvas.mapToGlobal(position))

    def _build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        settings_action = menu.addAction("当前图设置...")
        settings_action.triggered.connect(self._open_inspector)

        ratio_menu = QMenu("图片比例", menu)
        menu.addMenu(ratio_menu)
        preset_action = ratio_menu.addAction("保持预设")
        preset_action.triggered.connect(lambda: self._set_canvas_ratio(None))
        for label, ratio in (
            ("1:1", 1.0),
            ("5:4", 1.25),
            ("4:3", 4.0 / 3.0),
            ("16:9", 16.0 / 9.0),
        ):
            action = ratio_menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=ratio: self._set_canvas_ratio(value)
            )

        fit_action = menu.addAction("按比例适应标签页")
        fit_action.setCheckable(True)
        fit_action.setChecked(self._fit_to_view)
        fit_action.toggled.connect(self.set_fit_to_view)
        menu.addSeparator()
        reset_action = menu.addAction("恢复当前图默认样式")
        reset_action.triggered.connect(self.reset_style)
        copy_action = menu.addAction("复制图像")
        copy_action.triggered.connect(self.copy_plot)
        copy_vector_action = menu.addAction("复制当前矢量图")
        copy_vector_action.triggered.connect(self.copy_vector_plot)
        export_action = menu.addAction("导出当前图...")
        export_action.triggered.connect(self.export_plot)
        return menu

    def _open_inspector(self) -> None:
        from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog

        dialog = PlotInspectorDialog(self, self)
        dialog.changed.connect(lambda: self.plot_changed.emit(self))
        dialog.exec()

    def _set_canvas_ratio(self, ratio: float | None) -> None:
        overrides = dict(self.spec.overrides)
        if ratio is None:
            overrides.pop("figure_size", None)
            overrides.pop("axes_aspect", None)
        else:
            overrides["figure_size"] = canvas_size_for_ratio(ratio)
            overrides["axes_aspect"] = "auto"
        self._fit_to_view = True
        self.apply_overrides(overrides)
        self.plot_changed.emit(self)

    def set_fit_to_view(self, enabled: bool) -> None:
        self._fit_to_view = bool(enabled)
        self._update_canvas_geometry()

    def _update_canvas_geometry(self) -> None:
        area = self.canvas_host.contentsRect()
        if area.width() < 20 or area.height() < 20:
            return
        if not self._fit_to_view:
            self.canvas.setGeometry(area)
            return
        ratio = self.style.figure_size[0] / max(self.style.figure_size[1], 1e-9)
        if area.width() / max(area.height(), 1) > ratio:
            height = area.height()
            width = int(height * ratio)
        else:
            width = area.width()
            height = int(width / ratio)
        width = max(1, width)
        height = max(1, height)
        self.canvas.setGeometry(
            area.x() + max(0, (area.width() - width) // 2),
            area.y() + max(0, (area.height() - height) // 2),
            width,
            height,
        )

    def reset_style(self) -> None:
        self.spec.overrides.clear()
        self.spec.title = ""
        self.spec.show_legend = bool(self.base_style.legend)
        self.spec.show_axes = True
        self.spec.annotations = bool(self.base_style.annotation)
        for key in ("color_overrides", "bar_width", "bar_alpha", "fill_alpha", "line_alpha"):
            self.spec.analysis_options.pop(key, None)
        self.redraw()
        self.plot_changed.emit(self)

    def set_preset_name(self, name: str) -> None:
        index = self.preset_combo.findData(name)
        if index >= 0 and index != self.preset_combo.currentIndex():
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(index)
            self.preset_combo.blockSignals(False)

    def update_context(
        self,
        dataset: Dataset,
        *,
        fits: dict[str, EISFitResult] | None = None,
        metrics: dict[str, EISMetrics] | None = None,
        color_config: dict | None = None,
        user_presets: dict | None = None,
    ) -> None:
        self.dataset = dataset
        if fits is not None:
            self.fits = fits
        if metrics is not None:
            self.metrics = metrics
        if color_config is not None:
            self.color_config = color_config
        if user_presets is not None:
            self.user_presets = user_presets
            current = self.spec.preset
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            for name in preset_names(user_presets):
                self.preset_combo.addItem(preset_label(name, user_presets), name)
            index = self.preset_combo.findData(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
            self.preset_combo.blockSignals(False)

    def set_style(self, style: PlotStyle, *, clear_overrides: bool = True) -> None:
        self.base_style = style
        if clear_overrides:
            self.spec.overrides = {}
        self.style = style.with_overrides(self.spec.overrides)
        self.spec.preset = style.name
        self.set_preset_name(style.name)
        self.redraw()

    def apply_overrides(self, overrides: dict) -> None:
        self.spec.overrides = dict(overrides)
        if "legend" in overrides:
            self.spec.show_legend = bool(overrides["legend"])
        if "annotation" in overrides:
            self.spec.annotations = bool(overrides["annotation"])
        self.style = self.base_style.with_overrides(self.spec.overrides)
        self.redraw()

    def _on_follow_toggled(self, checked: bool) -> None:
        self.spec.follow_dataset = checked
        self.follow_changed.emit(self, checked)

    def set_follow_dataset(self, checked: bool) -> None:
        self.follow_cb.blockSignals(True)
        self.follow_cb.setChecked(checked)
        self.follow_cb.blockSignals(False)
        self.spec.follow_dataset = checked

    def _refresh_data_button(self) -> None:
        count = len(self.spec.run_ids)
        self.data_btn.setText(f"数据 ({count})...")
        self.data_btn.setToolTip(
            f"本图当前选择 {count} 个数据；点击选择绘制数据和本图图例模板"
        )

    def redraw(self) -> None:
        self.style = self.base_style.with_overrides(self.spec.overrides)
        self.style = self.style.with_overrides(paper_overrides(self.spec.paper_layout, self.style))
        self.title_label.setText(self.spec.title or self.spec.label)
        self.canvas.set_logical_size(self.style.figure_size)
        self._update_canvas_geometry()
        self._refresh_data_button()
        try:
            self.warnings = render_plot(
                self.figure,
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
            )
        except Exception as exc:  # noqa: BLE001
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                f"绘图失败:\n{exc}",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color="#a33",
                fontsize=max(9, self.style.font_size),
                fontfamily=["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                wrap=True,
            )
            ax.set_axis_off()
            self.warnings = [str(exc)]
        self.canvas.draw_idle()
        self.warning_label.setText("；".join(self.warnings[:3]))
        self.rendered.emit(self)

    def export_plot(self) -> None:
        default_name = f"{self.spec.label}.png"
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出当前图表",
            default_name,
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tif *.tiff)",
        )
        if not path:
            return
        output = Path(path)
        if not output.suffix:
            suffix = ".png"
            if "PDF" in selected_filter:
                suffix = ".pdf"
            elif "SVG" in selected_filter:
                suffix = ".svg"
            elif "TIFF" in selected_filter:
                suffix = ".tif"
            output = output.with_suffix(suffix)
        try:
            export_style = self.style
            if output.suffix.lower() in {".png", ".tif", ".tiff"}:
                dpi, accepted = QInputDialog.getInt(
                    self,
                    "栅格图片分辨率",
                    "导出 DPI（只增加像素，不改变画布尺寸）:",
                    self.style.save_dpi,
                    72,
                    1200,
                    50,
                )
                if not accepted:
                    return
                export_style = self.style.with_overrides({"save_dpi": dpi})
            figure = render_to_new_figure(
                self.dataset,
                self.spec,
                export_style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
            )
            export_figure(figure, output, export_style)
            self.message.emit(f"图表已导出: {output}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def copy_plot(self) -> None:
        try:
            figure = render_to_new_figure(
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
            )
            buffer = BytesIO()
            figure.savefig(buffer, format="png", dpi=self.style.save_dpi, facecolor=figure.get_facecolor())
            image = QImage.fromData(buffer.getvalue(), "PNG")
            if image.isNull():
                raise RuntimeError("无法生成剪贴板图像")
            QGuiApplication.clipboard().setImage(image)
            self.message.emit("图表已复制到剪贴板")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "复制失败", str(exc))

    def copy_vector_plot(self) -> None:
        try:
            svg = render_svg_bytes(
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
            )
            mime = QMimeData()
            mime.setData("image/svg+xml", QByteArray(svg))
            QGuiApplication.clipboard().setMimeData(mime)
            self.message.emit("当前矢量图已复制到剪贴板（SVG）")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "复制失败", str(exc))
