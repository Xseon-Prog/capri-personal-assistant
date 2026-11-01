"""Cyberpunk-themed separate viewer for long Capri responses."""
from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

STYLE = """
QDialog, QWidget { background: #08060d; color: #f5dce9; font-family: 'Segoe UI'; font-size: 10pt; }
QLabel#eyebrow { color: #28ff96; font-family: Consolas; font-size: 9pt; font-weight: 700; }
QLabel#title { color: #f5dce9; font-size: 16pt; font-weight: 700; }
QLabel#hint { color: #b49daf; font-size: 9pt; }
QPlainTextEdit { background: #120a18; color: #f5dce9; border: 1px solid #ff2260; border-radius: 4px; padding: 12px; selection-background-color: #ff2260; }
QPushButton { background: #1b0c20; color: #f5dce9; border: 1px solid #ff2260; border-radius: 4px; padding: 8px 14px; min-width: 90px; }
QPushButton:hover { background: #35112b; border-color: #00f0ff; }
QPushButton#primary { background: #ff2260; color: #ffffff; font-weight: 700; }
QScrollBar:vertical { background: #120a18; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #5b263f; min-height: 25px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #ff2260; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class AnswerWindowManager(QObject):
    """Reuses one window, preserving the signal API expected by main.py."""

    def __init__(self):
        super().__init__()
        self.dialog = QDialog()
        self.dialog.setWindowTitle("Капри — полный ответ")
        self.dialog.setWindowFlags(self.dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.dialog.resize(760, 560)
        self.dialog.setMinimumSize(540, 360)
        self.dialog.setStyleSheet(STYLE)
        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        tag = QLabel("// CAPRI :: ПОЛНЫЙ ОТВЕТ")
        tag.setObjectName("eyebrow")
        title = QLabel("Ответ Капри")
        title.setObjectName("title")
        hint = QLabel("Полный текст. Используй прокрутку или скопируй ответ целиком.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(tag)
        layout.addWidget(title)
        layout.addWidget(hint)
        self.viewer = QPlainTextEdit(self.dialog)
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.viewer.setFont(QFont("Consolas", 11))
        layout.addWidget(self.viewer, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        copy_button = QPushButton("Копировать весь ответ")
        copy_button.clicked.connect(self.copy_answer)
        buttons.addWidget(copy_button)
        close_button = QPushButton("Закрыть")
        close_button.setObjectName("primary")
        close_button.clicked.connect(self.dialog.hide)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    @Slot(str)
    def show(self, text: str) -> None:
        self.viewer.setPlainText(text or "")
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def copy_answer(self) -> None:
        QGuiApplication.clipboard().setText(self.viewer.toPlainText())
