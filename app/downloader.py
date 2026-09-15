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

    def download(self, app: AppEntry, progress_cb: ProgressCallback | None = None) -> DownloadResult:
        """
        Скачивает установщик для приложения.
        Приоритет: winget download → GitHub releases → direct URL.
        """
        if self.is_app_cancelled(app.id):
            return DownloadResult(app=app, success=False, error="Отменено")

        cb = progress_cb or (lambda *_: None)

        # Создаём отдельную папку для каждого приложения (чтобы не путать файлы)
        app_dir = self.download_dir / app.id
        app_dir.mkdir(parents=True, exist_ok=True)

        # Приоритет 1: winget download
        if app.winget_id:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание через winget...")
            result = self._download_winget(app, app_dir, cb)
            if result.success or self.is_app_cancelled(app.id):
                return result
            logger.warning(f"winget download failed for {app.name}: {result.error}, trying fallback...")

        # Приоритет 2: GitHub releases
        if app.github_repo:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание с GitHub...")
            result = self._download_github(app, app_dir, cb)
            if result.success or self.is_app_cancelled(app.id):
                return result
            logger.warning(f"GitHub download failed for {app.name}: {result.error}")

        # Приоритет 3: Direct URL
        if app.direct_url:
            if self.is_app_cancelled(app.id):
                return DownloadResult(app=app, success=False, error="Отменено")
            cb(app.id, 0, "Скачивание по прямой ссылке...")
            result = self._download_url(app, app.direct_url, app_dir, cb)
            if result.success or self.is_app_cancelled(app.id):
                return result
            logger.warning(f"Direct URL download failed for {app.name}: {result.error}")

        return DownloadResult(
            app=app,
            success=False,
            error="Нет доступных источников для скачивания",
        )

    def _download_winget(self, app: AppEntry, dest_dir: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает установщик через winget download."""
        try:
            # Запоминаем файлы до скачивания
            existing_files = set(dest_dir.iterdir()) if dest_dir.exists() else set()

            cmd = [
                "winget", "download",
                "--id", app.winget_id,
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

            # Читаем вывод для отслеживания прогресса
            output_lines = []
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

                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break

                    line = line.strip()
                    if line:
                        output_lines.append(line)
                        logger.debug(f"winget: {line}")

                        # Пытаемся извлечь прогресс из вывода winget
                        match = re.search(r'(\d+)\s*%', line)
                        if match:
                            percent = int(match.group(1))
                            cb(app.id, percent, f"Скачивание... {percent}%")
                        elif any(w in line.lower() for w in ["хэш", "hash", "проверка"]):
                            cb(app.id, 90, "Проверка хэша установщика...")
                        elif "скачивание" in line.lower() or "download" in line.lower():
                            cb(app.id, -1, "Скачивание...")

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
                cb(app.id, 100, "Скачано ✓")
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

            # Скачиваем файл
            dest_path = dest_dir / asset_name
            return self._download_file(app, download_url, dest_path, cb)

        except urllib.error.URLError as e:
            return DownloadResult(app=app, success=False, error=f"Ошибка сети: {e}")
        except Exception as e:
            return DownloadResult(app=app, success=False, error=str(e))

    def _download_url(self, app: AppEntry, url: str, dest_dir: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает файл по прямому URL."""
        try:
            # Определяем имя файла из URL
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            filename = unquote(parsed.path.split("/")[-1]) or f"{app.id}_installer.exe"

            # Если filename не имеет расширения, добавляем .exe
            if "." not in filename:
                filename += ".exe"

            dest_path = dest_dir / filename
            return self._download_file(app, url, dest_path, cb)

        except Exception as e:
            return DownloadResult(app=app, success=False, error=str(e))

    def _download_file(self, app: AppEntry, url: str, dest_path: Path, cb: ProgressCallback) -> DownloadResult:
        """Скачивает файл с URL в указанный путь с отображением прогресса."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            if "amd.com" in parsed.netloc:
                referer = "https://www.amd.com/"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": referer,
                },
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                total_size = response.headers.get("Content-Length")
                total_size = int(total_size) if total_size else None

                downloaded = 0
                block_size = 8192 * 4  # 32KB blocks

                with open(dest_path, "wb") as f:
                    while True:
                        if self.is_app_cancelled(app.id):
                            f.close()
                            if dest_path.exists():
                                try:
                                    dest_path.unlink()
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

            cb(app.id, 100, "Скачано ✓")
            logger.info(f"Downloaded {app.name} → {dest_path}")
            return DownloadResult(app=app, success=True, installer_path=dest_path)

        except urllib.error.URLError as e:
            return DownloadResult(app=app, success=False, error=f"Ошибка загрузки: {e}")
        except Exception as e:
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
