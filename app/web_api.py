"""
ZiablWinSetup — Web API Bridge.
Связывает Python-бэкенд (загрузка, установка, UAC, твики, обновления) с аппаратным WebView2 GUI.
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import webview

from app.catalog import (
    CATEGORIES,
    AppEntry,
    get_apps_by_category,
    get_catalog,
    get_recommended,
)
from app.detector import detect_installed_apps, uninstall_app, find_leftovers, delete_leftovers
from app.downloader import Downloader, DownloadResult
from app.i18n import STRINGS, CATEGORY_NAMES, i18n
from app.installer import Installer, InstallResult, get_desktop_path, get_exe_dir
from app.metro import (
    get_all_metro_apps,
    remove_metro_app_by_id,
    restore_metro_app_by_id,
    remove_batch_metro,
    restore_batch_metro,
)
from app.settings import (
    get_ignored_update_apps,
    load_settings,
    save_settings,
    set_app_ignored_update,
    set_ignored_update_apps,
    toggle_app_ignored_update,
)
from app.tweaks import apply_tweak_by_id, get_all_tweaks, revert_tweak_by_id
from app.updater import check_updates_sync
from app.utils import check_winget, get_winget_version, is_admin, install_winget, open_winget_store
from app.autostart import is_app_autostart_enabled, set_app_autostart
from app.startup_manager import StartupManager
from app.version import __version__, GITHUB_REPO
from app.self_updater import check_for_app_update, download_and_apply_update
from app.backup_restore import export_apps_backup, import_apps_backup, install_winget_package_sync, get_default_backup_dir
from app.registry_cleaner import scan_registry_issues, clean_registry_issues, get_backups_dir, restore_registry_backup

logger = logging.getLogger("WinSetup")


def _resolve_extract_path(settings: dict) -> Path:
    """
    Определяет путь для распаковки ZIP динамически в реальном времени:
    - 'exe_dir' (по умолчанию): папка рядом с запущенным файлом .exe
    - 'desktop': текущий рабочий стол пользователя (динамически)
    - 'custom': выбранная вручную папка (если она существует на этом компьютере)
    Никогда не сохраняет жестко заданный абсолютный путь по умолчанию!
    """
    mode = settings.get("extract_mode", "exe_dir")
    if mode == "desktop":
        return get_desktop_path()
    elif mode == "custom":
        custom = settings.get("custom_extract_path")
        if custom and os.path.exists(custom):
            return Path(custom)
    return get_exe_dir()


class AppBridge:
    """API-объект, методы которого доступны напрямую из JavaScript через window.pywebview.api."""

    def __init__(self):
        self._window: webview.Window | None = None
        self._downloader = Downloader()
        settings = load_settings()
        self._extract_path = _resolve_extract_path(settings)
        self._installer = Installer(extract_path=self._extract_path)
        self._catalog_map: dict[str, AppEntry] = {a.id: a for a in get_catalog()}
        self._downloaded_results: dict[str, DownloadResult] = {}
        self._is_downloading = False
        self._active_downloads = 0
        self._is_installing_all = False
        self._active_installs = 0
        self._is_upgrading_bulk = False
        self._active_upgrades = 0
        self._installed_apps: dict[str, dict[str, Any]] = {}
        self._available_updates: dict[str, dict[str, Any]] = {}
        self._pending_leftovers: dict[str, dict[str, list[str]]] = {}
        self._last_registry_issues: dict[str, Any] = {}
        self._app_data: dict[str, Any] | None = None
        self._tray_manager: Any = None
        self._is_quitting = False
        self._running_tweaks: dict[str, dict[str, Any]] = {}

    def set_window(self, window: webview.Window):
        self._window = window

    def set_tray_manager(self, tray_manager: Any):
        self._tray_manager = tray_manager

    def is_quitting(self) -> bool:
        return self._is_quitting

    def quit_app(self):
        """Полное закрытие приложения (минуя сворачивание в трей)."""
        logger.info("Quit requested via AppBridge.quit_app()")
        self._is_quitting = True
        if self._tray_manager:
            try:
                self._tray_manager.stop()
            except Exception as e:
                logger.debug(f"Error stopping tray manager: {e}")
        if self._window:
            try:
                self._window.destroy()
            except Exception as e:
                logger.debug(f"Error destroying window: {e}")

    def minimize_window_to_tray(self):
        """Сворачивает главное окно в системный трей."""
        if self._tray_manager:
            self._tray_manager.hide_window(show_notify=True)
        elif self._window:
            self._window.hide()

    def call_js(self, func_name: str, *args):
        """Безопасный вызов JS-функции из любого потока."""
        if not self._window:
            return
        json_args = [json.dumps(a, ensure_ascii=False) for a in args]
        code = f"if (typeof window.{func_name} === 'function') {{ window.{func_name}({', '.join(json_args)}); }}"
        try:
            self._window.evaluate_js(code)
        except Exception as e:
            logger.debug(f"JS call failed: {func_name} -> {e}")

    # ==========================================
    # Инициализация и системная информация
    # ==========================================

    def get_init_data(self) -> dict[str, Any]:
        """Возвращает актуальные данные для страницы на текущем компьютере пользователя."""
        settings = load_settings()
        user_lang = settings.get("language", i18n.lang)
        i18n.set_language(user_lang)

        winget_ok = check_winget()
        winget_ver = get_winget_version() if winget_ok else ""
        admin = is_admin()

        categories_data = [
            {
                "id": cid,
                "name": i18n.cat_name(cid),
                "name_ru": CATEGORY_NAMES.get("ru", {}).get(cid, cid),
                "name_en": CATEGORY_NAMES.get("en", {}).get(cid, cid),
                "count": sum(1 for a in get_catalog() if a.category == cid) if cid != "all" else len(get_catalog()),
            }
            for cid in CATEGORIES
        ]
        apps_data = [
            {
                "id": a.id,
                "name": a.name,
                "description": a.get_description(user_lang),
                "description_en": a.description_en,
                "notes": a.get_notes(user_lang),
                "notes_en": a.notes_en,
                "category": a.category,
                "recommended": a.recommended,
                "installer_type": a.installer_type,
                "has_silent": bool(a.silent_args),
                "web_url": a.web_url,
            }
            for a in get_catalog()
        ]
        recommended_ids = [a.id if hasattr(a, "id") else a for a in get_recommended()]
        installed_map = detect_installed_apps()
        self._installed_apps = installed_map
        ignored_update_ids = settings.get("ignored_update_apps", ["photoshop", "premiere"])

        self._extract_path = _resolve_extract_path(settings)
        self._installer.extract_path = self._extract_path

        system_info = {
            "winget_available": winget_ok,
            "winget_version": winget_ver,
            "is_admin": admin,
            "extract_path": str(self._extract_path),
            "app_version": __version__,
            "repo_url": f"https://github.com/{GITHUB_REPO}",
        }

        # Сбор элементов автозагрузки Windows и статуса автозапуска приложения
        try:
            startup_items = StartupManager.get_all_items()
        except Exception as e:
            logger.warning(f"Ошибка получения элементов автозагрузки: {e}")
            startup_items = []

        app_autostart = is_app_autostart_enabled()

        data = {
            "lang": user_lang,
            "strings": STRINGS.get(user_lang, STRINGS["ru"]),
            "strings_all": STRINGS,
            "categories": categories_data,
            "apps": apps_data,
            "recommended": recommended_ids,
            "installed_apps": installed_map,
            "installed": list(installed_map.keys()),
            "tweaks": get_all_tweaks(user_lang),
            "metro_apps": get_all_metro_apps(user_lang),
            "ignored_updates": ignored_update_ids,
            "system_info": system_info,
            "settings": settings,
            "startup_items": startup_items,
            "app_autostart_enabled": app_autostart,
            "app_version": __version__,
            "repo_url": f"https://github.com/{GITHUB_REPO}",
        }
        self._app_data = data
        return data

    def get_initial_data(self) -> dict[str, Any]:
        """Алиас для get_init_data для обратной совместимости."""
        return self.get_init_data()

    def set_language(self, lang: str) -> dict[str, str]:
        """Смена языка интерфейса на лету."""
        i18n.set_language(lang)
        settings = load_settings()
        settings["language"] = lang
        save_settings(settings)
        return STRINGS.get(lang, STRINGS["ru"])

    def toggle_language(self) -> dict[str, Any]:
        """Переключает язык между ru и en и возвращает актуальные строки, категории, софт и твики."""
        new_lang = "en" if i18n.lang == "ru" else "ru"
        i18n.set_language(new_lang)
        settings = load_settings()
        settings["language"] = new_lang
        save_settings(settings)
        if self._window:
            try:
                self._window.set_title(i18n.t("app_title"))
            except Exception:
                pass

        categories_data = [
            {
                "id": cid,
                "name": i18n.cat_name(cid),
                "name_ru": CATEGORY_NAMES.get("ru", {}).get(cid, cid),
                "name_en": CATEGORY_NAMES.get("en", {}).get(cid, cid),
                "count": sum(1 for a in get_catalog() if a.category == cid) if cid != "all" else len(get_catalog()),
            }
            for cid in CATEGORIES
        ]
        apps_data = [
            {
                "id": a.id,
                "name": a.name,
                "description": a.get_description(new_lang),
                "description_en": a.description_en,
                "notes": a.get_notes(new_lang),
                "notes_en": a.notes_en,
                "category": a.category,
                "recommended": a.recommended,
                "installer_type": a.installer_type,
                "has_silent": bool(a.silent_args),
                "web_url": a.web_url,
            }
            for a in get_catalog()
        ]

        return {
            "lang": new_lang,
            "strings": STRINGS.get(new_lang, STRINGS["ru"]),
            "categories": categories_data,
            "apps": apps_data,
            "tweaks": get_all_tweaks(new_lang),
            "metro_apps": get_all_metro_apps(new_lang),
        }

    def refresh_installed(self) -> list[str]:
        """Асинхронная проверка установленных приложений."""
        def worker():
            installed = detect_installed_apps()
            self.call_js("onInstalledAppsDetected", installed)
        threading.Thread(target=worker, daemon=True).start()
        return []

    def uninstall_app(self, app_id: str) -> dict[str, Any]:
        """Запуск деинсталляции приложения с отображением прогресса и поиском остатков."""
        app = self._catalog_map.get(app_id)
        if not app:
            return {"success": False, "error": f"Приложение {app_id} не найдено"}

        def worker():
            self.call_js("onAppStatus", app_id, "uninstalling", "Деинсталляция...")
            self.call_js("onLog", f"🗑️ {app.name} — запуск процесса удаления...")

            res = uninstall_app(app_id)
            if not res.get("success"):
                err = res.get("error", "Неизвестная ошибка")
                self.call_js("onAppStatus", app_id, "error", err)
                self.call_js("onLog", f"❌ {app.name} — ошибка деинсталляции: {err}")
                return

            leftovers = res.get("leftovers", {"dirs": [], "shortcuts": [], "registry": []})
            total_leftovers = len(leftovers.get("dirs", [])) + len(leftovers.get("shortcuts", [])) + len(leftovers.get("registry", []))

            # Если остатков нет
            if total_leftovers == 0:
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onAppUninstalled", app_id)
                self.call_js("onLog", f"✅ Программа «{app.name}» успешно удалена. Остаточных файлов не обнаружено.")
                try:
                    installed = detect_installed_apps()
                    self.call_js("onInstalledAppsDetected", installed)
                except Exception:
                    pass
                return

            # Проверяем пользовательскую настройку: всегда ли удалять остатки автоматически
            settings = load_settings()
            auto_clean = settings.get("auto_clean_leftovers")

            if auto_clean is True:
                # Автоматическая очистка
                cleaned = delete_leftovers(leftovers)
                summary_parts = []
                if cleaned["dirs"]:
                    summary_parts.append(f"{len(cleaned['dirs'])} папок")
                if cleaned["shortcuts"]:
                    summary_parts.append(f"{len(cleaned['shortcuts'])} ярлыков")
                if cleaned["registry"]:
                    summary_parts.append(f"{len(cleaned['registry'])} записей реестра")
                msg = f"Очищено остатков: {', '.join(summary_parts)}" if summary_parts else "Остатки очищены"
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onAppUninstalled", app_id)
                self.call_js("onLog", f"🧹 Программа «{app.name}» успешно удалена. {msg}.")
                try:
                    installed = detect_installed_apps()
                    self.call_js("onInstalledAppsDetected", installed)
                except Exception:
                    pass
            else:
                # Сохраняем найденные остатки и вызываем модальное окно в стиле Uninstall Tool
                self._pending_leftovers[app_id] = leftovers
                self.call_js("onAppStatus", app_id, "uninstalling", "Очистка остатков...")
                self.call_js("onLog", f"🔍 {app.name} — обнаружено {total_leftovers} остаточных элементов. Ожидание подтверждения...")
                self.call_js("onShowLeftoversModal", app_id, app.name, leftovers)

        threading.Thread(target=worker, daemon=True).start()
        return {"success": True, "message": "Процесс деинсталляции запущен"}

    def clean_pending_leftovers(self, app_id: str, do_clean: bool, remember: bool, selected_leftovers: dict[str, list[str]] | None = None) -> dict[str, Any]:
        """Обрабатывает выбор пользователя из диалогового окна Uninstall Tool."""
        app = self._catalog_map.get(app_id)
        app_name = app.name if app else app_id
        leftovers = self._pending_leftovers.pop(app_id, None)

        if remember:
            settings = load_settings()
            settings["auto_clean_leftovers"] = bool(do_clean)
            save_settings(settings)
            status_text = "включена" if do_clean else "отключена"
            self.call_js("onLog", f"⚙️ Автоматическая очистка остатков {status_text} (выбор запомнен).")

        if do_clean:
            target = selected_leftovers if (selected_leftovers is not None) else leftovers
            if target and (target.get("dirs") or target.get("shortcuts") or target.get("registry")):
                cleaned = delete_leftovers(target)
                summary_parts = []
                if cleaned.get("dirs"):
                    summary_parts.append(f"{len(cleaned['dirs'])} папок")
                if cleaned.get("shortcuts"):
                    summary_parts.append(f"{len(cleaned['shortcuts'])} ярлыков")
                if cleaned.get("registry"):
                    summary_parts.append(f"{len(cleaned['registry'])} записей реестра")
                msg = f"Очищено остатков: {', '.join(summary_parts)}" if summary_parts else "Остатки очищены"
                self.call_js("onLog", f"🧹 Программа «{app_name}» полностью удалена. {msg}.")
            else:
                self.call_js("onLog", f"ℹ️ Выделение со всех остатков «{app_name}» снято, файлы сохранены.")
        else:
            self.call_js("onLog", f"ℹ️ Очистка остатков программы «{app_name}» пропущена пользователем.")

        self.call_js("onAppStatus", app_id, "idle", "")
        self.call_js("onAppUninstalled", app_id)
        try:
            installed = detect_installed_apps()
            self.call_js("onInstalledAppsDetected", installed)
        except Exception:
            pass
        return {"success": True}

    # ==========================================
    # Настройки и исключения
    # ==========================================

    def get_settings(self) -> dict:
        return load_settings()

    def save_settings(self, settings_dict: dict) -> bool:
        return save_settings(settings_dict)

    def update_settings_key(self, key: str, value: Any) -> bool:
        settings = load_settings()
        settings[key] = value
        return save_settings(settings)

    def get_ignored_apps(self) -> list[str]:
        return get_ignored_update_apps()

    def toggle_ignore_update(self, app_id: str) -> bool:
        """Переключает статус исключения приложения из автообновления."""
        is_ignored = toggle_app_ignored_update(app_id)
        app = self._catalog_map.get(app_id)
        name = app.name if app else app_id
        msg = f"🛡️ {name}: {'исключён из автообновления' if is_ignored else 'включён в автообновление'}"
        self.call_js("onLog", msg)
        return is_ignored

    def set_ignore_update(self, app_id: str, ignored: bool) -> list[str]:
        return set_app_ignored_update(app_id, ignored)

    def set_all_ignored_updates(self, app_ids: list[str]) -> list[str]:
        """Устанавливает полный список исключенных приложений."""
        res = set_ignored_update_apps(app_ids)
        self.call_js("onLog", f"🛡️ Обновлен список исключений автообновления: {len(res)} приложений.")
        return res

    # ==========================================
    # Резервное копирование и восстановление программ
    # ==========================================

    def export_apps_backup_dialog(self) -> dict[str, Any]:
        """Диалог сохранения файла и экспорт резервной копии программ."""
        chosen_path = None
        if self._window:
            try:
                import datetime
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                def_name = f"ZiablWinSetup_Backup_{today_str}.ziablbackup"
                res = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=def_name,
                    file_types=("ZiablWinSetup Backup (*.ziablbackup;*.json)", "All Files (*.*)"),
                )
                if res and len(res) > 0:
                    chosen_path = res[0]
                elif res is not None and len(res) == 0:
                    return {"cancelled": True}
            except Exception as e:
                logger.debug(f"Save backup file dialog error: {e}")

        result = export_apps_backup(chosen_path)
        if result.get("success"):
            self.call_js("onLog", f"💾 {result.get('message')}")
        return result

    def import_apps_backup_dialog(self) -> dict[str, Any]:
        """Диалог выбора файла и чтение резервной копии программ."""
        chosen_path = None
        if self._window:
            try:
                res = self._window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    file_types=(
                        "Резервные копии (*.ziablbackup;*.txt;*.json)",
                        "Файлы ZiablWinSetup Backup (*.ziablbackup)",
                        "Текстовые бэкапы (*.txt)",
                        "Все файлы (*.*)",
                    ),
                )
                if res and len(res) > 0:
                    chosen_path = res[0]
                else:
                    return {"cancelled": True}
            except Exception as e:
                logger.error(f"Error opening backup file dialog: {e}")
                return {"success": False, "message": str(e)}

        if not chosen_path:
            return {"cancelled": True}

        result = import_apps_backup(chosen_path)
        if result.get("success"):
            stats = result.get("stats", {})
            self.call_js("onLog", f"📥 Загружен бэкап «{result.get('filename')}»: {stats.get('catalog_total', 0)} программ каталога, {stats.get('system_total', 0)} программ системы.")
        return result

    def install_backup_winget(self, winget_id: str) -> dict[str, Any]:
        """Установка сторонней программы из бэкапа через winget."""
        def worker():
            self.call_js("onLog", f"📦 Установка {winget_id} через winget...")
            res = install_winget_package_sync(winget_id)
            if res.get("success"):
                self.call_js("onLog", f"✅ {res.get('message')}")
            else:
                self.call_js("onLog", f"❌ {res.get('message')}")
            self.call_js("onBackupWingetFinished", winget_id, res.get("success", False), res.get("message", ""))

        threading.Thread(target=worker, daemon=True).start()
        return {"success": True, "message": "Установка запущена в фоне"}

    def open_external_browser_search(self, query: str):
        """Открывает поиск в веб-браузере по названию программы."""
        import urllib.parse
        encoded = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded}+download")

    # ==========================================
    # Очистка и оптимизация реестра Windows
    # ==========================================

    def scan_registry_cleaner(self) -> dict[str, Any]:
        """Сканирует реестр на предмет устаревших/мусорных записей."""
        issues = scan_registry_issues()
        self._last_registry_issues = {item["id"]: item for item in issues}
        self.call_js("onLog", f"🔍 Реестр просканирован. Найдено проблем: {len(issues)}.")
        return {"success": True, "issues": issues, "count": len(issues)}

    def clean_registry_selected(self, selected_ids: list[str]) -> dict[str, Any]:
        """Очищает выбранные записи реестра с обязательным бэкапом."""
        selected_items = [self._last_registry_issues[iid] for iid in selected_ids if iid in self._last_registry_issues]
        if not selected_items:
            return {"success": False, "message": "Нет записей для очистки"}

        res = clean_registry_issues(selected_items)
        if res.get("success"):
            for iid in selected_ids:
                self._last_registry_issues.pop(iid, None)
            self.call_js("onLog", f"🧹 {res.get('message')}")
        else:
            self.call_js("onLog", f"❌ Ошибка очистки реестра: {res.get('message')}")
        return res

    def open_backups_directory(self) -> dict[str, Any]:
        """Открывает папку с созданными резервными копиями в Проводнике."""
        try:
            b_dir = get_backups_dir()
            b_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", str(b_dir.resolve())])
            return {"success": True, "path": str(b_dir)}
        except Exception as e:
            logger.error(f"Failed to open backups dir: {e}")
            return {"success": False, "message": str(e)}

    def _open_file_dialog_native(
        self,
        title: str,
        filter_str_ps: str,
        file_types_webview: tuple[str, ...],
        directory: str = "",
    ) -> str | None:
        """
        Безопасное открытие диалога выбора файла.
        Сначала пробует webview.create_file_dialog со строгим форматом pywebview,
        при любой ошибке мгновенно и надежно использует PowerShell OpenFileDialog.
        """
        if self._window:
            try:
                res = self._window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    directory=directory or None,
                    allow_multiple=False,
                    file_types=file_types_webview,
                )
                if res and len(res) > 0:
                    return str(res[0])
                elif res is not None and len(res) == 0:
                    # Пользователь нажал "Отмена"
                    return None
            except Exception as e:
                logger.warning(f"pywebview create_file_dialog warning (falling back to PowerShell): {e}")

        # PowerShell WinForms OpenFileDialog fallback
        try:
            dir_clause = f'$f.InitialDirectory = "{directory}";' if directory and os.path.exists(directory) else ""
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.OpenFileDialog
            $f.Filter = "{filter_str_ps}"
            $f.Title = "{title}"
            {dir_clause}
            if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                Write-Output $f.FileName
            }}
            """
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                creationflags=NO_WINDOW,
                text=True,
                timeout=60
            ).strip()
            if out and os.path.exists(out):
                return out
        except Exception as e:
            logger.warning(f"PowerShell OpenFileDialog fallback error: {e}")

        return None

    def restore_registry_backup_dialog(self) -> dict[str, Any]:
        """Открывает диалог выбора .reg файла для восстановления реестра из бэкапа."""
        try:
            b_dir = get_backups_dir()
            b_dir.mkdir(parents=True, exist_ok=True)
            title = "Выберите файл резервной копии реестра (.reg)" if i18n.lang == "ru" else "Select Registry Backup File (.reg)"
            reg_path = self._open_file_dialog_native(
                title=title,
                filter_str_ps="Файлы реестра (*.reg)|*.reg|Все файлы (*.*)|*.*",
                file_types_webview=("Файлы реестра (*.reg)", "Все файлы (*.*)"),
                directory=str(b_dir.resolve()),
            )
            if not reg_path:
                return {"success": False, "cancelled": True}
            ok, msg = restore_registry_backup(reg_path)
            if ok:
                self.call_js("onLog", f"🔄 {msg}")
            else:
                self.call_js("onLog", f"❌ {msg}")
            return {"success": ok, "message": msg, "path": reg_path}
        except Exception as e:
            logger.error(f"Error in restore_registry_backup_dialog: {e}")
            return {"success": False, "message": str(e)}

    def restore_registry_from_text(self, reg_text: str, filename: str = "") -> dict[str, Any]:
        """Восстанавливает реестр из переданного текста .reg файла."""
        try:
            import tempfile
            from app.registry_cleaner import restore_registry_backup
            clean_name = Path(filename).name if filename else "backup.reg"
            temp_file = Path(tempfile.gettempdir()) / f"ziabl_restore_{clean_name}"
            temp_file.write_text(reg_text, encoding="utf-8-sig")
            ok, msg = restore_registry_backup(str(temp_file.resolve()))
            try:
                temp_file.unlink(missing_ok=True)
            except Exception:
                pass
            if ok:
                self.call_js("onLog", f"🔄 {msg}")
            else:
                self.call_js("onLog", f"❌ {msg}")
            return {"success": ok, "message": msg}
        except Exception as e:
            logger.error(f"Error in restore_registry_from_text: {e}")
            return {"success": False, "message": str(e)}

    # ==========================================
    # Сканер файлов VirusTotal API
    # ==========================================

    def get_virustotal_config(self) -> dict[str, Any]:
        """Возвращает статус наличия API ключа VirusTotal."""
        from app.virustotal import get_virustotal_api_key
        key = get_virustotal_api_key()
        masked = f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else ("***" if key else "")
        return {
            "has_key": bool(key),
            "masked_key": masked,
        }

    def save_virustotal_api_key(self, api_key: str) -> dict[str, Any]:
        """Сохраняет и строго валидирует пользовательский API ключ VirusTotal."""
        from app.virustotal import set_virustotal_api_key, validate_virustotal_api_key
        key = (api_key or "").strip()
        if not key:
            set_virustotal_api_key("")
            msg = "API ключ VirusTotal удален." if i18n.lang == "ru" else "VirusTotal API key removed."
            self.call_js("onLog", f"ℹ️ {msg}")
            return {"success": True, "has_key": False, "message": msg}

        valid, err_msg = validate_virustotal_api_key(key, lang=i18n.lang)
        if not valid:
            self.call_js("onLog", f"❌ {err_msg}")
            return {"success": False, "has_key": False, "message": err_msg}

        ok = set_virustotal_api_key(key)
        if ok:
            msg = "API ключ VirusTotal успешно сохранен и проверен." if i18n.lang == "ru" else "VirusTotal API key verified and saved."
            self.call_js("onLog", f"🛡️ {msg}")
            return {"success": True, "has_key": True, "message": msg}
        return {"success": False, "has_key": False, "message": "Не удалось сохранить ключ в настройках."}

    def browse_and_scan_virustotal(self) -> dict[str, Any]:
        """Открывает диалог выбора файла и запускает сканирование в VirusTotal."""
        try:
            title = "Выберите файл для проверки VirusTotal" if i18n.lang == "ru" else "Select file to scan with VirusTotal"
            file_path = self._open_file_dialog_native(
                title=title,
                filter_str_ps="Все файлы (*.*)|*.*|Программы и архивы (*.exe;*.msi;*.dll;*.zip;*.7z)|*.exe;*.msi;*.dll;*.zip;*.7z",
                file_types_webview=("Все файлы (*.*)", "Программы и файлы (*.exe;*.msi;*.dll;*.zip;*.7z)"),
            )
            if not file_path:
                return {"success": False, "cancelled": True}
            from app.virustotal import scan_file_by_path
            res_scan = scan_file_by_path(file_path)
            if res_scan.get("success"):
                if res_scan.get("found"):
                    score = res_scan.get("score_text", "")
                    self.call_js("onLog", f"🛡️ VirusTotal проверка завершена для «{res_scan.get('file_name')}»: {score} угроз")
                else:
                    self.call_js("onLog", f"🛡️ VirusTotal: файл «{res_scan.get('file_name')}» ранее не исследовался.")
            elif res_scan.get("message"):
                self.call_js("onLog", f"⚠️ VirusTotal: {res_scan.get('message')}")
            return res_scan
        except Exception as e:
            logger.error(f"Error in browse_and_scan_virustotal: {e}")
            return {"success": False, "message": str(e)}

    def scan_virustotal_hash(self, sha256: str, filename: str = "", file_size: int = 0) -> dict[str, Any]:
        """Сканирует SHA-256 хэш файла в VirusTotal напрямую без передачи всего файла."""
        from app.virustotal import scan_file_by_hash
        res_scan = scan_file_by_hash(sha256, filename=filename, file_size=file_size)
        if res_scan.get("success"):
            if res_scan.get("found"):
                score = res_scan.get("score_text", "")
                self.call_js("onLog", f"🛡️ VirusTotal проверка завершена для «{res_scan.get('file_name')}»: {score} угроз")
            else:
                self.call_js("onLog", f"🛡️ VirusTotal: файл «{res_scan.get('file_name')}» ранее не исследовался.")
        elif res_scan.get("message"):
            self.call_js("onLog", f"⚠️ VirusTotal: {res_scan.get('message')}")
        return res_scan

    def upload_virustotal_base64(self, file_bytes_base64: str, filename: str) -> dict[str, Any]:
        """Принимает Base64-данные файла из браузера и загружает их в VirusTotal для анализа."""
        import base64
        from app.virustotal import upload_file_bytes
        try:
            raw_bytes = base64.b64decode(file_bytes_base64)
            self.call_js("onLog", f"📤 Отправка файла «{filename}» ({len(raw_bytes)} Б) на анализ в VirusTotal...")
            res_upload = upload_file_bytes(raw_bytes, filename=filename)
            if res_upload.get("success") and res_upload.get("found"):
                score = res_upload.get("score_text", "")
                self.call_js("onLog", f"✅ Анализ VirusTotal завершен: {score} угроз")
            elif res_upload.get("message"):
                self.call_js("onLog", f"⚠️ VirusTotal: {res_upload.get('message')}")
            return res_upload
        except Exception as e:
            logger.error(f"Error in upload_virustotal_base64: {e}")
            return {"success": False, "message": f"Ошибка отправки файла на анализ: {e}"}

    def scan_virustotal_path(self, file_path: str) -> dict[str, Any]:
        """Сканирует переданный путь к файлу в VirusTotal."""
        from app.virustotal import scan_file_by_path
        res_scan = scan_file_by_path(file_path)
        if res_scan.get("success"):
            if res_scan.get("found"):
                score = res_scan.get("score_text", "")
                self.call_js("onLog", f"🛡️ VirusTotal проверка завершена: {score} угроз")
            else:
                self.call_js("onLog", "🛡️ VirusTotal: файл ранее не исследовался.")
        elif res_scan.get("message"):
            self.call_js("onLog", f"⚠️ VirusTotal: {res_scan.get('message')}")
        return res_scan

    def upload_and_scan_virustotal(self, file_path: str) -> dict[str, Any]:
        """Загружает неизвестный файл на проверку в VirusTotal."""
        from app.virustotal import upload_and_scan_file
        self.call_js("onLog", "📤 Отправка файла на анализ в VirusTotal...")
        res_upload = upload_and_scan_file(file_path)
        if res_upload.get("success") and res_upload.get("found"):
            score = res_upload.get("score_text", "")
            self.call_js("onLog", f"✅ Анализ VirusTotal завершен: {score} угроз")
        elif res_upload.get("message"):
            self.call_js("onLog", f"⚠️ VirusTotal: {res_upload.get('message')}")
        return res_upload

    # ==========================================
    # Путь для распаковки портативных версий
    # ==========================================

    def get_extract_path(self) -> str:
        return str(self._extract_path)

    def browse_extract_path(self) -> str:
        """Диалог выбора папки для распаковки архивов."""
        if not self._window:
            return str(self._extract_path)
        try:
            res = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(self._extract_path),
            )
            if res and len(res) > 0:
                chosen = Path(res[0])
                if chosen.exists() and chosen.is_dir():
                    self._extract_path = chosen
                    self._installer.extract_path = self._extract_path
                    settings = load_settings()
                    settings["extract_mode"] = "custom"
                    settings["custom_extract_path"] = str(self._extract_path)
                    save_settings(settings)
                    self.call_js("onLog", f"📁 Путь распаковки: {self._extract_path}")
                    return str(self._extract_path)
        except Exception as e:
            logger.error(f"Error browsing extract path: {e}")
        return str(self._extract_path)

    def set_extract_path_to_desktop(self) -> str:
        """Устанавливает режим распаковки на Рабочий стол текущего пользователя."""
        desktop = get_desktop_path()
        self._extract_path = desktop
        self._installer.extract_path = self._extract_path
        settings = load_settings()
        settings["extract_mode"] = "desktop"
        settings.pop("custom_extract_path", None)
        save_settings(settings)
        self.call_js("onLog", f"📁 Путь распаковки установлен на Рабочий стол: {self._extract_path}")
        return str(self._extract_path)

    def set_extract_path_to_exe_dir(self) -> str:
        """Устанавливает режим распаковки рядом с исполняемым файлом программы."""
        exe_dir = get_exe_dir()
        self._extract_path = exe_dir
        self._installer.extract_path = self._extract_path
        settings = load_settings()
        settings["extract_mode"] = "exe_dir"
        settings.pop("custom_extract_path", None)
        save_settings(settings)
        self.call_js("onLog", f"📁 Путь распаковки установлен рядом с программой: {self._extract_path}")
        return str(self._extract_path)

    def open_path(self, path_str: str):
        """Открывает папку в Проводнике."""
        try:
            os.startfile(path_str)
        except Exception as e:
            logger.error(f"Error opening path {path_str}: {e}")

    # ==========================================
    # Скачивание
    # ==========================================

    def download_selected(self, app_ids: list[str]):
        """Запускает параллельное скачивание выбранных приложений."""
        if self._is_downloading:
            return

        apps_to_download = [self._catalog_map[aid] for aid in app_ids if aid in self._catalog_map]
        if not apps_to_download:
            return

        self._is_downloading = True
        self._downloader.reset()

        def worker():
            total = len(apps_to_download)
            completed = 0
            self.call_js("onLog", f"📥 {i18n.t('log_start_download', count=total)}")

            def progress_cb(app_id: str, percent: float, status_text: str):
                self.call_js("onAppProgress", app_id, percent, status_text)

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}
                for app in apps_to_download:
                    self.call_js("onAppStatus", app.id, "downloading", i18n.t("status_downloading"))
                    f = executor.submit(self._downloader.download, app, progress_cb)
                    futures[f] = app

                for f in futures:
                    app = futures[f]
                    try:
                        result = f.result()
                        completed += 1
                        if result.success:
                            self._downloaded_results[app.id] = result
                            self.call_js("onAppDownloaded", app.id, str(result.installer_path))
                            self.call_js("onLog", i18n.t("log_downloaded", name=app.name))
                        else:
                            self.call_js("onAppStatus", app.id, "error", result.error)
                            self.call_js("onLog", i18n.t("log_download_error", name=app.name, error=result.error))

                        self.call_js("onOverallProgress", completed, total, i18n.t("downloading_progress", done=completed, total=total))
                    except Exception as e:
                        completed += 1
                        self.call_js("onAppStatus", app.id, "error", str(e))
                        self.call_js("onLog", i18n.t("log_download_error", name=app.name, error=str(e)))

            self._is_downloading = False
            self.call_js("onLog", i18n.t("log_download_done"))
            self.call_js("onDownloadPhaseDone", len(self._downloaded_results))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def download_single(self, app_id: str):
        """Одиночное скачивание приложения."""
        if app_id not in self._catalog_map:
            return
        app = self._catalog_map[app_id]

        def worker():
            self._active_downloads += 1
            self.call_js("onAppStatus", app.id, "downloading", i18n.t("status_downloading"))
            self.call_js("onLog", f"📥 {app.name}: {i18n.t('status_downloading')}")

            def progress_cb(aid: str, percent: float, status_text: str):
                self.call_js("onAppProgress", aid, percent, status_text)

            try:
                up_info = getattr(self, "_available_updates", {}).get(app_id, {})
                target_ver = up_info.get("available_version", "")
                target_wid = up_info.get("target_winget_id", "")
                result = self._downloader.download(app, progress_cb, target_winget_id=target_wid, target_version=target_ver)
                if result.success:
                    self._downloaded_results[app.id] = result
                    self.call_js("onAppDownloaded", app.id, str(result.installer_path))
                    self.call_js("onLog", i18n.t("log_downloaded", name=app.name))
                elif self._downloader.is_app_cancelled(app.id):
                    self.call_js("onAppProgress", app.id, 0, "")
                    self.call_js("onAppStatus", app.id, "idle", "")
                else:
                    self.call_js("onAppStatus", app.id, "error", result.error)
                    self.call_js("onLog", i18n.t("log_download_error", name=app.name, error=result.error))
            except Exception as e:
                self.call_js("onAppStatus", app.id, "error", str(e))
                self.call_js("onLog", i18n.t("log_download_error", name=app.name, error=str(e)))
            finally:
                self._active_downloads -= 1

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def cancel_downloads(self):
        """Отмена всех текущих скачиваний и установок."""
        self._downloader.cancel()
        self._installer.cancel()
        self._is_downloading = False
        self._is_installing_all = False
        self._is_upgrading_bulk = False
        self.call_js("onLog", "🛑 Все операции отменены.")

    def cancel_single_download(self, app_id: str):
        """Отмена одиночного скачивания или установки/обновления приложения."""
        self._downloader.cancel_app(app_id)
        self._installer.cancel_app(app_id)
        self.call_js("onAppProgress", app_id, 0, "")
        self.call_js("onAppStatus", app_id, "idle", "")
        app = self._catalog_map.get(app_id)
        name = app.name if app else app_id
        self.call_js("onLog", f"🛑 Операция для {name} отменена.")

    def delete_downloaded_app(self, app_id: str):
        """Удаляет скачанный файл установщика/архива для приложения и сбрасывает статус карточки."""
        if app_id in self._downloaded_results:
            dl_res = self._downloaded_results.pop(app_id)
            if dl_res.installer_path and Path(dl_res.installer_path).exists():
                try:
                    p = Path(dl_res.installer_path)
                    p.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Error removing installer file for {app_id}: {e}")

        # Также удаляем папку приложения в downloads/<app_id>
        app_dir = self._downloader.download_dir / app_id
        if app_dir.exists():
            try:
                shutil.rmtree(app_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing app download directory {app_dir}: {e}")

        self.call_js("onAppProgress", app_id, 0, "")
        self.call_js("onAppStatus", app_id, "idle", "")
        app = self._catalog_map.get(app_id)
        name = app.name if app else app_id
        self.call_js("onLog", f"🗑️ Скачанный установщик {name} удален.")

    def clean_downloaded_installers(self) -> dict[str, Any]:
        """Удаляет все .exe, .msi и дистрибутивы, скачанные программой в кэш."""
        try:
            from app.tweaks import _clean_winsetup_installers
            ok, msg = _clean_winsetup_installers()
            self._downloaded_results.clear()
            self.call_js("onLog", f"🗑️ {msg}")
            return {"success": ok, "message": msg}
        except Exception as e:
            logger.error(f"Error cleaning downloaded installers: {e}")
            return {"success": False, "message": str(e)}

    def is_busy(self) -> bool:
        """Проверяет, выполняется ли в данный момент скачивание, установка или обновление."""
        if self._is_downloading or self._is_installing_all or self._is_upgrading_bulk:
            return True
        if self._active_downloads > 0 or self._active_installs > 0 or self._active_upgrades > 0:
            return True
        if getattr(self._downloader, "_active_processes", None) and len(self._downloader._active_processes) > 0:
            return True
        if getattr(self._installer, "_active_processes", None) and len(self._installer._active_processes) > 0:
            return True
        if getattr(self._installer, "_active_handles", None) and len(self._installer._active_handles) > 0:
            return True
        return False

    # ==========================================
    # Установка
    # ==========================================

    def install_single(self, app_id: str, silent: bool = False, as_admin: bool = False):
        """Одиночная установка скачанного приложения."""
        if app_id not in self._catalog_map or app_id not in self._downloaded_results:
            return
        app = self._catalog_map[app_id]
        dl_res = self._downloaded_results[app_id]

        def worker():
            self._active_installs += 1
            try:
                self.call_js("onAppStatus", app.id, "installing", i18n.t("status_installing"))
                self.call_js("onLog", i18n.t("log_start_install", name=app.name))

                res = self._installer.run(app, Path(dl_res.installer_path), silent=silent, as_admin=as_admin)

                if res.success:
                    if app.installer_type == "zip":
                        self.call_js("onAppStatus", app.id, "extracted", res.error)
                        self.call_js("onLog", i18n.t("log_extracted", name=app.name, path=res.error))
                    elif app.installer_type == "portable":
                        self.call_js("onAppStatus", app.id, "done", "")
                        self.call_js("onAppInstalled", app.id)
                        self.call_js("onLog", f"🚀 {app.name}: ярлык создан на Рабочем столе, приложение готово к работе.")
                    else:
                        self.call_js("onAppStatus", app.id, "done", "")
                        self.call_js("onLog", i18n.t("log_installed", name=app.name))
                elif getattr(res, "cancelled", False):
                    self.call_js("onAppStatus", app.id, "downloaded", "")
                    self.call_js("onLog", f"⚠️ Установка {app.name} отменена пользователем.")
                else:
                    self.call_js("onAppStatus", app.id, "error", res.error)
                    self.call_js("onLog", i18n.t("log_install_error", name=app.name, error=res.error))
            finally:
                self._active_installs -= 1

        threading.Thread(target=worker, daemon=True).start()

    def install_all(self, modes_map: dict[str, str]):
        """Алиас для вызова массовой установки из JavaScript."""
        self.install_all_downloaded(modes_map)

    def install_all_downloaded(self, modes_map: dict[str, str]):
        """Массовая последовательная установка всех скачанных приложений."""
        if self._is_installing_all:
            return

        downloaded_apps = []
        for aid, dres in self._downloaded_results.items():
            if aid in self._catalog_map and dres.success:
                downloaded_apps.append((self._catalog_map[aid], dres.installer_path))

        if not downloaded_apps:
            return

        self._is_installing_all = True

        def worker():
            total = len(downloaded_apps)
            self.call_js("onLog", f"\n⚙️ {i18n.t('installing_progress', done=0, total=total)}")

            for idx, (app, path) in enumerate(downloaded_apps):
                if not Path(path).exists():
                    continue

                mode = modes_map.get(app.id, "interactive")
                silent = (mode == "silent")

                self.call_js("onAppStatus", app.id, "installing", i18n.t("status_installing"))
                self.call_js("onLog", i18n.t("log_start_install", name=app.name))
                self.call_js("onInstallAllProgress", idx, total, i18n.t("installing_progress", done=idx, total=total))

                res = self._installer.run(app, Path(path), silent=silent, as_admin=False)

                if res.success:
                    if app.installer_type == "zip":
                        self.call_js("onAppStatus", app.id, "extracted", res.error)
                        self.call_js("onLog", i18n.t("log_extracted", name=app.name, path=res.error))
                    elif app.installer_type == "portable":
                        self.call_js("onAppStatus", app.id, "done", "")
                        self.call_js("onAppInstalled", app.id)
                        self.call_js("onLog", f"🚀 {app.name}: ярлык создан на Рабочем столе, приложение готово к работе.")
                    else:
                        self.call_js("onAppStatus", app.id, "done", "")
                        self.call_js("onLog", i18n.t("log_installed", name=app.name))
                elif getattr(res, "cancelled", False):
                    self.call_js("onAppStatus", app.id, "downloaded", "")
                    self.call_js("onLog", f"⚠️ Установка {app.name} отменена пользователем.")
                else:
                    self.call_js("onAppStatus", app.id, "error", res.error)
                    self.call_js("onLog", i18n.t("log_install_error", name=app.name, error=res.error))

                self.call_js("onInstallAllProgress", idx + 1, total, i18n.t("installing_progress", done=idx + 1, total=total))

            self._is_installing_all = False
            self.call_js("onLog", i18n.t("log_all_done"))
            self.call_js("onInstallAllDone")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def launch_app(self, app_id: str):
        """Запускает установленное или портативное приложение."""
        app = self._catalog_map.get(app_id)
        if not app:
            return

        # 1. Проверяем в папке распаковки пользователя
        portable_exe = self._extract_path / app.name / f"{app.name}.exe"
        if not portable_exe.exists():
            app_folder = self._extract_path / app.name
            if app_folder.is_dir():
                for f in app_folder.glob("*.exe"):
                    if not f.name.endswith(".old"):
                        portable_exe = f
                        break
        if not portable_exe.exists():
            portable_exe = self._extract_path / f"{app.name}.exe"

        # 2. Если файл есть в скачанных
        if not portable_exe.exists() and app_id in self._downloaded_results:
            dres = self._downloaded_results[app_id]
            if dres.installer_path and Path(dres.installer_path).exists():
                portable_exe = Path(dres.installer_path)

        # 3. Ищем путь из обнаруженных установленных приложений
        if not portable_exe.exists() and self._installed_apps and app_id in self._installed_apps:
            det_path = self._installed_apps[app_id].get("path")
            if det_path and Path(det_path).exists():
                portable_exe = Path(det_path)

        # 4. Ищем ярлык на рабочем столе
        if not portable_exe.exists():
            desktop = get_desktop_path()
            for lnk in (desktop / f"{app.name}.lnk", desktop / f"{app.id}.lnk", desktop / "GPU-Z.lnk", desktop / "TechPowerUp GPU-Z.lnk"):
                if lnk.exists():
                    try:
                        os.startfile(str(lnk))
                        self.call_js("onLog", f"🚀 {app.name} запущен через ярлык.")
                        return
                    except Exception as e:
                        logger.warning(f"Failed to start shortcut {lnk}: {e}")

        if portable_exe.exists():
            try:
                os.startfile(str(portable_exe))
                self.call_js("onLog", f"🚀 {app.name} запущен.")
            except Exception as e:
                try:
                    creationflags = subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0
                    subprocess.Popen(
                        [str(portable_exe)],
                        cwd=str(portable_exe.parent),
                        creationflags=creationflags,
                        close_fds=True,
                    )
                    self.call_js("onLog", f"🚀 {app.name} запущен.")
                except Exception as e2:
                    self.call_js("onLog", f"❌ Ошибка запуска {app.name}: {e2}")
        else:
            try:
                os.startfile(app.name)
            except Exception as e:
                logger.warning(f"Could not start {app.name}: {e}")

    def open_app_folder(self, app_id: str):
        """Открывает папку с установленным/распакованным приложением."""
        app = self._catalog_map.get(app_id)
        if not app:
            return
        target_dir = self._extract_path / app.name
        if not target_dir.exists():
            target_dir = self._extract_path
        try:
            os.startfile(str(target_dir))
        except Exception as e:
            logger.error(f"Error opening folder {target_dir}: {e}")

    # ==========================================
    # Твики и фичи
    # ==========================================

    def get_tweaks(self) -> list[dict]:
        return get_all_tweaks(i18n.lang)

    def apply_tweak(self, tweak_id: str) -> dict[str, Any]:
        res = apply_tweak_by_id(tweak_id, lang=i18n.lang)
        if tweak_id == "clean_winsetup_installers":
            self._downloaded_results.clear()
            self.call_js("onLog", f"🗑️ {res.get('message', '')}")
        elif tweak_id in ("repair_system_files", "restore_health_dism") and res.get("success"):
            self._start_tweak_status_monitor(tweak_id)
        return res

    def get_tweak_running_status(self, tweak_id: str) -> dict[str, Any]:
        """Возвращает текущий статус выполнения длительного твика для надежного фронтенд-поллинга."""
        return self._running_tweaks.get(tweak_id, {"running": False, "completed": False})

    def _start_tweak_status_monitor(self, tweak_id: str) -> None:
        """Запускает фоновый поток мониторинга выполнения sfc /scannow или DISM RestoreHealth."""
        from app.tweaks import get_sfc_status_file, get_dism_status_file, get_tweak_process_handle, set_tweak_process_handle, TWEAKS
        status_file = get_sfc_status_file() if tweak_id == "repair_system_files" else get_dism_status_file()
        tweak_name = "sfc" if tweak_id == "repair_system_files" else "dism"

        self._running_tweaks[tweak_id] = {
            "running": True,
            "completed": False,
            "id": tweak_id,
            "message": "Консоль запущена..."
        }

        def monitor():
            time.sleep(2)
            handle = get_tweak_process_handle(tweak_name)

            for _ in range(1800):  # До 30 минут
                time.sleep(1)

                # 1. Проверяем файл статуса (создается bat-файлом сразу по окончании работы команды)
                if status_file.exists():
                    try:
                        content = status_file.read_text(encoding="utf-8").strip()
                        if content.startswith("SUCCESS") or content.startswith("REPAIRED") or content.startswith("ERROR") or content.startswith("COMPLETED"):
                            if tweak_id == "repair_system_files":
                                if "SUCCESS" in content:
                                    msg_ru = "✅ Сканирование sfc /scannow завершено: повреждений целостности не обнаружено."
                                    msg_en = "✅ sfc /scannow scan complete: no integrity violations found."
                                else:
                                    msg_ru = "✅ Сканирование sfc /scannow завершено: поврежденные системные файлы восстановлены."
                                    msg_en = "✅ sfc /scannow scan complete: corrupted system files were repaired."
                            else:
                                if "SUCCESS" in content:
                                    msg_ru = "✅ Восстановление хранилища компонентов DISM успешно завершено."
                                    msg_en = "✅ DISM component store restore completed successfully."
                                else:
                                    msg_ru = "⚠️ Восстановление DISM завершено. Проверьте журнал CBS/DISM."
                                    msg_en = "⚠️ DISM restore completed. Check CBS/DISM logs."

                            res_data = {
                                "id": tweak_id,
                                "running": False,
                                "completed": True,
                                "success": True,
                                "message": msg_en if i18n.lang == "en" else msg_ru,
                                "message_ru": msg_ru,
                                "message_en": msg_en,
                            }
                            self._running_tweaks[tweak_id] = res_data

                            for t in TWEAKS:
                                if t.id == tweak_id:
                                    t.last_result = res_data["message"]
                                    t.last_result_ru = msg_ru
                                    t.last_result_en = msg_en

                            self.call_js("onTweakCompleted", res_data)
                            try:
                                status_file.unlink(missing_ok=True)
                            except Exception:
                                pass
                            if handle:
                                try:
                                    ctypes.windll.kernel32.CloseHandle(handle)
                                except Exception:
                                    pass
                                set_tweak_process_handle(tweak_name, None)
                            return
                    except Exception as e:
                        logger.debug(f"Status file read error: {e}")

                # 2. Проверяем статус процесса через Windows Handle (если окно консоли закрыли крестиком)
                if handle:
                    try:
                        wait_code = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                        if wait_code == 0:  # Процесс консоли завершился / окно закрыто!
                            time.sleep(1)
                            if status_file.exists():
                                continue  # Прочтется на следующем шаге
                            msg_ru = "⚠️ Консоль была закрыта пользователем до завершения."
                            msg_en = "⚠️ Console was closed by user before completion."
                            res_data = {
                                "id": tweak_id,
                                "running": False,
                                "completed": True,
                                "success": False,
                                "message": msg_en if i18n.lang == "en" else msg_ru,
                                "message_ru": msg_ru,
                                "message_en": msg_en,
                            }
                            self._running_tweaks[tweak_id] = res_data
                            for t in TWEAKS:
                                if t.id == tweak_id:
                                    t.last_result = res_data["message"]
                                    t.last_result_ru = msg_ru
                                    t.last_result_en = msg_en
                            self.call_js("onTweakCompleted", res_data)
                            try:
                                ctypes.windll.kernel32.CloseHandle(handle)
                            except Exception:
                                pass
                            set_tweak_process_handle(tweak_name, None)
                            return
                    except Exception as e:
                        logger.debug(f"Process handle wait error: {e}")

        threading.Thread(target=monitor, daemon=True).start()

    def revert_tweak(self, tweak_id: str) -> dict[str, Any]:
        return revert_tweak_by_id(tweak_id, lang=i18n.lang)

    # ==========================================
    # Metro / UWP приложения Windows
    # ==========================================

    def get_metro_apps(self) -> list[dict[str, Any]]:
        """Возвращает список всех Metro приложений со статусом установки."""
        return get_all_metro_apps(i18n.lang)

    def remove_metro_app(self, app_id: str) -> dict[str, Any]:
        """Удаляет одно Metro приложение."""
        return remove_metro_app_by_id(app_id)

    def restore_metro_app(self, app_id: str) -> dict[str, Any]:
        """Восстанавливает одно Metro приложение."""
        return restore_metro_app_by_id(app_id)

    def remove_selected_metro(self, app_ids: list[str]) -> list[dict[str, Any]]:
        """Пакетное удаление выбранных Metro приложений."""
        return remove_batch_metro(app_ids)

    def restore_selected_metro(self, app_ids: list[str]) -> list[dict[str, Any]]:
        """Пакетное восстановление выбранных Metro приложений."""
        return restore_batch_metro(app_ids)

    # ==========================================
    # Потоковое обновление и проверка версий
    # ==========================================

    def rescan_installed_apps(self):
        """Повторно сканирует реестр Windows и пути программ для обновления статуса установленных."""
        def worker():
            self.call_js("onRescanStart")
            self.call_js("onLog", f"🔍 {i18n.t('rescanning_installed')}")
            try:
                self._installed_apps = detect_installed_apps()
                count = len(self._installed_apps)
                self.call_js("onInstalledAppsDetected", self._installed_apps)
                self.call_js("onRescanDone", count)
                self.call_js("onLog", f"✅ {i18n.t('rescan_completed', count=count)}")
            except Exception as e:
                logger.error(f"Error rescanning installed apps: {e}")
                self.call_js("onRescanDone", -1)
                self.call_js("onLog", f"❌ Ошибка проверки установленных программ: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def check_updates(self):
        """Запускает фоновую проверку обновлений и шлет результат в JS."""
        def worker():
            self.call_js("onUpdateCheckStart")
            installed_map = detect_installed_apps()
            self._installed_apps = installed_map
            updates = check_updates_sync(installed_map)
            self._available_updates = updates
            self.call_js("onInstalledAppsDetected", installed_map)
            self.call_js("onUpdatesChecked", updates)

        threading.Thread(target=worker, daemon=True).start()

    def _do_upgrade_sync(self, app_id: str, silent: bool = True) -> bool:
        """Синхронное обновление одного приложения с потоковым выводом в реальном времени."""
        app = self._catalog_map.get(app_id)
        if not app:
            return False

        if not app.winget_id and not app.github_repo and not app.direct_url:
            self.call_js("onAppProgress", app_id, 0, "")
            self.call_js("onAppStatus", app_id, "idle", "")
            self.call_js("onLog", f"ℹ️ Для {app.name} обновление выполняется вручную.")
            return False

        self._active_upgrades += 1
        try:
            self._downloader.reset_app(app_id)
            self._installer.reset_app(app_id)

            self.call_js("onAppStatus", app_id, "installing", i18n.t("status_installing"))
            self.call_js("onAppProgress", app_id, 5, "Инициализация...")
            self.call_js("onLog", f"⬆️ Начало обновления {app.name}...")

            def progress_cb(aid: str, percent: float, text: str):
                self.call_js("onAppProgress", aid, percent, f"{text}")

            target_version = ""
            target_winget_id = ""
            if hasattr(self, "_available_updates") and self._available_updates:
                up_info = self._available_updates.get(app_id, {})
                target_version = up_info.get("available_version", "")
                target_winget_id = up_info.get("target_winget_id", "")

            d_res = self._downloader.download(app, progress_cb, target_winget_id=target_winget_id, target_version=target_version)
            if self._downloader.is_app_cancelled(app_id) or self._installer.is_app_cancelled(app_id):
                self.call_js("onAppProgress", app_id, 0, "")
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onLog", f"⚠️ Обновление {app.name} отменено пользователем.")
                return False

            if not d_res.success:
                self.call_js("onAppProgress", app_id, 0, "")
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onLog", f"❌ Ошибка скачивания обновления {app.name}: {d_res.error}")
                return False

            self._downloaded_results[app_id] = d_res

            self.call_js("onAppStatus", app_id, "installing", "⚙️ Установка обновления...")
            self.call_js("onAppProgress", app_id, 90, "⚙️ Запуск установщика...")
            self.call_js("onLog", f"⚙️ Установка новой версии {app.name}...")

            as_admin = False
            is_silent = silent
            if app_id in ("anydesk", "gpuz", "python", "obs", "obs-studio", "amnezia-vpn") or (app.silent_args and any("program files" in str(a).lower() for a in app.silent_args)):
                as_admin = True
            if app_id == "amnezia-vpn" or not app.silent_args:
                is_silent = False
                as_admin = True
                self.call_js("onLog", f"ℹ️ Открыт установщик {app.name}. Пожалуйста, подтвердите установку в открывшемся окне...")

            inst_res = self._installer.run(app, Path(d_res.installer_path), silent=is_silent, as_admin=as_admin, version=target_version)
            if inst_res.success:
                if hasattr(self, "_installed_apps") and self._installed_apps is not None:
                    if app_id not in self._installed_apps:
                        self._installed_apps[app_id] = {"installed": True, "name": app.name}
                    if target_version:
                        self._installed_apps[app_id]["version"] = target_version
                if hasattr(self, "_available_updates") and self._available_updates:
                    self._available_updates.pop(app_id, None)
                self.call_js("onAppProgress", app_id, 100, "Готово!")
                self.call_js("onAppStatus", app_id, "done", "")
                self.call_js("onLog", f"✅ {app.name} успешно обновлён!")
                self.call_js("onUpdateCompleted", app_id, target_version)
                return True
            elif inst_res.cancelled or self._installer.is_app_cancelled(app_id):
                self.call_js("onAppProgress", app_id, 0, "")
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onLog", f"⚠️ Обновление {app.name} отменено пользователем.")
                return False
            else:
                self.call_js("onAppProgress", app_id, 0, "")
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onLog", f"❌ Ошибка установки обновления {app.name}: {inst_res.error}")
                return False
        except Exception as e:
            logger.error(f"Error upgrading {app.name}: {e}", exc_info=True)
            self.call_js("onAppProgress", app_id, 0, "")
            self.call_js("onAppStatus", app_id, "idle", "")
            self.call_js("onLog", f"❌ Ошибка обновления {app.name}: {e}")
            return False
        finally:
            self._active_upgrades -= 1

    def upgrade_app(self, app_id: str):
        """Обновляет приложение в отдельном фоновом потоке."""
        def worker():
            app = self._catalog_map.get(app_id)
            app_name = app.name if app else app_id
            self.call_js("onOverallProgress", 0, 1, f"Обновление {app_name}...")
            try:
                success = self._do_upgrade_sync(app_id, silent=True)
                if success:
                    self.call_js("onUpdateCompleted", app_id)
                    self.call_js("onOverallProgress", 1, 1, f"Готово: {app_name} успешно обновлён (100%)")
                else:
                    self.call_js("onAppStatus", app_id, "idle", "")
                    self.call_js("onAppProgress", app_id, 0, "")
                    self.call_js("onOverallProgress", 0, 1, f"Ошибка обновления {app_name}")
            except Exception as e:
                logger.error(f"Fatal error in upgrade_app worker for {app_name}: {e}", exc_info=True)
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onAppProgress", app_id, 0, "")
                self.call_js("onLog", f"❌ Ошибка обновления {app_name}: {e}")
                self.call_js("onOverallProgress", 0, 1, f"Ошибка обновления {app_name}")
        threading.Thread(target=worker, daemon=True).start()

    def upgrade_all(self, app_ids: list[str], is_bulk: bool = True):
        """Последовательно обновляет приложения из списка с фильтрацией исключений."""
        if self._is_upgrading_bulk:
            return

        def worker():
            self._is_upgrading_bulk = True
            try:
                target_ids = list(app_ids)

                # Если массовое обновление («Обновить все») — фильтруем исключенные из настроек
                if is_bulk:
                    ignored_set = set(get_ignored_update_apps())
                    filtered = [aid for aid in target_ids if aid not in ignored_set]
                    skipped = [aid for aid in target_ids if aid in ignored_set]
                    if skipped:
                        skipped_names = [self._catalog_map[aid].name for aid in skipped if aid in self._catalog_map]
                        self.call_js("onLog", f"🛡️ Пропущены из автообновления: {', '.join(skipped_names)}")
                        for s_id in skipped:
                            self.call_js("onAppStatus", s_id, "idle", "")
                            self.call_js("onAppProgress", s_id, 0, "")
                    target_ids = filtered

                total = len(target_ids)
                if total == 0:
                    self.call_js("onLog", "ℹ️ Нет доступных приложений для обновления.")
                    self.call_js("onOverallProgress", 1, 1, "Готово: все программы обновлены (100%)")
                    self.call_js("onUpdateAllDone")
                    return

                self.call_js("onLog", f"⬆️ Запуск последовательного обновления {total} приложений...")
                success_count = 0

                for idx, aid in enumerate(target_ids):
                    app = self._catalog_map.get(aid)
                    app_name = app.name if app else aid
                    self.call_js("onOverallProgress", idx, total, f"Обновление {app_name} ({idx + 1}/{total})")
                    try:
                        if self._do_upgrade_sync(aid, silent=True):
                            success_count += 1
                        else:
                            self.call_js("onAppProgress", aid, 0, "")
                            self.call_js("onAppStatus", aid, "idle", "")
                    except Exception as loop_err:
                        logger.error(f"Error updating {app_name} in loop: {loop_err}", exc_info=True)
                        self.call_js("onAppProgress", aid, 0, "")
                        self.call_js("onAppStatus", aid, "idle", "")
                        self.call_js("onLog", f"❌ Ошибка обновления {app_name}: {loop_err}")
                    self.call_js("onOverallProgress", idx + 1, total, f"Завершено {idx + 1}/{total}")

                self.call_js("onOverallProgress", total, total, f"Готово: {success_count}/{total} обновлено (100%)")
                self.call_js("onLog", f"✨ Обновление завершено: {success_count}/{total} успешно обновлено.")
                self.call_js("onUpdateAllDone")
            except Exception as e:
                logger.error(f"Fatal error in upgrade_all worker: {e}", exc_info=True)
                self.call_js("onLog", f"❌ Критическая ошибка массового обновления: {e}")
                self.call_js("onOverallProgress", 0, 1, "Ошибка массового обновления")
                self.call_js("onUpdateAllDone")
            finally:
                self._is_upgrading_bulk = False

        threading.Thread(target=worker, daemon=True).start()

    def upgrade_selected(self, app_ids: list[str]):
        """Обновляет выбранные галочками приложения (без принудительной фильтрации)."""
        self.upgrade_all(app_ids, is_bulk=False)

    def open_url(self, url: str):
        """Открывает указанный URL в системном браузере по умолчанию."""
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Error opening url {url}: {e}")

    def install_winget_auto(self):
        """Запускает автоматическое скачивание и установку Winget."""
        def worker():
            self.call_js("onWingetInstallProgress", 5, i18n.t("winget_installing"))
            self.call_js("onLog", "🚀 Запуск автоматической установки Windows Package Manager (Winget)...")

            def progress_cb(pct, text):
                self.call_js("onWingetInstallProgress", pct, text)
                self.call_js("onLog", f"📦 Winget: {text}")

            success, msg_or_ver = install_winget(progress_cb)
            if success:
                # Обновляем кэш winget в self._app_data
                if self._app_data and "system_info" in self._app_data:
                    self._app_data["system_info"]["winget_available"] = True
                    self._app_data["system_info"]["winget_version"] = msg_or_ver
                self.call_js("onWingetInstalled", msg_or_ver)
                self.call_js("onLog", f"✅ {i18n.t('winget_install_success')} ({msg_or_ver})")
            else:
                self.call_js("onWingetInstallProgress", 0, f"Ошибка: {msg_or_ver}")
                self.call_js("onLog", f"❌ Ошибка установки Winget: {msg_or_ver}")

        threading.Thread(target=worker, daemon=True).start()

    def open_winget_store(self):
        """Открывает страницу App Installer в Microsoft Store."""
        self.call_js("onLog", "🛍️ Открытие страницы Microsoft Store (App Installer)...")
        open_winget_store()

    # ==========================================
    # Управление автозагрузкой Windows и автозапуском приложения
    # ==========================================

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
        self.call_js("onStartupItemsUpdated", items)
        return items

    def toggle_startup_item(self, item_id: str, enable: bool) -> dict[str, Any]:
        """Включает или отключает элемент автозагрузки Windows."""
        try:
            success, msg = StartupManager.toggle_item(item_id, enable)
            if success:
                self.call_js("onLog", f"⚙️ Автозагрузка: {msg}")
            else:
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
                self.call_js("onLog", f"🗑️ Автозагрузка: {msg}")
            else:
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
                self.call_js("onLog", f"📂 {msg}")
            else:
                self.call_js("onLog", f"⚠️ Не удалось открыть папку: {msg}")
            return {"success": success, "message": msg}
        except Exception as e:
            logger.error(f"Error opening folder for startup item {item_id}: {e}")
            return {"success": False, "message": str(e)}

    def browse_executable_file(self) -> str:
        """Открывает диалог выбора исполняемого файла (.exe, .bat, .cmd, .lnk)."""
        if self._window:
            try:
                res = self._window.create_file_dialog(
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
                self.call_js("onLog", f"🚀 Автозагрузка: {msg}")
                self.rescan_startup_items()
            else:
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
            self.call_js("onLog", f"🪟 Сворачивание в трей при закрытии {status_text}.")
            return {"success": True, "enabled": enabled}
        except Exception as e:
            logger.error(f"Error setting minimize_to_tray_on_close: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================
    # Автопоиск и установка обновлений ZiablWinSetup (Self-Updater)
    # ==========================================

    def check_self_update(self, manual: bool = False):
        """
        Проверяет наличие новой версии ZiablWinSetup на GitHub Releases.
        manual=True при нажатии пользователем кнопки 'Проверить обновление'.
        """
        def worker():
            if manual:
                self.call_js("onLog", "🔍 Проверка наличия новой версии ZiablWinSetup...")

            settings = load_settings()
            # Если автоматическая проверка и пользователь отключил её в настройках
            if not manual and not settings.get("auto_check_app_updates", True):
                logger.debug("Автопоиск обновлений приложения отключен в настройках.")
                return

            res = check_for_app_update(current_version=__version__)
            if res.get("update_available"):
                skipped = settings.get("skipped_app_version", "")
                if not manual and skipped == res.get("latest_version"):
                    logger.debug(f"Версия v{skipped} была ранее пропущена пользователем.")
                    return

                self.call_js("onLog", f"🎉 Найдено обновление ZiablWinSetup: v{res['latest_version']}!")
                self.call_js("onAppUpdateFound", res)

                # Уведомление в системном трее, если окно скрыто
                if self._tray_manager and hasattr(self._tray_manager, "notify"):
                    self._tray_manager.notify(
                        f"Вышла новая версия v{res['latest_version']}! Кликните, чтобы обновиться.",
                        "Обновление ZiablWinSetup"
                    )
            else:
                if manual:
                    self.call_js("onAppUpdateNotFound", res)
                    msg = i18n.t("self_update_no_updates", version=__version__)
                    self.call_js("onLog", f"✨ {msg}")

        threading.Thread(target=worker, daemon=True).start()

    def get_current_changelog(self) -> dict[str, Any]:
        """Возвращает метаданные релиза и список изменений Git для текущей или новой версии."""
        try:
            return check_for_app_update(current_version=__version__)
        except Exception as e:
            logger.error(f"Ошибка получения списка изменений: {e}")
            return {"success": False, "error": str(e), "current_version": __version__}

    def apply_self_update(self, download_url: str):
        """Скачивает новую версию ZiablWinSetup и производит бесшовный перезапуск."""
        def worker():
            self.call_js("onLog", "🚀 Запуск скачивания и установки обновления ZiablWinSetup...")

            def progress_cb(pct: int, text: str):
                self.call_js("onSelfUpdateProgress", pct, text)
                self.call_js("onLog", f"📦 Обновление ZiablWinSetup: {text}")

            def exit_cb():
                try:
                    time.sleep(0.5)
                    self.quit_app()
                except Exception as e:
                    logger.debug(f"Error in exit_cb: {e}")
                def force_exit():
                    time.sleep(1.0)
                    os._exit(0)
                threading.Thread(target=force_exit, daemon=True).start()

            success, msg = download_and_apply_update(
                download_url=download_url,
                progress_callback=progress_cb,
                exit_callback=exit_cb,
            )
            if not success:
                self.call_js("onSelfUpdateError", msg)
                self.call_js("onLog", f"❌ Ошибка обновления ZiablWinSetup: {msg}")

        threading.Thread(target=worker, daemon=True).start()

    def skip_app_version(self, version_str: str) -> dict[str, Any]:
        """Сохраняет версию приложения, которую пользователь решил пропустить."""
        try:
            settings = load_settings()
            settings["skipped_app_version"] = version_str
            save_settings(settings)
            self.call_js("onLog", f"Версия v{version_str} добавлена в пропущенные.")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_auto_check_app_updates(self, enabled: bool) -> dict[str, Any]:
        """Включает/выключает автопроверку обновлений приложения при старте."""
        try:
            settings = load_settings()
            settings["auto_check_app_updates"] = enabled
            save_settings(settings)
            status = "включен" if enabled else "отключен"
            self.call_js("onLog", f"⚙️ Автопоиск обновлений программы {status}.")
            return {"success": True, "enabled": enabled}
        except Exception as e:
            return {"success": False, "error": str(e)}


