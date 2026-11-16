"""Small rendered preview for user-editable plot text."""
from io import BytesIO

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel
from cvanalysis.ui.theme import theme_color


class FormattedTextPreview(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        self.setAccessibleName("图中文字预览")

    def show_preview(self, text):
        self.setAccessibleDescription(text)
        if len(text) > 256 or text.count("\n") > 5:
            self.setText(text[:256] + "…")
            return
        if "$" not in text:
            self.setText(text)
            return
        try:
            with mpl.rc_context({"text.usetex": False}):
                figure = Figure(figsize=(5, min(2.0, .45 + .23 * text.count("\n"))), dpi=100)
                FigureCanvasAgg(figure)
                figure.patch.set_alpha(0)
                figure.text(.01, .5, text, va="center", fontsize=10,
                            color=theme_color("text"),
                            fontfamily=["Microsoft YaHei", "SimHei", "DejaVu Sans"])
                buffer = BytesIO()
                figure.savefig(buffer, format="png", transparent=True, bbox_inches="tight", pad_inches=.05)
            pixmap = QPixmap()
            if pixmap.loadFromData(buffer.getvalue(), "PNG"):
                if pixmap.width() > 500:
                    pixmap = pixmap.scaledToWidth(500, Qt.SmoothTransformation)
                self.setPixmap(pixmap)
                return
        except (ValueError, RuntimeError, OverflowError):
            pass
        self.setText(text)
