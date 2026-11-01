"""Cyberpunk-styled input, choice, and report windows for Capri (PySide6)."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Slot, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

BG = "#08060d"
PANEL = "#120a18"
PANEL_ALT = "#1b0c20"
PINK = "#ff2260"
CYAN = "#00f0ff"
GREEN = "#28ff96"
TEXT = "#f5dce9"
MUTED = "#b49daf"
BORDER = "#5b263f"

CAPRI_STYLE = f"""
QDialog, QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI'; font-size: 10pt; }}
QLabel#eyebrow {{ color: {GREEN}; font-family: Consolas; font-size: 9pt; font-weight: 700; }}
QLabel#title {{ color: {TEXT}; font-size: 16pt; font-weight: 700; }}
QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLineEdit, QPlainTextEdit, QListWidget {{ background: {PANEL}; color: {TEXT}; border: 1px solid {PINK}; border-radius: 4px; padding: 8px; selection-background-color: {PINK}; selection-color: #ffffff; }}
QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus {{ border: 1px solid {CYAN}; }}
QListWidget {{ padding: 5px; outline: 0; }}
QListWidget::item {{ background: {PANEL}; border: 1px solid transparent; border-radius: 4px; padding: 10px 9px; margin: 2px 0; }}
QListWidget::item:selected {{ background: #2c1028; border: 1px solid {PINK}; color: #ffffff; }}
QPushButton {{ background: {PANEL_ALT}; color: {TEXT}; border: 1px solid {PINK}; border-radius: 4px; padding: 8px 14px; min-width: 88px; }}
QPushButton:hover {{ background: #35112b; border-color: {CYAN}; }}
QPushButton:pressed {{ background: #4c1535; }}
QPushButton#primary {{ background: {PINK}; color: #ffffff; font-weight: 700; border: 1px solid {PINK}; }}
QPushButton#primary:hover {{ background: #ff4779; border-color: {CYAN}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 25px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {PINK}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def _header(parent: QWidget, title: str, eyebrow: str) -> QVBoxLayout:
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    tag = QLabel(eyebrow)
    tag.setObjectName("eyebrow")
    heading = QLabel(title)
    heading.setObjectName("title")
    layout.addWidget(tag)
    layout.addWidget(heading)
    return layout


class CommandInputDialog(QDialog):
    """Themed replacement for QInputDialog.getText used by the command palette."""

    def __init__(self, title: str, prompt: str, parent: QWidget | None = None, default: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title or "Капри")
        self.setMinimumWidth(540)
        self.resize(620, 300)  # CAPRI_CYBERPUNK_UI_V7: wider multiline question input
        self.setStyleSheet(CAPRI_STYLE)
        root = _header(self, "Команда или вопрос", "// CAPRI :: ВВОД")
        hint = QLabel((prompt or "Введи текст для Капри.") + "\nEnter — новая строка; Ctrl+Enter — отправить.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.editor = QPlainTextEdit(self)  # CAPRI_CYBERPUNK_UI_V7
        self.editor.setPlaceholderText("Например: объясни, как работает DNS…")
        self.editor.setPlainText(default)
        self.editor.setMinimumHeight(100)
        self.editor.setMaximumHeight(150)
        root.addWidget(self.editor)
        self._submit_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.editor)
        self._submit_shortcut.activated.connect(self.accept)
        self._submit_shortcut_enter = QShortcut(QKeySequence("Ctrl+Enter"), self.editor)
        self._submit_shortcut_enter.activated.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        send = QPushButton("Передать Капри")
        send.setObjectName("primary")
        send.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(send)
        root.addLayout(buttons)
        self.editor.setFocus()
        self.editor.selectAll()

    @staticmethod
    def getText(parent=None, title="Капри", label="Команда или вопрос:", **kwargs):
        default = kwargs.get("text", "")
        dialog = CommandInputDialog(title, label, parent, default)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.editor.toPlainText(), accepted  # CAPRI_CYBERPUNK_UI_V7


class ChoiceDialog(QDialog):
    """Styled, keyboard-navigable choice dialog for ambiguous app/process matches."""

    def __init__(self, options: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Капри — выбор варианта")
        self.resize(520, min(570, 250 + max(1, len(options)) * 48))
        self.setStyleSheet(CAPRI_STYLE)
        root = _header(self, "Выбери вариант", "// CAPRI :: ВЫБОР")
        hint = QLabel("Нашлось несколько совпадений. Выбери нужное; ничего не будет выполнено до выбора.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.list = QListWidget(self)
        for index, option in enumerate(options, 1):
            item = QListWidgetItem(f"{index:02d}   {option}")
            item.setData(Qt.ItemDataRole.UserRole, option)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        root.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        choose = QPushButton("Выбрать")
        choose.setObjectName("primary")
        choose.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(choose)
        root.addLayout(buttons)
        self.list.setFocus()
        self._enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self.list)
        self._enter.activated.connect(self.accept)

    def selected_value(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""


class ChoiceWindowManager(QObject):
    """Ensures dialogs are created in the GUI thread and sends the selected label back."""

    selected = Signal(str)

    @Slot(object)
    def show(self, options) -> None:
        values = [str(value) for value in (options or [])]
        dialog = ChoiceDialog(values)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_value():
            self.selected.emit(dialog.selected_value())
        else:
            self.selected.emit("отмена")


class ReportWindowManager(QObject):
    """Cyberpunk-themed viewer for generated diagnostics; the report remains saved as TXT."""

    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self.dialog = QDialog()
        self.dialog.setWindowTitle("Капри — системный отчёт")
        self.dialog.resize(900, 680)
        self.dialog.setMinimumSize(620, 420)
        self.dialog.setStyleSheet(CAPRI_STYLE)
        root = _header(self.dialog, "Отчёт диагностики ПК", "// CAPRI :: SYSTEM REPORT")
        self.path_label = QLabel("Отчёт сохранён локально.")
        self.path_label.setObjectName("hint")
        self.path_label.setWordWrap(True)
        root.addWidget(self.path_label)
        self.viewer = QPlainTextEdit(self.dialog)
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.viewer.setFont(QFont("Consolas", 10))
        root.addWidget(self.viewer, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        copy_btn = QPushButton("Копировать отчёт")
        copy_btn.clicked.connect(self.copy_report)
        folder_btn = QPushButton("Открыть папку")
        folder_btn.clicked.connect(self.open_folder)
        close_btn = QPushButton("Закрыть")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.dialog.hide)
        buttons.addWidget(copy_btn)
        buttons.addWidget(folder_btn)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

    @Slot(str, str)
    def show(self, path: str, report: str) -> None:
        self.path = Path(path) if path else None
        self.path_label.setText(f"Сохранённый файл: {self.path}" if self.path else "Отчёт доступен в окне.")
        self.viewer.setPlainText(report or "Отчёт пуст.")
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def copy_report(self) -> None:
        QGuiApplication.clipboard().setText(self.viewer.toPlainText())

    def open_folder(self) -> None:
        if self.path and self.path.parent.exists():
            try:
                os.startfile(str(self.path.parent))
            except (AttributeError, OSError):
                pass
