"""Compact always-on-top push-to-talk window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from jarvis.app import Services


class ControlWindow(QWidget):
    """A single button that starts and stops manual microphone capture."""

    def __init__(self, services: Services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self._timer = QTimer(self)

        self.setWindowTitle("Джарвис — микрофон")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(340)

        self.button = QPushButton("🎤 Говорить")
        self.button.setMinimumHeight(64)
        self.button.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self.button.clicked.connect(self._toggle)

        self.status = QLabel("Готов. Нажмите и говорите.")
        self.status.setWordWrap(True)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #666;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.button)
        layout.addWidget(self.status)
        layout.addWidget(self.hint)

        self._timer.timeout.connect(self._refresh)
        self._timer.start(100)
        self._refresh()

    def _toggle(self) -> None:
        voice = self._services.voice
        if voice is None:
            self._set_status("Голосовой режим недоступен: микрофон не открылся.")
            return
        if voice.recording:
            voice.stop_manual_recording()
        else:
            voice.start_manual_recording()
        self._refresh()

    def _refresh(self) -> None:
        voice = self._services.voice
        if voice is None:
            self.button.setText("🎤 Говорить")
            self.button.setEnabled(False)
            self._set_status("Голосовой режим недоступен.")
            self.hint.setText("Запустите без --text и проверьте микрофон.")
            return

        if not voice.running:
            self.button.setText("🎤 Говорить")
            self.button.setEnabled(False)
            self._set_status("Голосовой цикл не запущен.")
        elif voice.recording:
            self.button.setText("⏹ Остановить")
            self.button.setEnabled(True)
            self._set_status("Слушаю… Нажмите ещё раз, чтобы остановить запись.")
        elif voice.busy:
            self.button.setText("⏳ Обрабатываю…")
            self.button.setEnabled(False)
            self._set_status("Распознаю речь и готовлю ответ…")
        elif self._services.tts.is_speaking:
            self.button.setText("🔊 Говорю…")
            self.button.setEnabled(False)
            self._set_status("Озвучиваю ответ…")
        else:
            self.button.setText("🎤 Говорить")
            self.button.setEnabled(True)
            self._set_status("Готов. Нажмите и говорите.")

        hotkey = self._services.config.assistant.manual_hotkey
        wake = "включён" if voice.wake_word_enabled else "выключен"
        hint = f"Wake word: {wake}."
        if hotkey:
            hint += f" Переключение: {hotkey}."
        self.hint.setText(hint)

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Hide instead of closing so the tray application keeps running."""

        event.ignore()
        self.hide()
