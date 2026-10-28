# -*- coding: utf-8 -*-
"""Data-level legend template editor and shared token widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from cvanalysis.domain.models import CPRun, CVRun, EISRun
from cvanalysis.plotting.legend import file_numbers_for_runs, legend_tokens, render_legend_template, template_uses_cycle


def build_token_combo(parent=None, kind: str | None = None) -> QComboBox:
    combo = QComboBox(parent)
    combo.addItem("插入字段...", "")
    for token in legend_tokens(kind):
        combo.addItem(token.placeholder, token.token)
        combo.setItemData(combo.count() - 1, f"{token.label}：{token.description}", Qt.ToolTipRole)
    return combo


def insert_token(line_edit: QLineEdit, token: str) -> None:
    if not token:
        return
    text = line_edit.text()
    position = line_edit.cursorPosition()
    placeholder = "{" + token + "}"
    line_edit.setText(text[:position] + placeholder + text[position:])
    line_edit.setCursorPosition(position + len(placeholder))
    line_edit.setFocus()


class LegendTemplateDialog(QDialog):
    def __init__(
        self,
        runs: list[CVRun | EISRun | CPRun],
        parent=None,
        *,
        title: str = "设置数据默认图例模板",
        file_numbers: dict[str, int] | None = None,
    ):
        super().__init__(parent)
        self.runs = list(runs)
        self.file_numbers = file_numbers if file_numbers is not None else file_numbers_for_runs(self.runs)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        info = QLabel(
            f"将应用到 {len(self.runs)} 个数据的默认图例。留空时使用文件名或 Cycle 编号。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.template_edit = QLineEdit(self._initial_template())
        kinds = {
            "cv" if isinstance(run, CVRun) else "cp" if isinstance(run, CPRun) else "eis"
            for run in self.runs
        }
        kind = kinds.pop() if len(kinds) == 1 else None
        self.template_edit.setPlaceholderText(self._placeholder_for(kind))
        self.template_edit.textChanged.connect(self._refresh_preview)
        layout.addWidget(QLabel("图例模板:"))
        layout.addWidget(self.template_edit)

        self.token_combo = build_token_combo(self, kind)
        self.token_combo.currentIndexChanged.connect(self._insert_from_combo)
        layout.addWidget(self.token_combo)

        hint = QLabel(
            "字段大小写不敏感。逐循环图例请包含 {cycle_n} 或 {Cycle_Number}。"
            "{file_n} 随数据集文件排序更新；{cycle_n} 保持文件内原始循环号。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #607d8b;")
        layout.addWidget(hint)

        layout.addWidget(QLabel("预览:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(110)
        layout.addWidget(self.preview)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #a33;")
        layout.addWidget(self.warning)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _initial_template(self) -> str:
        templates = {run.legend_template or "" for run in self.runs}
        return templates.pop() if len(templates) == 1 else ""

    @staticmethod
    def _placeholder_for(kind: str | None) -> str:
        if kind == "cv":
            return "例如 {CV_Voltage}-{Cycle_Number}"
        if kind == "eis":
            return "例如 {File_Name}-{Low_Freq}"
        if kind == "cp":
            return "例如 {File_Name}-{Current}"
        return "例如 {Sample_Name}"

    def _insert_from_combo(self, index: int) -> None:
        token = self.token_combo.itemData(index)
        if token:
            insert_token(self.template_edit, token)
            self.token_combo.blockSignals(True)
            self.token_combo.setCurrentIndex(0)
            self.token_combo.blockSignals(False)

    def _refresh_preview(self, *args) -> None:
        template = self.template_edit.text()
        lines: list[str] = []
        unknown: list[str] = []
        for run in self.runs[:4]:
            cycle = run.cycles[0] if isinstance(run, CVRun) and run.cycles else None
            fallback = f"Cycle {cycle.index}" if cycle is not None else run.legend_name
            if template:
                labels: list[str] = []
                unresolved_all: list[str] = []
                cycles = (
                    run.cycles[:3]
                    if isinstance(run, CVRun) and template_uses_cycle(template)
                    else [cycle]
                )
                for item in cycles:
                    label, unresolved = render_legend_template(
                        template, run, cycle=item, file_number=self.file_numbers.get(run.run_id)
                    )
                    labels.append(label if label.strip() else fallback)
                    unresolved_all.extend(unresolved)
                if not labels:
                    labels = [fallback]
                label = " / ".join(labels)
                if isinstance(run, CVRun) and len(run.cycles) > len(cycles):
                    label += " …"
                unknown.extend(token for token in unresolved_all if token not in unknown)
            else:
                label = (
                    f"默认：文件名 / Cycle {cycle.index}"
                    if cycle is not None
                    else "默认：文件名"
                )
            lines.append(f"{run.display_name}  →  {label}")
        self.preview.setPlainText("\n".join(lines))
        self.warning.setText(
            "未知字段: " + "、".join("{" + token + "}" for token in unknown)
            if unknown
            else ""
        )

    def accept(self) -> None:
        if self.warning.text():
            answer = QMessageBox.question(
                self,
                "模板包含未知字段",
                self.warning.text() + "\n这些字段会按原样显示，仍要应用吗？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()

    def template(self) -> str:
        return self.template_edit.text().strip()
