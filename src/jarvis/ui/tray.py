"""System tray icon, status/history windows and settings entry point."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

from loguru import logger

from jarvis.ui.control_window import ControlWindow
from jarvis.ui.settings_window import SettingsDialog, write_config

if TYPE_CHECKING:
    from jarvis.app import Services


def _make_icon() -> Any:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#1f6feb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "J")
    painter.end()
    return QIcon(pixmap)


def _status_text(services: Services) -> str:
    status = services.assistant.status()
    voice = "есть" if services.tts.available else "нет"
    voice_loop = "включён" if services.voice is not None else "выключен"
    wake = (
        "включён"
        if services.voice is not None and services.config.assistant.wake_word_enabled
        else "выключен"
    )
    return (
        f"Состояние: {status['state']}\n"
        f"Модель: {status['model']}\n"
        f"Ollama: {'доступна' if status['llm'] else 'недоступна'}\n"
        f"Голос: {voice}\n"
        f"Голосовой режим: {voice_loop}\n"
        f"Wake word: {wake}\n"
        f"Активация: {services.config.assistant.hotkey}\n"
        f"Кнопка «Говорить»: {services.config.assistant.manual_hotkey or 'только в окне'}"
    )


def run_tray(services: Services, on_quit: Any = None) -> int:
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QMenu,
        QMessageBox,
        QTextBrowser,
        QVBoxLayout,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from PySide6.QtWidgets import QSystemTrayIcon

    tray = QSystemTrayIcon(_make_icon())
    tray.setToolTip("Джарвис")
    menu = QMenu()

    def show_status() -> None:
        QMessageBox.information(None, "Джарвис — статус", _status_text(services))

    def show_history() -> None:
        dialog = QDialog()
        dialog.setWindowTitle("История Джарвиса")
        dialog.resize(520, 420)
        browser = QTextBrowser()
        rows = []
        for turn in services.history.recent(20):
            who = "Вы" if turn.role == "user" else "Джарвис"
            rows.append(f"<b>{who}:</b> {turn.text}")
        commands = services.commands.recent(10)
        if commands:
            rows.append("<hr><b>Журнал команд:</b>")
            for command in commands:
                rows.append(f"{command['intent']} — {command['status']}")
        browser.setHtml("<br>".join(rows) or "История пуста.")
        layout = QVBoxLayout(dialog)
        layout.addWidget(browser)
        dialog.exec()

    def show_settings() -> None:
        def apply() -> None:
            write_config(services.root / "config" / "config.toml", services.config)
            tray.showMessage("Джарвис", "Настройки сохранены и применены.")

        dialog = SettingsDialog(
            services.config,
            on_apply=apply,
            tts=services.tts,
            voice_loop=services.voice,
        )
        dialog.exec()

    control = ControlWindow(services)
    control.adjustSize()

    def show_control() -> None:
        if control.isVisible():
            control.hide()
            return
        screen = app.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            control.move(
                area.right() - control.width() - 24,
                area.bottom() - control.height() - 48,
            )
        control.show()
        control.raise_()
        control.activateWindow()

    def open_log() -> None:
        log_path = services.config.logging.file
        if not os.path.isabs(log_path):
            log_path = str(services.config.data_path(services.root) / os.path.basename(log_path))
        if os.path.exists(log_path):
            os.startfile(log_path)  # type: ignore[attr-defined]
        else:
            QMessageBox.warning(None, "Джарвис", "Файл журнала ещё не создан.")

    def quit_app() -> None:
        tray.hide()
        control.hide()
        if on_quit is not None:
            on_quit()
        app.quit()

    menu.addAction("Пульт микрофона", show_control)
    menu.addAction("Статус", show_status)
    menu.addAction("История", show_history)
    menu.addAction("Настройки", show_settings)
    menu.addAction("Открыть журнал", open_log)
    menu.addSeparator()
    menu.addAction("Выход", quit_app)

    tray.setContextMenu(menu)
    tray.show()

    if services.voice is not None:
        show_control()
        if services.config.assistant.wake_word_enabled:
            greeting = (
                f"Скажите «хей, Джарвис», нажмите {services.config.assistant.hotkey} "
                "или кнопку «Говорить»."
            )
        else:
            hotkey = services.config.assistant.manual_hotkey
            greeting = "Нажмите кнопку «Говорить»"
            greeting += f" или {hotkey}." if hotkey else "."
    else:
        greeting = "Голосовой режим недоступен; работает текстовый ввод."
        if services.config.assistant.wake_word_enabled:
            greeting += " Wake word отключён вместе с микрофоном."
    tray.showMessage("Джарвис запущен", greeting)
    logger.info("Tray started")
    return int(app.exec())
