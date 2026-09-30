"""
ZiablWinSetup — Управление системным треем (System Tray).
Обеспечивает работу приложения в фоновом режиме, сворачивание в трей,
контекстное меню и быстрый вызов окна по клику на иконку.
"""

import ctypes
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from PIL import Image
import pystray

from app.autostart import is_app_autostart_enabled, set_app_autostart

logger = logging.getLogger("WinSetup")


def _get_icon_image() -> Image.Image:
    """Загружает иконку приложения из assets."""
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    ico_path = assets_dir / "icon.ico"
    png_path = assets_dir / "icon.png"

    if png_path.exists():
        try:
            img = Image.open(png_path)
            return img.resize((32, 32), Image.Resampling.LANCZOS)
        except Exception as e:
            logger.warning(f"Не удалось загрузить icon.png: {e}")

    if ico_path.exists():
        try:
            return Image.open(ico_path)
        except Exception as e:
            logger.warning(f"Не удалось загрузить icon.ico: {e}")

    # Запасной вариант: генерируем аккуратную иконку 32x32
    return Image.new("RGBA", (32, 32), color=(0, 120, 212, 255))


class SystemTrayManager:
    """Управляет иконкой и контекстным меню приложения в трее Windows."""

    def __init__(self, window: Any = None, on_quit_callback: Callable = None):
        self._window = window
        self._on_quit_callback = on_quit_callback
        self._icon: pystray.Icon | None = None
        self._is_visible = True
        self._has_notified_tray = False

    def set_window(self, window: Any):
        self._window = window

    def show_window(self):
        """Показывает главное окно и выводит его на передний план."""
        if not self._window:
            return
        try:
            self._window.show()
            self._window.restore()
            self._is_visible = True

            # Выводим окно на передний план через Win32 API
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, self._window.title)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка отображения окна из трея: {e}")

    def hide_window(self, show_notify: bool = False):
        """Скрывает окно в системный трей."""
        if not self._window:
            return
        try:
            self._window.hide()
            self._is_visible = False

            if show_notify and not self._has_notified_tray and self._icon:
                self._has_notified_tray = True
                try:
                    self._icon.notify(
                        "ZiablWinSetup продолжает работать в системном трее. Кликните по иконке, чтобы открыть.",
                        "ZiablWinSetup свернут в трей"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Ошибка скрытия окна в трей: {e}")

    def toggle_window(self):
        """Переключает видимость окна (клик по иконке трея)."""
        if self._is_visible:
            self.hide_window(show_notify=False)
        else:
            self.show_window()

    def _on_toggle_autostart(self, icon, item):
        new_state = not is_app_autostart_enabled()
        set_app_autostart(new_state)

    def _on_check_updates(self, icon, item):
        self.show_window()
        if self._window:
            try:
                self._window.evaluate_js("if (window.triggerCheckUpdates) window.triggerCheckUpdates();")
            except Exception as e:
                logger.warning(f"Ошибка запуска проверки обновлений из трея: {e}")

    def _on_exit(self, icon, item):
        logger.info("Запрошен выход из приложения через меню трея.")
        if self._on_quit_callback:
            self._on_quit_callback()
        else:
            self.stop()
            if self._window:
                self._window.destroy()

    def start(self):
        """Запускает иконку трея в фоновом потоке."""
        if self._icon is not None:
            return

        image = _get_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("🪟 Показать / Скрыть", lambda icon, item: self.toggle_window(), default=True),
            pystray.MenuItem("🔄 Проверить обновления", self._on_check_updates),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "⚙️ Запускать с Windows",
                self._on_toggle_autostart,
                checked=lambda item: is_app_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Выход", self._on_exit),
        )

        self._icon = pystray.Icon(
            name="ZiablWinSetup",
            icon=image,
            title="ZiablWinSetup — Массовая установка софта",
            menu=menu,
        )

        def runner():
            try:
                logger.info("Системный трей запущен.")
                self._icon.run()
            except Exception as e:
                logger.error(f"Ошибка в цикле системного трея: {e}")

        tray_thread = threading.Thread(target=runner, name="SystemTrayThread", daemon=True)
        tray_thread.start()

    def stop(self):
        """Останавливает и удаляет иконку из трея."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
            logger.info("Системный трей остановлен.")
