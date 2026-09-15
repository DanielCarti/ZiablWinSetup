"""
ZiablWinSetup — Web API Bridge.
Связывает Python-бэкенд (загрузка, установка, UAC, твики, обновления) с аппаратным WebView2 GUI.
"""

import json
import logging
import os
import re
import subprocess
import threading
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
from app.detector import detect_installed_apps, uninstall_app
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
    toggle_app_ignored_update,
)
from app.tweaks import apply_tweak_by_id, get_all_tweaks, revert_tweak_by_id
from app.updater import check_updates_sync
from app.utils import check_winget, get_winget_version, is_admin

logger = logging.getLogger("WinSetup")


class AppBridge:
    """API-объект, методы которого доступны напрямую из JavaScript через window.pywebview.api."""

    def __init__(self):
        self._window: webview.Window | None = None
        self._downloader = Downloader()
        settings = load_settings()
        saved_path = settings.get("extract_path")
        if saved_path and os.path.exists(saved_path):
            self._extract_path = Path(saved_path)
        else:
            self._extract_path = get_desktop_path()
        self._installer = Installer(extract_path=self._extract_path)
        self._catalog_map: dict[str, AppEntry] = {a.id: a for a in get_catalog()}
        self._downloaded_results: dict[str, DownloadResult] = {}
        self._is_downloading = False
        self._active_downloads = 0
        self._is_installing_all = False
        self._active_installs = 0
        self._is_upgrading_bulk = False
        self._active_upgrades = 0

    def set_window(self, window: webview.Window):
        self._window = window

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
        ignored_update_ids = settings.get("ignored_update_apps", ["photoshop", "premiere"])

        saved_path = settings.get("extract_path")
        if saved_path and os.path.exists(saved_path):
            self._extract_path = Path(saved_path)
        else:
            self._extract_path = get_desktop_path()
        self._installer.extract_path = self._extract_path

        system_info = {
            "winget_available": winget_ok,
            "winget_version": winget_ver,
            "is_admin": admin,
            "extract_path": str(self._extract_path),
        }

        return {
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
        }

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
        """Переключает язык между ru и en и возвращает актуальные строки и твики."""
        new_lang = "en" if i18n.lang == "ru" else "ru"
        i18n.set_language(new_lang)
        settings = load_settings()
        settings["language"] = new_lang
        save_settings(settings)
        return {
            "lang": new_lang,
            "strings": STRINGS.get(new_lang, STRINGS["ru"]),
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

    def uninstall_app(self, app_id: str):
        """Запуск деинсталляции приложения."""
        app = self._catalog_map.get(app_id)
        if not app:
            return

        def worker():
            self.call_js("onAppStatus", app_id, "uninstalling", i18n.t("status_uninstalling"))
            self.call_js("onLog", i18n.t("log_start_uninstall", name=app.name))
            res = uninstall_app(app)
            if res.success:
                self.call_js("onAppStatus", app_id, "idle", "")
                self.call_js("onAppUninstalled", app_id)
                self.call_js("onLog", i18n.t("log_uninstalled", name=app.name))
            else:
                self.call_js("onAppStatus", app_id, "error", res.error)
                self.call_js("onLog", i18n.t("log_uninstall_error", name=app.name, error=res.error))

        threading.Thread(target=worker, daemon=True).start()

    # ==========================================
    # Настройки и исключения
    # ==========================================

    def get_settings(self) -> dict:
        return load_settings()

    def save_settings(self, settings_dict: dict) -> bool:
        return save_settings(settings_dict)

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
                if chosen.exists():
                    self._extract_path = chosen
                    self._installer.extract_path = self._extract_path
                    settings = load_settings()
                    settings["extract_path"] = str(self._extract_path)
                    save_settings(settings)
                    self.call_js("onLog", f"📁 Путь распаковки: {self._extract_path}")
                    return str(self._extract_path)
        except Exception as e:
            logger.error(f"Error browsing extract path: {e}")
        return str(self._extract_path)

    def set_extract_path_to_desktop(self) -> str:
        """Устанавливает путь распаковки на Рабочий стол текущего пользователя."""
        desktop = get_desktop_path()
        self._extract_path = desktop
        self._installer.extract_path = self._extract_path
        settings = load_settings()
        settings["extract_path"] = str(self._extract_path)
        save_settings(settings)
        self.call_js("onLog", f"📁 Путь распаковки установлен на Рабочий стол: {self._extract_path}")
        return str(self._extract_path)

    def set_extract_path_to_exe_dir(self) -> str:
        """Устанавливает путь распаковки рядом с исполняемым файлом программы."""
        exe_dir = get_exe_dir()
        self._extract_path = exe_dir
        self._installer.extract_path = self._extract_path
        settings = load_settings()
        settings["extract_path"] = str(self._extract_path)
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
                result = self._downloader.download(app, progress_cb)
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

    # ==========================================
    # Твики и фичи
    # ==========================================

    def get_tweaks(self) -> list[dict]:
        return get_all_tweaks(i18n.lang)

    def apply_tweak(self, tweak_id: str) -> dict[str, Any]:
        return apply_tweak_by_id(tweak_id)

    def revert_tweak(self, tweak_id: str) -> dict[str, Any]:
        return revert_tweak_by_id(tweak_id)

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
            updates = check_updates_sync(installed_map)
            self.call_js("onInstalledAppsDetected", installed_map)
            self.call_js("onUpdatesChecked", updates)

        threading.Thread(target=worker, daemon=True).start()

    def _do_upgrade_sync(self, app_id: str) -> bool:
        """Синхронное обновление одного приложения с потоковым выводом в реальном времени."""
        app = self._catalog_map.get(app_id)
        if not app:
            return False

        if not app.winget_id and not app.github_repo and not app.direct_url:
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

            d_res = self._downloader.download(app, progress_cb)
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

            self.call_js("onAppStatus", app_id, "installing", "⚙️ Установка обновления...")
            self.call_js("onAppProgress", app_id, 90, "⚙️ Запуск установщика...")
            self.call_js("onLog", f"⚙️ Установка новой версии {app.name}...")

            inst_res = self._installer.run(app, Path(d_res.installer_path), silent=False)
            if inst_res.success:
                self.call_js("onAppProgress", app_id, 100, "Готово!")
                self.call_js("onAppStatus", app_id, "done", "")
                self.call_js("onLog", f"✅ {app.name} успешно обновлён!")
                self.call_js("onUpdateCompleted", app_id)
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
            logger.error(f"Error upgrading {app.name}: {e}")
            self.call_js("onAppProgress", app_id, 0, "")
            self.call_js("onAppStatus", app_id, "idle", "")
            self.call_js("onLog", f"❌ Ошибка обновления {app.name}: {e}")
            return False
        finally:
            self._active_upgrades -= 1

    def upgrade_app(self, app_id: str):
        """Обновляет приложение в отдельном фоновом потоке."""
        def worker():
            self._do_upgrade_sync(app_id)
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
                    self.call_js("onOverallProgress", 0, 1, "Готово")
                    self.call_js("onUpdateAllDone")
                    return

                self.call_js("onLog", f"⬆️ Запуск последовательного обновления {total} приложений...")
                success_count = 0

                for idx, aid in enumerate(target_ids):
                    app = self._catalog_map.get(aid)
                    app_name = app.name if app else aid
                    self.call_js("onOverallProgress", idx, total, f"Обновление {app_name} ({idx + 1}/{total})")
                    if self._do_upgrade_sync(aid):
                        success_count += 1
                    self.call_js("onOverallProgress", idx + 1, total, f"Завершено {idx + 1}/{total}")

                self.call_js("onOverallProgress", total, total, f"Готово: {success_count}/{total}")
                self.call_js("onLog", f"✨ Обновление завершено: {success_count}/{total} успешно обновлено.")
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
