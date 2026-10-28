"""
Startup Manager API Mixin.
Управление программами автозагрузки Windows (реестр Run, папки Startup, Task Scheduler).
"""

import logging
import subprocess
from typing import Any
import webview
from app.autostart import is_app_autostart_enabled, set_app_autostart
from app.history import action_history
from app.settings import load_settings, save_settings
from app.startup_manager import StartupManager

logger = logging.getLogger("WinSetup")


class StartupApiMixin:
    """Миксин для работы с автозагрузкой Windows."""

    def get_startup_items(self) -> list[dict]:
        """Возвращает актуальный список всех элементов автозагрузки Windows."""
        try:
            return StartupManager.get_all_items()
        except Exception as e:
            logger.error(f"Error getting startup items: {e}")
            return []

    def rescan_startup_items(self) -> list[dict]:
        """Повторно сканирует все источники автозагрузки и уведомляет интерфейс."""
        items = self.get_startup_items()
        if hasattr(self, "call_js"):
            self.call_js("onStartupItemsUpdated", items)
        return items

    def toggle_startup_item(self, item_id: str, enable: bool, record_history: bool = True) -> dict[str, Any]:
        """Включает или отключает элемент автозагрузки Windows."""
        try:
            success, msg = StartupManager.toggle_item(item_id, enable)
            if success:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"⚙️ Автозагрузка: {msg}")
                if record_history:
                    act_title = f"{'Включен' if enable else 'Отключен'} автозапуск: {item_id}"
                    act_title_en = f"{'Enabled' if enable else 'Disabled'} startup: {item_id}"
                    action_history.record_action(
                        action_type="startup_toggle",
                        title=act_title,
                        title_en=act_title_en,
                        revert_data={"item_id": item_id, "enable": not enable},
                        can_undo=True,
                    )
            else:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"⚠️ Ошибка изменения автозагрузки: {msg}")
            return {"success": success, "message": msg}
        except Exception as e:
            logger.error(f"Error toggling startup item {item_id}: {e}")
            return {"success": False, "message": str(e)}

    def delete_startup_item(self, item_id: str) -> dict[str, Any]:
        """Удаляет элемент из автозагрузки Windows."""
        try:
            success, msg = StartupManager.delete_item(item_id)
            if success:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"🗑️ Автозагрузка: {msg}")
            else:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"⚠️ Ошибка удаления из автозагрузки: {msg}")
            return {"success": success, "message": msg}
        except Exception as e:
            logger.error(f"Error deleting startup item {item_id}: {e}")
            return {"success": False, "message": str(e)}

    def open_startup_item_folder(self, item_id: str) -> dict[str, Any]:
        """Открывает папку с файлом элемента автозагрузки в Проводнике."""
        try:
            success, msg = StartupManager.open_folder(item_id)
            if success:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"📁 {msg}")
            else:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"⚠️ Не удалось открыть папку: {msg}")
            return {"success": success, "message": msg}
        except Exception as e:
            logger.error(f"Error opening folder for startup item {item_id}: {e}")
            return {"success": False, "message": str(e)}

    def browse_executable_file(self) -> str:
        """Открывает диалог выбора исполняемого файла (.exe, .bat, .cmd, .lnk)."""
        window = getattr(self, "_window", None)
        if window:
            try:
                res = window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_packages=False,
                    file_types=("Исполняемые файлы (*.exe;*.bat;*.cmd;*.lnk)", "Все файлы (*.*)")
                )
                if res and len(res) > 0:
                    return str(res[0])
            except Exception as e:
                logger.warning(f"Error opening file dialog via webview: {e}")

        try:
            ps_script = """
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.OpenFileDialog
            $f.Filter = "Исполняемые файлы (*.exe;*.bat;*.cmd;*.lnk)|*.exe;*.bat;*.cmd;*.lnk|Все файлы (*.*)|*.*"
            $f.Title = "Выберите программу для автозагрузки"
            if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                Write-Output $f.FileName
            }
            """
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            ).stdout.strip()
            return out
        except Exception:
            return ""

    def add_startup_item(self, name: str, exe_path: str, args: str = "") -> dict[str, Any]:
        """Добавляет программу в автозапуск пользователя."""
        try:
            success, msg = StartupManager.add_custom_item(name, exe_path, args)
            if success:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"🚀 Автозагрузка: {msg}")
                self.rescan_startup_items()
            else:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"⚠️ Ошибка добавления в автозагрузку: {msg}")
            return {"success": success, "message": msg}
        except Exception as e:
            logger.error(f"Error adding startup item {name}: {e}")
            return {"success": False, "message": str(e)}

    def is_app_autostart_active(self) -> bool:
        """Проверяет, включен ли запуск ZiablWinSetup при старте Windows."""
        return is_app_autostart_enabled()

    def set_app_autostart_active(self, enabled: bool) -> dict[str, Any]:
        """Включает или отключает запуск ZiablWinSetup при старте Windows."""
        try:
            success = set_app_autostart(enabled)
            settings = load_settings()
            settings["autostart_with_windows"] = enabled
            save_settings(settings)
            status_text = "включен" if enabled else "отключен"
            if hasattr(self, "call_js"):
                self.call_js("onLog", f"⚙️ Автозапуск ZiablWinSetup с Windows {status_text}.")
            return {"success": success, "enabled": enabled}
        except Exception as e:
            logger.error(f"Error setting app autostart: {e}")
            return {"success": False, "error": str(e)}

    def set_minimize_to_tray_setting(self, enabled: bool) -> dict[str, Any]:
        """Включает или выключает сворачивание в трей при закрытии."""
        try:
            settings = load_settings()
            settings["minimize_to_tray_on_close"] = enabled
            save_settings(settings)
            status_text = "включено" if enabled else "отключено"
            if hasattr(self, "call_js"):
                self.call_js("onLog", f"🪟 Сворачивание в трей при закрытии {status_text}.")
            return {"success": True, "enabled": enabled}
        except Exception as e:
            logger.error(f"Error setting minimize_to_tray_on_close: {e}")
            return {"success": False, "error": str(e)}
