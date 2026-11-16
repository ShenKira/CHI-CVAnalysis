"""The shipped icon must load independently of the launch directory."""
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from cvanalysis.ui.app import application_icon_path, create_application
from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.theme import current_theme, set_current_theme


def test_application_icon_loads_and_is_inherited_by_window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    old_icon, old_font, old_qss = QIcon(app.windowIcon()), app.font(), app.styleSheet()
    old_theme = current_theme()
    combo_animation = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    monkeypatch.chdir(tmp_path)
    window = None
    try:
        create_application([])
        assert application_icon_path().is_absolute()
        assert application_icon_path().is_file()
        with Image.open(application_icon_path()) as icon:
            assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.info['sizes']
        assert not app.windowIcon().isNull()
        for side in (16, 32, 48, 256):
            assert not app.windowIcon().pixmap(side, side).isNull()
        window = MainWindow(settings_path=tmp_path / 'icon-settings.json')
        assert not window.windowIcon().isNull()
    finally:
        if window is not None:
            window.close()
            window.deleteLater()
        app.setWindowIcon(old_icon)
        app.setFont(old_font)
        app.setStyleSheet(old_qss)
        set_current_theme(old_theme)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, combo_animation)
        app.processEvents()
