# -*- coding: utf-8 -*-
"""Shared GUI design tokens and QSS contract."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from cvanalysis.ui.theme import (
    application_stylesheet,
    apply_button_role,
)
from cvanalysis.ui.tokens import UiTokens


def test_ui_tokens_clamp_font_and_keep_shape_scale():
    base = UiTokens.from_scale(1.0)
    small = UiTokens.from_scale(0.8)
    large = UiTokens.from_scale(1.6)

    assert base.font_size_pt == 11.0
    assert small.font_size_pt == 9.0
    assert large.font_size_pt == 14.0
    assert base.radius_sm == 4
    assert base.radius_md == 6
    assert base.radius_lg == 8
    assert small.control_height >= 22
    assert large.control_height <= 40


def test_stylesheet_contains_semantic_tokens_and_no_placeholders():
    qss = application_stylesheet(1.0, "default")
    assert "__" not in qss
    assert "#5b7080" in qss  # text_tertiary / muted
    assert "#7a8794" in qss  # border_control
    assert "#8a5a00" in qss  # warning distinct from error
    assert "#a33a3a" in qss  # error
    assert "QPushButton[primary=\"true\"]" in qss
    assert "QPushButton[pill=\"true\"]" in qss
    assert "border-radius: 8px" in qss
    assert "QScrollBar::handle:vertical" in qss
    assert "QDoubleSpinBox:disabled" in qss


def test_button_roles_are_explicit_and_repolishable():
    app = QApplication.instance() or QApplication([])
    button = QPushButton("应用")
    apply_button_role(button, "primary", pill=True)
    assert button.property("primary") is True
    assert button.property("pill") is True
    assert button.property("danger") is False

    apply_button_role(button, "danger")
    assert button.property("primary") is False
    assert button.property("danger") is True
    assert button.property("pill") is False
    button.deleteLater()
    app.processEvents()
