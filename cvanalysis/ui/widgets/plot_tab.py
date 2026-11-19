# -*- coding: utf-8 -*-
"""A tab containing one matplotlib plot document."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QActionGroup, QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
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
from cvanalysis.ui.theme import apply_button_role
from cvanalysis.ui.glass.surfaces import MaterialManager
from cvanalysis.ui.glass.plot_toolbar import CompactNavigationToolbar, FloatingPlotToolbar
from cvanalysis.ui.glass.popups import wrap_menu
from shiboken6 import isValid
from cvanalysis.plotting.paper import paper_overrides
from cvanalysis.plotting.axis_limits import axis_display_units, axis_display_dimensions
from cvanalysis.plotting.it_references import references_from_options, store_references


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
    warning_reported = Signal(object, object)
    plot_changed = Signal(object)
    preset_changed = Signal(object, str)
    data_requested = Signal(object)

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
        text_values: dict | None = None,
        glass_manager=None,
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
        self.text_values = dict(text_values or {})
        self.warnings: list[str] = []
        self.reported_warnings: set[str] = set()
        self.dirty = False
        self._fit_to_view = True
        self.glass_manager = glass_manager or MaterialManager(self)
        self._build_ui()
        self.redraw()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.figure = Figure(figsize=self.style.figure_size, dpi=self.style.dpi)
        self.canvas = AutoResizeCanvas(self.figure)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_context_menu)
        self.canvas.mpl_connect("button_press_event", self._reference_double_click)
        self.canvas_host = CanvasHost(self, self.canvas)
        self.canvas_host.setProperty("themeRole", "canvas-host")
        layout.addWidget(self.canvas_host, stretch=1)
        self.toolbar = CompactNavigationToolbar(self.canvas, self.canvas_host)
        self.toolbar.setMaximumHeight(36)
        self.liquid_toolbar = FloatingPlotToolbar(self, self.glass_manager)

    def _show_context_menu(self, position) -> None:
        if not self.canvas.rect().contains(position):
            position = self.canvas.rect().center()
        menu = self._build_context_menu()
        try:
            menu.exec(self.canvas.mapToGlobal(position))
        finally:
            if isValid(menu):
                menu.deleteLater()

    def _build_settings_menu(self) -> QMenu:
        """Single discoverable entry point for per-plot settings and export."""
        menu = QMenu(self)
        data_action = menu.addAction("本图数据与图例...")
        data_action.triggered.connect(lambda: self.data_requested.emit(self))
        if self.spec.kind == "it_curve":
            references_action = menu.addAction("参考线与图例...")
            references_action.triggered.connect(lambda: self.open_it_reference_manager())
        style_action = menu.addAction("当前图设置...")
        style_action.triggered.connect(self._open_inspector)
        presets = menu.addMenu("绘图预设")
        group = QActionGroup(presets)
        group.setExclusive(True)
        # Keep Python ownership alive as well as the Qt parent chain on PySide.
        menu._preset_menu = presets
        menu._preset_group = group
        for name in preset_names(self.user_presets):
            action = presets.addAction(preset_label(name, self.user_presets))
            action.setCheckable(True)
            action.setChecked(name == self.spec.preset)
            action.triggered.connect(lambda checked=False, value=name: self.preset_changed.emit(self, value))
            group.addAction(action)
        menu.addSeparator()

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
        self._settings_fit_action = fit_action
        fit_action.setCheckable(True)
        fit_action.setChecked(self._fit_to_view)
        fit_action.toggled.connect(self.set_fit_to_view)
        menu.addSeparator()
        menu.addAction("复制当前图像", self.copy_plot)
        menu.addAction("复制当前矢量图", self.copy_vector_plot)
        menu.addAction("导出当前图...", self.export_plot)
        menu.addAction("恢复当前图默认样式", self.reset_style)
        # Keep Python wrappers for submenu actions alive for the popup's full
        # lifetime; some PySide versions otherwise delete a submenu when its
        # transient QAction wrapper is collected.
        menu._action_refs = list(menu.actions())
        presets._action_refs = list(presets.actions())
        ratio_menu._action_refs = list(ratio_menu.actions())
        return menu

    def _build_context_menu(self) -> QMenu:
        source = self._build_settings_menu()
        return wrap_menu(source, self.canvas, self.glass_manager)

    def _open_inspector(self) -> None:
        from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog

        dialog = PlotInspectorDialog(self, self)
        dialog.changed.connect(lambda: self.plot_changed.emit(self))
        dialog.exec()

    def _reference_double_click(self, event) -> None:
        if (self.spec.kind != "it_curve" or not event.dblclick or event.button != 1
                or event.inaxes is None or self.toolbar.mode):
            return
        ax = event.inaxes
        for artist in reversed(ax.texts):
            ref_id = getattr(artist, "_it_reference_id", None)
            if ref_id and artist.get_visible() and artist.contains(event)[0]:
                self.open_it_reference_manager(selected_id=ref_id)
                return
        candidates = []
        for line in ax.lines:
            ref_id = getattr(line, "_it_reference_id", None)
            if ref_id and line.get_visible() and line.contains(event)[0]:
                y = ax.transData.transform((0, line.get_ydata()[0]))[1]
                candidates.append((abs(y - event.y), ref_id))
        if candidates:
            self.open_it_reference_manager(selected_id=min(candidates)[1])

    def open_it_reference_manager(self, *, add=False, selected_id=None):
        if self.spec.kind != "it_curve":
            return
        from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceManagerDialog, ItReferenceSettingsDialog
        axis = self.figure.axes[0] if self.figure.axes else None
        unit = axis_display_units(axis).get("y") if axis is not None else None
        dimension = axis_display_dimensions(axis).get("y") if axis is not None else None
        unit_info = ({"label": unit[0], "factor": unit[1], "dimension": dimension}
                     if unit and dimension else None)
        records = references_from_options(self.spec.analysis_options)
        if add:
            dialog = ItReferenceSettingsDialog(unit_info, parent=self)
            if dialog.exec() != QDialog.Accepted:
                return
            records.append(dialog.record)
        else:
            dialog = ItReferenceManagerDialog(records, unit_info, selected_id, self)
            if dialog.exec() != QDialog.Accepted:
                return
            records = dialog.records
        store_references(self.spec.analysis_options, records)
        self.redraw()
        self.plot_changed.emit(self)

    def _set_canvas_ratio(self, ratio: float | None) -> None:
        overrides = dict(self.spec.overrides)
        if ratio is None:
            overrides.pop("figure_size", None)
            overrides.pop("axes_aspect", None)
        else:
            overrides["figure_size"] = canvas_size_for_ratio(ratio)
            overrides["axes_aspect"] = "auto"
        self._fit_to_view = True
        self._sync_fit_action()
        self.apply_overrides(overrides)
        self.plot_changed.emit(self)

    def set_fit_to_view(self, enabled: bool) -> None:
        self._fit_to_view = bool(enabled)
        self._sync_fit_action()
        self._update_canvas_geometry()

    def _sync_fit_action(self) -> None:
        action = getattr(self, "_settings_fit_action", None)
        if action is not None and isValid(action):
            action.blockSignals(True)
            action.setChecked(self._fit_to_view)
            action.blockSignals(False)

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
        role_colors = self.spec.analysis_options.get("color_overrides_by_role")
        if isinstance(role_colors, dict):
            remaining = {key: value for key, value in role_colors.items() if key not in ("graphics", "text")}
            if remaining:
                self.spec.analysis_options["color_overrides_by_role"] = remaining
            else:
                self.spec.analysis_options.pop("color_overrides_by_role", None)
        self.redraw()
        self.plot_changed.emit(self)

    def update_context(
        self,
        dataset: Dataset,
        *,
        fits: dict[str, EISFitResult] | None = None,
        metrics: dict[str, EISMetrics] | None = None,
        color_config: dict | None = None,
        user_presets: dict | None = None,
        text_values: dict | None = None,
    ) -> None:
        self.dataset = dataset
        if fits is not None:
            self.fits = fits
        if metrics is not None:
            self.metrics = metrics
        if color_config is not None:
            self.color_config = color_config
        if text_values is not None:
            self.text_values = dict(text_values)
        if user_presets is not None:
            self.user_presets = user_presets

    def set_style(self, style: PlotStyle, *, clear_overrides: bool = True) -> None:
        self.base_style = style
        if clear_overrides:
            self.spec.overrides = {}
        self.style = style.with_overrides(self.spec.overrides)
        self.spec.preset = style.name
        self.redraw()

    def set_text_values(self, values: dict | None, *, redraw: bool = True) -> None:
        self.text_values = dict(values or {})
        if redraw:
            self.redraw()

    def apply_overrides(self, overrides: dict) -> None:
        self.spec.overrides = dict(overrides)
        if "legend" in overrides:
            self.spec.show_legend = bool(overrides["legend"])
        if "annotation" in overrides:
            self.spec.annotations = bool(overrides["annotation"])
        self.style = self.base_style.with_overrides(self.spec.overrides)
        self.redraw()

    def mark_dirty(self) -> None:
        """Request a redraw when the tab becomes visible again."""
        self.dirty = True

    def redraw(self) -> None:
        self.style = self.base_style.with_overrides(self.spec.overrides)
        self.style = self.style.with_overrides(paper_overrides(self.spec.paper_layout, self.style))
        self.canvas.set_logical_size(self.style.figure_size)
        self._update_canvas_geometry()
        try:
            self.warnings = render_plot(
                self.figure,
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
                text_values=self.text_values,
            )
        except Exception as exc:  # noqa: BLE001
            self.figure.clear()
            self.figure.add_subplot(111).set_axis_off()
            self.warnings = [f"绘图失败：{exc}"]
        self.canvas.draw_idle()
        self.dirty = False
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
            diagnostics = []
            figure = render_to_new_figure(
                self.dataset,
                self.spec,
                export_style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
                text_values=self.text_values,
                diagnostics=diagnostics,
            )
            self.warning_reported.emit(self, diagnostics)
            export_figure(figure, output, export_style)
            self.message.emit(f"图表已导出: {output}")
        except Exception as exc:  # noqa: BLE001
            self.warning_reported.emit(self, [f"导出失败：{exc}"])

    def copy_plot(self) -> None:
        try:
            diagnostics = []
            figure = render_to_new_figure(
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
                text_values=self.text_values,
                diagnostics=diagnostics,
            )
            self.warning_reported.emit(self, diagnostics)
            buffer = BytesIO()
            figure.savefig(buffer, format="png", dpi=self.style.save_dpi, facecolor=figure.get_facecolor())
            image = QImage.fromData(buffer.getvalue(), "PNG")
            if image.isNull():
                raise RuntimeError("无法生成剪贴板图像")
            QGuiApplication.clipboard().setImage(image)
            self.message.emit("图表已复制到剪贴板")
        except Exception as exc:  # noqa: BLE001
            self.warning_reported.emit(self, [f"复制失败：{exc}"])

    def copy_vector_plot(self) -> None:
        try:
            diagnostics = []
            svg = render_svg_bytes(
                self.dataset,
                self.spec,
                self.style,
                color_config=self.color_config,
                fits=self.fits,
                metrics=self.metrics,
                text_values=self.text_values,
                diagnostics=diagnostics,
            )
            self.warning_reported.emit(self, diagnostics)
            mime = QMimeData()
            mime.setData("image/svg+xml", QByteArray(svg))
            QGuiApplication.clipboard().setMimeData(mime)
            self.message.emit("当前矢量图已复制到剪贴板（SVG）")
        except Exception as exc:  # noqa: BLE001
            self.warning_reported.emit(self, [f"复制失败：{exc}"])
