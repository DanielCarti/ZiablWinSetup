"""
WinSetup — Модуль скачивания.
Скачивает установщики через winget download, прямые URL или GitHub Releases API.
"""

import fnmatch
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.catalog import AppEntry
from app.utils import ensure_download_dir, format_size

logger = logging.getLogger("WinSetup")

# Тип callback-функции прогресса: (app_id, percent 0-100, status_text)
ProgressCallback = Callable[[str, float, str], None]


def _safe_cb(cb: ProgressCallback, *args):
    """Безопасный вызов callback-функции без риска прерывания загрузки из-за ошибок UI или кодировки."""
    try:
        cb(*args)
    except Exception:
        pass


@dataclass
class DownloadResult:
    """Результат скачивания."""
    app: AppEntry
    success: bool
    installer_path: Path | None = None
    error: str = ""


class Downloader:
    """Менеджер скачивания установщиков."""

    def __init__(self, download_dir: Path | None = None):
        self.download_dir = download_dir or ensure_download_dir()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._cancelled = False
        self._cancelled_apps: set[str] = set()
        self._active_processes: dict[str, subprocess.Popen] = {}

    def cancel(self):
        """Отменяет все текущие и будущие скачивания."""
        self._cancelled = True
        for proc in list(self._active_processes.values()):
            try:
                proc.kill()
            except Exception:
                pass

    def cancel_app(self, app_id: str):
        """Отменяет скачивание конкретного приложения."""
        self._cancelled_apps.add(app_id)
        proc = self._active_processes.get(app_id)
        if proc and proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def reset_app(self, app_id: str):
        """Сбрасывает флаг отмены для отдельного приложения."""
        self._cancelled_apps.discard(app_id)

    def is_app_cancelled(self, app_id: str) -> bool:
        """Проверяет, было ли отменено скачивание для всего процесса или для конкретного приложения."""
        return self._cancelled or (app_id in self._cancelled_apps)

    def reset(self):
        """Сбрасывает флаг отмены."""
        self._cancelled = False
        self._cancelled_apps.clear()
        self._active_processes.clear()

    def get_cached_installer(self, app: AppEntry, target_version: str = "") -> Path | None:
        """
        Проверяет, скачан ли уже подходящий и валидный установщик для приложения в локальном кэше.
        Если указана target_version, проверяет соответствие версии в имени файла или PE-метаданных.
        """
        app_dir = self.download_dir / app.id
        if not app_dir.exists():
            return None

        candidates: list[Path] = []
        for item in app_dir.rglob("*"):
            if item.is_file():
                ext = item.suffix.lower()
                if ext in (".exe", ".msi", ".zip", ".msix", ".msixbundle") and not item.name.endswith((".part", ".tmp", ".old")):
                    try:
                        if item.stat().st_size >= 256 * 1024:
                            candidates.append(item)
                    except Exception:
                        pass

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if target_version:
            clean_ver = target_version.lstrip("vV").strip()
            # 1. Поиск по имени файла (например OBS-Studio-32.2.2...)
            for cand in candidates:
                if clean_ver in cand.name:
                    return cand

            # 2. Поиск по PE ресурсам GetFileVersionInfo
            from app.utils import get_file_version
            for cand in candidates:
                if cand.suffix.lower() in (".exe", ".dll"):
                    pe_ver = get_file_version(cand)
                    if pe_ver and clean_ver in pe_ver:
                        return cand

            # 3. Поиск по манифестам winget .yaml
            for yaml_file in app_dir.glob("*.yaml"):
                try:
                    content = yaml_file.read_text(encoding="utf-8", errors="ignore")
                    if f"PackageVersion: {clean_ver}" in content or f"PackageVersion: {target_version}" in content:
                        for cand in candidates:
                            if clean_ver in cand.name:
                                return cand
                except Exception:
                    pass

            return None

        return candidates[0]

    def download(self, app: AppEntry, progress_cb: ProgressCallback | None = None, target_winget_id: str = "", target_version: str = "") -> DownloadResult:
        """
        Скачивает установщик для приложения.
        Приоритет: локальный кэш → GitHub releases → winget download → direct URL.
        """
        if self.is_app_cancelled(app.id):
            return DownloadResult(app=app, success=False, error="Отменено")

        cb = progress_cb or (lambda *_: None)

        # 0. Проверяем локальный кэш на наличие уже скачанного установщика
        cached_file = self.get_cached_installer(app, target_version=target_version)
        if cached_file:
            size_str = format_size(cached_file.stat().st_size)
            logger.info(f"Используется готовый установщик из кэша для {app.name}: {cached_file.name} ({size_str})")
            _safe_cb(cb, app.id, 100, f"Готово (из кэша: {size_str})")
            return DownloadResult(app=app, success=True, installer_path=cached_file)

        # Создаём отдельную папку для каждого приложения (чтобы не путать файлы)
        app_dir = self.download_dir / app.id
        app_dir.mkdir(parents=True, exist_ok=True)

        last_error = ""

        # Приоритет 1: GitHub releases (прямая загрузка с CDN через urllib с отображением байтов и скорости)
        if app.github_repo:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание с GitHub...")
            result = self._download_github(app, app_dir, cb)
            if result.success or self.is_app_cancelled(app.id):
                return result
            last_error = result.error
            logger.warning(f"GitHub download failed for {app.name}: {result.error}, trying winget/fallback...")

        # Приоритет 2: winget download
        effective_winget_id = target_winget_id or app.winget_id
        if effective_winget_id:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание через winget...")
            result = self._download_winget(app, app_dir, cb, target_winget_id=effective_winget_id)
            if result.success or self.is_app_cancelled(app.id):
                return result
            last_error = result.error
            logger.warning(f"winget download failed for {app.name}: {result.error}, trying fallback...")

        # Приоритет 3: Direct URL
        if app.direct_url:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание по прямой ссылке...")
            result = self._download_url(app, app.direct_url, app_dir, cb)
            if result.success or self.is_app_cancelled(app.id):
                return result
            last_error = result.error
            logger.warning(f"Direct URL download failed for {app.name}: {result.error}")

        if last_error:
            if "не удается найти указанный файл" in last_error.lower() or "winerror 2" in last_error.lower():
                final_error = "Winget не установлен в системе, а резервная ссылка недоступна"
            else:
                final_error = f"Ошибка скачивания: {last_error}"
        else:
            final_error = "Нет доступных источников для скачивания"

        return DownloadResult(
            app=app,
            success=False,
            error=final_error,
        )

    def _download_winget(self, app: AppEntry, dest_dir: Path, cb: ProgressCallback, target_winget_id: str = "") -> DownloadResult:
        """Скачивает установщик через winget download с неблокирующим чтением и таймером активности."""
        try:
            import queue
            import time

            # Запоминаем файлы до скачивания
            existing_files = set(dest_dir.iterdir()) if dest_dir.exists() else set()
            pkg_id = target_winget_id or app.winget_id

            cmd = [
                "winget", "download",
                "--id", pkg_id,
                "-d", str(dest_dir),
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--disable-interactivity",
            ]

            logger.info(f"Running: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
            self._active_processes[app.id] = process

            output_lines = []
            line_queue = queue.Queue()

            def reader_thread():
                try:
                    for line in iter(process.stdout.readline, ""):
                        line_queue.put(line)
                except Exception:
                    pass
                finally:
                    try:
                        process.stdout.close()
                    except Exception:
                        pass

            r_thread = threading.Thread(target=reader_thread, daemon=True)
            r_thread.start()

            start_time = time.time()
            last_status_time = start_time

            try:
                while True:
                    if self.is_app_cancelled(app.id):
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                                capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW
                            )
                        except Exception:
                            process.kill()
                        return DownloadResult(app=app, success=False, error="Отменено пользователем")

                    # Забираем поступившие строки вывода
                    while not line_queue.empty():
                        try:
                            line = line_queue.get_nowait().strip()
                        except queue.Empty:
                            break
                        if line:
                            output_lines.append(line)
                            logger.debug(f"winget: {line}")

                            match = re.search(r'(\d+)\s*%', line)
                            if match:
                                percent = int(match.group(1))
                                cb(app.id, percent, f"Скачивание... {percent}%")
                            elif any(w in line.lower() for w in ["хэш", "hash", "проверка"]):
                                cb(app.id, 92, "Проверка хэша установщика...")

                    if process.poll() is not None and line_queue.empty():
                        break

                    now = time.time()
                    if now - last_status_time >= 0.5:
                        last_status_time = now
                        elapsed = int(now - start_time)
                        curr_size = 0
                        if dest_dir.exists():
                            for f in dest_dir.iterdir():
                                if f not in existing_files and not f.name.endswith(".yaml"):
                                    try:
                                        curr_size += f.stat().st_size
                                    except Exception:
                                        pass
                        if curr_size > 0:
                            mb = curr_size / (1024 * 1024)
                            cb(app.id, -1, f"Скачивание через winget ({mb:.1f} МБ, {elapsed} сек)...")
                        else:
                            cb(app.id, -1, f"Скачивание через winget ({elapsed} сек)...")

                    time.sleep(0.1)

                returncode = process.wait()
            finally:
                self._active_processes.pop(app.id, None)

            if returncode != 0:
                error_text = "\n".join(output_lines[-5:])
                return DownloadResult(
                    app=app, success=False,
                    error=f"winget завершился с кодом {returncode}: {error_text}"
                )

            # Ищем скачанный файл
            installer_path = self._find_downloaded_file(dest_dir, existing_files)

            if installer_path:
                _safe_cb(cb, app.id, 100, "Скачано")
                logger.info(f"Downloaded {app.name} → {installer_path}")
                return DownloadResult(app=app, success=True, installer_path=installer_path)

            return DownloadResult(
                app=app, success=False,
                error="Файл установщика не найден после скачивания"
            )

        except Exception as e:
            return DownloadResult(app=app, success=False, error=str(e))

    def _download_github(self, app: AppEntry, dest_dir: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает последний релиз с GitHub."""
        try:
            api_url = f"https://api.github.com/repos/{app.github_repo}/releases/latest"

            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "WinSetup/1.0", "Accept": "application/vnd.github.v3+json"},
            )

            cb(app.id, 0, "Получение информации о релизе...")

            with urllib.request.urlopen(req, timeout=30) as response:
                release_data = json.loads(response.read().decode("utf-8"))

            assets = release_data.get("assets", [])
            if not assets:
                return DownloadResult(app=app, success=False, error="Нет файлов в релизе")

            # Ищем подходящий asset
            download_url = None
            asset_name = None

            if app.github_asset_pattern:
                for asset in assets:
                    name = asset["name"].lower()
                    pattern = app.github_asset_pattern.lower()
                    if fnmatch.fnmatch(name, pattern):
                        download_url = asset["browser_download_url"]
                        asset_name = asset["name"]
                        break

            # Если паттерн не помог, берём первый exe/msi/zip
            if not download_url:
                for ext in [".exe", ".msi", ".zip"]:
                    for asset in assets:
                        if asset["name"].lower().endswith(ext):
                            download_url = asset["browser_download_url"]
                            asset_name = asset["name"]
                            break
                    if download_url:
                        break

            if not download_url:
                # Берём просто первый asset
                download_url = assets[0]["browser_download_url"]
                asset_name = assets[0]["name"]

            # Скачиваем файл с проверкой кэша
            dest_path = dest_dir / asset_name
            remote_size = int(asset.get("size", 0)) if asset else 0
            if dest_path.exists() and dest_path.stat().st_size >= 256 * 1024:
                if remote_size == 0 or dest_path.stat().st_size == remote_size:
                    size_str = format_size(dest_path.stat().st_size)
                    logger.info(f"Файл {asset_name} уже в кэше ({size_str}), повторная загрузка пропущена.")
                    _safe_cb(cb, app.id, 100, f"Готово (из кэша: {size_str})")
                    return DownloadResult(app=app, success=True, installer_path=dest_path)

            return self._download_file(app, download_url, dest_path, cb)

        except urllib.error.URLError as e:
            return DownloadResult(app=app, success=False, error=f"Ошибка сети: {e}")
        except Exception as e:
            return DownloadResult(app=app, success=False, error=str(e))

    def _download_url(self, app: AppEntry, url: str, dest_dir: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает файл по прямому URL с проверкой кэша."""
        try:
            # Определяем имя файла из URL
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            filename = unquote(parsed.path.split("/")[-1]) or f"{app.id}_installer.exe"

            # Если filename не имеет расширения, добавляем .exe
            if "." not in filename:
                filename += ".exe"

            dest_path = dest_dir / filename

            # Если файл уже существует в кэше, проверяем Content-Length через быстрый HEAD запрос
            if dest_path.exists() and dest_path.stat().st_size >= 256 * 1024:
                try:
                    head_req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                        method="HEAD"
                    )
                    with urllib.request.urlopen(head_req, timeout=5) as head_resp:
                        cl = head_resp.headers.get("Content-Length")
                        if cl and int(cl) == dest_path.stat().st_size:
                            size_str = format_size(dest_path.stat().st_size)
                            logger.info(f"Файл {dest_path.name} уже в кэше ({size_str}), повторная загрузка пропущена.")
                            _safe_cb(cb, app.id, 100, f"Готово (из кэша: {size_str})")
                            return DownloadResult(app=app, success=True, installer_path=dest_path)
                except Exception:
                    pass

            return self._download_file(app, url, dest_path, cb)

        except Exception as e:
            return DownloadResult(app=app, success=False, error=str(e))

    def _download_file(self, app: AppEntry, url: str, dest_path: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает файл с URL в указанный путь с отображением прогресса и атомарной записью через .part."""
        part_path = dest_path.with_suffix(dest_path.suffix + ".part")
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            if "amd.com" in parsed.netloc:
                referer = "https://www.amd.com/"

            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            if "techpowerup.com" in parsed.netloc:
                user_agent = "winget-cli"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Referer": referer,
                },
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                total_size = response.headers.get("Content-Length")
                total_size = int(total_size) if total_size else None

                downloaded = 0
                block_size = 8192 * 4  # 32KB blocks

                with open(part_path, "wb") as f:
                    while True:
                        if self.is_app_cancelled(app.id):
                            f.close()
                            if part_path.exists():
                                try:
                                    part_path.unlink()
                                except Exception:
                                    pass
                            return DownloadResult(app=app, success=False, error="Отменено пользователем")

                        block = response.read(block_size)
                        if not block:
                            break

                        f.write(block)
                        downloaded += len(block)

                        if total_size:
                            percent = (downloaded / total_size) * 100
                            size_str = f"{format_size(downloaded)} / {format_size(total_size)}"
                            cb(app.id, percent, f"Скачивание... {size_str}")
                        else:
                            cb(app.id, -1, f"Скачивание... {format_size(downloaded)}")

            # Загрузка завершена успешно — заменяем .part на финальный файл
            if part_path.exists():
                if dest_path.exists():
                    try:
                        dest_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                part_path.replace(dest_path)

            _safe_cb(cb, app.id, 100, "Скачано")
            logger.info(f"Downloaded {app.name} → {dest_path}")
            return DownloadResult(app=app, success=True, installer_path=dest_path)

        except urllib.error.URLError as e:
            if part_path.exists():
                try:
                    part_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return DownloadResult(app=app, success=False, error=f"Ошибка загрузки: {e}")
        except Exception as e:
            if part_path.exists():
                try:
                    part_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return DownloadResult(app=app, success=False, error=str(e))

    @staticmethod
    def _find_downloaded_file(directory: Path, exclude_files: set[Path] | None = None) -> Path | None:
        """
        Находит скачанный файл в директории.
        Ищет .exe, .msi, .msix, .zip файлы.
        """
        exclude = exclude_files or set()
        candidates = []

        for item in directory.rglob("*"):
            if item.is_file() and item not in exclude:
                ext = item.suffix.lower()
                if ext in (".exe", ".msi", ".msix", ".msixbundle", ".zip", ".appx", ".appxbundle"):
                    candidates.append(item)

        # Fallback: если winget обновил существующий файл или все файлы уже были в exclude
        if not candidates:
            for item in directory.rglob("*"):
                if item.is_file():
                    ext = item.suffix.lower()
                    if ext in (".exe", ".msi", ".msix", ".msixbundle", ".zip", ".appx", ".appxbundle"):
                        candidates.append(item)

        if not candidates:
            return None

        # Возвращаем самый свежий файл
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]
