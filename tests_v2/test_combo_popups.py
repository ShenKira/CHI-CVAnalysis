# -*- coding: utf-8 -*-
"""Bottom-right combo popups must keep the opaque popup skin."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.ui.app import create_application
from cvanalysis.ui.glass.controls import LiquidComboView
from cvanalysis.ui.main_window import MainWindow


def test_application_disables_only_combo_popup_animation():
    app = QApplication.instance() or QApplication([])
    combo_animation = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    menu_animation = QApplication.isEffectEnabled(Qt.UI_AnimateMenu)
    try:
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, True)
        create_application([])
        assert not QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        assert QApplication.isEffectEnabled(Qt.UI_AnimateMenu) == menu_animation
    finally:
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, combo_animation)


def test_options_panel_combos_use_opaque_liquid_popups(tmp_path):
    app = QApplication.instance() or QApplication([])
    run = SweepRun(
        "it-popup",
        "sample",
        "it",
        np.array([0.0, 1.0, 2.0]),
        np.array([1e-6, 2e-6, 4e-6]),
        SweepMetadata("test", {}),
    )
    window = MainWindow(settings_path=tmp_path / "combo_popup.json")
    try:
        window.dataset = Dataset(it_runs=[run])
        window._refresh_model_and_panel()
        window._request_plot("it_curve", run_ids=[run.run_id])
        app.processEvents()
        panel = window.options_panel
        combos = panel.findChildren(QComboBox)
        assert combos
        for combo in combos:
            view = combo.view()
            assert isinstance(view, LiquidComboView)
            popup = getattr(view, "_popup", None)
            assert popup is not None
            assert not popup.testAttribute(Qt.WA_TranslucentBackground)
            assert popup.testAttribute(Qt.WA_StyledBackground)
            assert str(popup.styleSheet())

        # Changing the display mode rebuilds the axis unit combo; the new
        # widget must be installed without waiting for a later idle scan.
        mode = panel.controls["it_current_display"]
        mode.setCurrentIndex(mode.findData("reference_capacitance"))
        panel.controls["it_reference_capacitance"].setText("2")
        panel.apply()
        app.processEvents()
        assert panel.controls["it_current_display"].currentData() == "reference_capacitance"
        for combo in panel.findChildren(QComboBox):
            assert isinstance(combo.view(), LiquidComboView)
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()
