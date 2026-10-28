# -*- coding: utf-8 -*-
"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        scale = max(1.0, min(1.6, self.font().pointSizeF() / 11.0))
        self.resize(int(500 * scale), int(640 * scale))
        self._build_ui(settings)

    def _build_ui(self, settings: dict) -> None:
        layout = QVBoxLayout(self)
        analysis = settings.get("analysis", {})
        eis = settings.get("eis", {})

        group = QGroupBox("默认分析参数")
        form = QFormLayout(group)
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.0, 1e6)
        self.area_spin.setDecimals(6)
        self.area_spin.setSuffix(" cm²")
        self.area_spin.setValue(float(analysis.get("area_cm2") or 0.0))
        self.area_spin.setSpecialValueText("未设置")
        form.addRow("电极面积:", self.area_spin)

        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setRange(0.0, 1e9)
        self.mass_spin.setDecimals(5)
        self.mass_spin.setSuffix(" mg")
        self.mass_spin.setValue(float(analysis.get("mass_mg") or 0.0))
        self.mass_spin.setSpecialValueText("未设置")
        form.addRow("活性物质质量:", self.mass_spin)

        self.outlier_spin = QSpinBox()
        self.outlier_spin.setRange(0, 100)
        self.outlier_spin.setValue(int(analysis.get("outlier_count", 1)))
        self.outlier_spin.setToolTip("按偏离均值的程度固定剔除最多 N 个循环；这是固定数量裁剪，不是阈值异常检测。0 表示保留全部有效循环。")
        form.addRow("统计裁剪循环数（固定数量）:", self.outlier_spin)

        self.outlier_method_combo = QComboBox()
        self.outlier_method_combo.addItem("固定数量裁剪（默认）", "trim")
        self.outlier_method_combo.addItem("z-score 阈值", "zscore")
        index = self.outlier_method_combo.findData(analysis.get("outlier_method", "trim"))
        self.outlier_method_combo.setCurrentIndex(max(0, index))
        self.outlier_method_combo.setToolTip(
            "固定数量：始终剔除偏离最大的 N 个循环；z-score：只剔除 |z| 超过阈值的循环。"
        )
        form.addRow("离群循环排除方式:", self.outlier_method_combo)
        self.outlier_z_spin = QDoubleSpinBox()
        self.outlier_z_spin.setRange(0.1, 20.0)
        self.outlier_z_spin.setDecimals(2)
        self.outlier_z_spin.setValue(float(analysis.get("outlier_z", 3.0)))
        self.outlier_z_spin.setSuffix(" σ")
        form.addRow("z-score 阈值:", self.outlier_z_spin)
        self.outlier_method_combo.currentIndexChanged.connect(self._sync_outlier_z)
        self._sync_outlier_z()

        self.sensitivity_spin = QDoubleSpinBox()
        self.sensitivity_spin.setRange(0.1, 1e6)
        self.sensitivity_spin.setDecimals(2)
        self.sensitivity_spin.setValue(float(analysis.get("sensitivity_factor", 10.0)))
        form.addRow("电流溢出阈值（倍灵敏度）:", self.sensitivity_spin)

        self.segmentation_combo = QComboBox()
        self.segmentation_combo.addItem("稳健模式（推荐）", "robust")
        self.segmentation_combo.addItem("旧版兼容模式", "legacy")
        index = self.segmentation_combo.findData(analysis.get("segmentation", "robust"))
        self.segmentation_combo.setCurrentIndex(max(0, index))
        form.addRow("循环分割算法:", self.segmentation_combo)

        self.normalization_combo = QComboBox()
        self.normalization_combo.addItem("原始值", "none")
        self.normalization_combo.addItem("按面积", "area")
        self.normalization_combo.addItem("按质量", "mass")
        index = self.normalization_combo.findData(analysis.get("default_normalization", "none"))
        self.normalization_combo.setCurrentIndex(max(0, index))
        form.addRow("默认归一化:", self.normalization_combo)
        layout.addWidget(group)

        color_group = QGroupBox("CV 颜色循环")
        color_form = QFormLayout(color_group)
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem("默认颜色", "default")
        self.color_mode_combo.addItem("自定义颜色", "custom")
        self.color_mode_combo.addItem("xkcd 随机颜色", "xkcd")
        colors = settings.get("colors", {})
        index = self.color_mode_combo.findData(colors.get("mode", "default"))
        self.color_mode_combo.setCurrentIndex(max(0, index))
        color_form.addRow("颜色模式:", self.color_mode_combo)
        self.color_seed_spin = QSpinBox()
        self.color_seed_spin.setRange(0, 2147483647)
        self.color_seed_spin.setValue(int(colors.get("random_seed", 42)))
        color_form.addRow("xkcd 随机种子:", self.color_seed_spin)
        self.color_delta_spin = QDoubleSpinBox()
        self.color_delta_spin.setRange(1.0, 100.0)
        self.color_delta_spin.setDecimals(1)
        self.color_delta_spin.setValue(float(colors.get("delta_e_min", 20.0)))
        color_form.addRow("最小 ΔE:", self.color_delta_spin)
        self.color_random_cb = QCheckBox("启用 xkcd 随机颜色")
        self.color_random_cb.setChecked(bool(colors.get("enable_random", False)))
        color_form.addRow(self.color_random_cb)
        self.custom_colors_edit = QLineEdit(", ".join(colors.get("custom_colors", [])))
        self.custom_colors_edit.setToolTip("逗号分隔的十六进制颜色，用于“自定义颜色”模式")
        color_form.addRow("自定义颜色:", self.custom_colors_edit)
        layout.addWidget(color_group)

        eis_group = QGroupBox("EIS")
        eis_form = QFormLayout(eis_group)
        self.fit_enabled_cb = QCheckBox("打开 EIS 图时自动使用已有拟合")
        self.fit_enabled_cb.setChecked(bool(eis.get("fit_enabled", False)))
        eis_form.addRow(self.fit_enabled_cb)
        self.fit_model_combo = QComboBox()
        self.fit_model_combo.addItem("自动（按谱形推荐）", "auto")
        self.fit_model_combo.addItem("Rs-(Rct||CPE)", "rct_cpe")
        self.fit_model_combo.addItem("Rs-(Rct||C)", "rct_c")
        self.fit_model_combo.addItem("Rs-CPE（阻塞/超电容）", "rs_cpe")
        self.fit_model_combo.addItem("Rs-C", "rs_c")
        index = self.fit_model_combo.findData(eis.get("fit_model", "auto"))
        self.fit_model_combo.setCurrentIndex(max(0, index))
        eis_form.addRow("默认拟合模型:", self.fit_model_combo)
        layout.addWidget(eis_group)

        ui_group = QGroupBox("??")
        ui_form = QFormLayout(ui_group)
        self.ui_scale_spin = QDoubleSpinBox()
        self.ui_scale_spin.setRange(0.8, 1.6)
        self.ui_scale_spin.setSingleStep(0.05)
        self.ui_scale_spin.setDecimals(2)
        self.ui_scale_spin.setValue(float(settings.get("ui", {}).get("scale", 1.0)))
        self.ui_scale_spin.setToolTip("高分辨率屏幕可调到 1.15–1.30；修改后立即生效并保存。")
        ui_form.addRow("界面缩放倍数:", self.ui_scale_spin)
        layout.addWidget(ui_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _sync_outlier_z(self) -> None:
        self.outlier_z_spin.setEnabled(
            self.outlier_method_combo.currentData() == "zscore"
        )

    def values(self) -> dict:
        return {
            "analysis": {
                "area_cm2": self.area_spin.value() or None,
                "mass_mg": self.mass_spin.value() or None,
                "outlier_count": self.outlier_spin.value(),
                "outlier_method": self.outlier_method_combo.currentData(),
                "outlier_z": self.outlier_z_spin.value(),
                "sensitivity_factor": self.sensitivity_spin.value(),
                "segmentation": self.segmentation_combo.currentData(),
                "default_normalization": self.normalization_combo.currentData(),
            },
            "colors": {
                "mode": self.color_mode_combo.currentData(),
                "random_seed": self.color_seed_spin.value(),
                "delta_e_min": self.color_delta_spin.value(),
                "enable_random": self.color_random_cb.isChecked(),
                "custom_colors": [
                    color.strip()
                    for color in self.custom_colors_edit.text().split(",")
                    if color.strip()
                ],
            },
            "eis": {
                "fit_enabled": self.fit_enabled_cb.isChecked(),
                "fit_model": self.fit_model_combo.currentData(),
            },
            "ui": {
                "scale": self.ui_scale_spin.value(),
            },
        }
