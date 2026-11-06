# -*- coding: utf-8 -*-
"""Fixed bottom panel and legacy dock-layout migration checks."""

from __future__ import annotations

import json

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDockWidget

from cvanalysis.domain.models import Dataset
from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.main_window import MainWindow


def test_fixed_bottom_panel_clear_and_layout_restore(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "layout.json"
    window = MainWindow(settings_path=path)
    window.show()
    app.processEvents()
    window._on_import_complete(Dataset(cv_runs=synthetic_cv_runs), [])
    window._request_plot("cv_cap_scan")
    app.processEvents()
    panel = window.options_panel
    assert not panel.isWindow()
    assert window.dockWidgetArea(window.log_dock) == Qt.BottomDockWidgetArea
    assert window.log_dock.features() == QDockWidget.NoDockWidgetFeatures
    assert window.log_dock.height() >= 300
    assert window.bottom_splitter.widget(2) is panel
    window.bottom_splitter.setSizes([430, 700, 580])
    app.processEvents()
    window.close_all_plots()
    assert panel.tab is None and not panel.apply_button.isEnabled()
    assert panel.isVisible()
    window.close()
    restored = MainWindow(settings_path=path)
    restored.show()
    app.processEvents()
    # Offscreen restoreGeometry clamps the window; the fixed panel keeps its minimum.
    assert restored.bottom_splitter.sizes()[2] >= restored.options_panel.minimumWidth()
    assert restored.bottom_splitter.sizes()[0] > 0
    assert restored.bottom_splitter.sizes()[1] > 0
    restored.close()


def test_legacy_dock_layout_state_is_ignored_without_losing_config(tmp_path):
    app = QApplication.instance() or QApplication([])

    for version in (1, 2):
        base = SettingsService(tmp_path / f"base-{version}.json")
        raw = json.loads(base.path.read_text(encoding="utf-8"))
        raw["ui"]["bottom_layout_version"] = version
        if version == 2:
            raw["presets"]["active"] = "ieee-single"
            for key in ("plot", "axis", "grid", "tick"):
                raw.pop(key, None)
            raw["ui"].setdefault("column_widths", {}).setdefault("dataset", {})[
                "名称"
            ] = 222
        path = tmp_path / f"legacy-{version}.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        window = MainWindow(settings_path=path)
        window.show()
        QTimer.singleShot(50, app.quit)
        assert app.exec() == 0
        assert window.dockWidgetArea(window.log_dock) == Qt.BottomDockWidgetArea
        window.close()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["ui"]["bottom_layout_version"] == 4
        assert saved["ui"]["window_state"] is None
        if version == 2:
            assert saved["ui"]["column_widths"]["dataset"]["名称"] == 222
            assert saved["presets"]["active"] == "ieee-single"
