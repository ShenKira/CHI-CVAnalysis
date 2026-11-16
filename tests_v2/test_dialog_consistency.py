"""Smoke checks for the newer editing dialogs and their small-screen controls."""
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceManagerDialog, ItReferenceSettingsDialog
from cvanalysis.ui.dialogs.legend_dialog import LegendAliasDialog, LegendTemplateDialog
from cvanalysis.ui.dialogs.text_preset_dialog import TextPresetEditorDialog
from cvanalysis.ui.theme import application_stylesheet, current_theme, set_current_theme


def test_edit_dialogs_keep_primary_actions_visible(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    previous_qss = app.styleSheet()
    previous_theme = current_theme()
    app.setStyleSheet(application_stylesheet())
    run = synthetic_cv_runs[0]
    unit = {"label": "A", "factor": 1., "dimension": "current"}
    dialogs = [LegendTemplateDialog([run]), LegendAliasDialog(run),
               ItReferenceSettingsDialog(unit), ItReferenceManagerDialog([], unit),
               TextPresetEditorDialog(SettingsService(tmp_path / "settings.json"), "default")]
    try:
        for dialog in dialogs:
            dialog.resize(max(500, dialog.minimumWidth()), max(460, dialog.minimumHeight()))
            dialog.show()
            app.processEvents()
            buttons = dialog.findChild(QDialogButtonBox)
            ok = buttons.button(QDialogButtonBox.Ok)
            assert ok is not None and ok.property("primary") is True
            assert ok.isVisible()
            origin = ok.mapTo(dialog, QPoint())
            assert dialog.rect().contains(origin)
            assert dialog.rect().contains(origin + QPoint(ok.width() - 1, ok.height() - 1))
            dialog.hide()
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
        app.setStyleSheet(previous_qss)
        set_current_theme(previous_theme)
        app.processEvents()
