"""
ZiablWinSetup — Модуль автоматического обновления самого приложения (Self-Updater).
Проверяет наличие новых версий на GitHub Releases, скачивает новую версию в фоне
и перезапускает приложение через автономный открепленный процесс Windows (как в TG WS Proxy).
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.version import __version__, APP_NAME, GITHUB_REPO

logger = logging.getLogger("WinSetup")


def parse_version_tuple(ver_str: str) -> tuple[int, ...]:
    """Преобразует строку версии ('v1.2.0' или '1.2.0') в кортеж чисел (1, 2, 0)."""
    if not ver_str:
        return (0, 0, 0)
    cleaned = ver_str.lstrip("vV").strip()
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0, 0, 0)
    return tuple(int(p) for p in parts)


def is_newer_version(latest_ver: str, current_ver: str = __version__) -> bool:
    """Возвращает True, если latest_ver строго больше current_ver."""
    return parse_version_tuple(latest_ver) > parse_version_tuple(current_ver)


def cleanup_old_files():
    """Удаляет временные файлы .old и .bak, оставшиеся после предыдущего обновления."""
    try:
        exe_dir = Path(sys.executable).resolve().parent
        for old_file in exe_dir.glob("*.old"):
            try:
                old_file.unlink(missing_ok=True)
                logger.debug(f"Удален старый файл обновления: {old_file}")
            except Exception:
                pass
        for bak_file in exe_dir.glob("*.bak"):
            try:
                bak_file.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Ошибка при очистке старых файлов обновления: {e}")


def check_for_app_update(current_version: str = __version__) -> dict[str, Any]:
    """
    Проверяет наличие новой версии ZiablWinSetup в GitHub Releases.
    Возвращает словарь с метаданными релиза и статусом обновления.
    """
    cleanup_old_files()

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    logger.info(f"Проверка обновлений приложения: {url} (текущая версия: v{current_version})...")

    headers = {
        "User-Agent": f"ZiablWinSetup/{current_version}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag_name = data.get("tag_name", "").strip()
        latest_ver = tag_name.lstrip("vV").strip()
        release_title = data.get("name") or f"ZiablWinSetup v{latest_ver}"
        release_notes = data.get("body", "").strip()
        published_at = data.get("published_at", "")
        html_url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"

        # Ищем исполняемый файл ZiablWinSetup.exe среди ассетов
        assets = data.get("assets", [])
        exe_asset = None
        for a in assets:
            name = a.get("name", "").lower()
            if name.endswith(".exe"):
                exe_asset = a
                if "ziablwinsetup" in name:
                    break

        download_url = exe_asset.get("browser_download_url") if exe_asset else None
        file_size = exe_asset.get("size", 0) if exe_asset else 0

        has_update = bool(download_url and is_newer_version(latest_ver, current_version))

        logger.info(
            f"Результат проверки: последняя версия v{latest_ver}, "
            f"текущая v{current_version}, доступно обновление: {has_update}"
        )

        return {
            "success": True,
            "update_available": has_update,
            "current_version": current_version,
            "latest_version": latest_ver,
            "tag_name": tag_name,
            "release_title": release_title,
            "release_notes": release_notes,
            "download_url": download_url,
            "file_size": file_size,
            "published_at": published_at,
            "html_url": html_url,
        }

    except Exception as e:
        logger.warning(f"Не удалось проверить обновления приложения на GitHub: {e}")
        return {
            "success": False,
            "update_available": False,
            "current_version": current_version,
            "latest_version": current_version,
            "error": str(e),
        }


def download_and_apply_update(
    download_url: str,
    progress_callback: Callable[[int, str], None] = None,
    exit_callback: Callable[[], None] = None,
) -> tuple[bool, str]:
    """
    Скачивает новую версию приложения с прогрессом и запускает автономный скрипт
    замены исполняемого файла и перезапуска.
    """
    if not download_url:
        return False, "Не указан URL для скачивания обновления."

    temp_dir = Path(tempfile.gettempdir())
    timestamp = int(time.time())
    new_exe_path = temp_dir / f"ZiablWinSetup_new_{timestamp}.exe"
    updater_cmd_path = temp_dir / f"ziabl_update_{timestamp}.cmd"

    try:
        logger.info(f"Скачивание обновления из {download_url} в {new_exe_path}...")
        if progress_callback:
            progress_callback(5, "Подключение к серверу GitHub...")

        req = urllib.request.Request(download_url, headers={"User-Agent": "ZiablWinSetup/SelfUpdater"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 128 * 1024  # 128 KB
            start_time = time.time()
            last_update_time = start_time

            with open(new_exe_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_update_time >= 0.12 or downloaded == total_size:
                        last_update_time = now
                        elapsed = max(now - start_time, 0.01)
                        speed_mb = (downloaded / (1024 * 1024)) / elapsed
                        pct = int((downloaded / total_size) * 90) if total_size > 0 else 50
                        dl_mb = downloaded / (1024 * 1024)
                        tot_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                        status_str = f"{dl_mb:.1f} МБ / {tot_mb:.1f} МБ ({speed_mb:.1f} МБ/с)"
                        if progress_callback:
                            progress_callback(pct, status_str)

        if not new_exe_path.exists() or new_exe_path.stat().st_size < 1024 * 1024:
            return False, "Скачанный файл поврежден или имеет неверный размер."

        if progress_callback:
            progress_callback(95, "Подготовка к перезапуску...")

        # Определяем целевой путь исполняемого файла
        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            target_exe = Path(sys.executable).resolve()
        else:
            # Для режима разработки: заменяем dist/ZiablWinSetup.exe или запускаем скачанный
            dev_dist = Path(__file__).resolve().parent.parent / "dist" / "ZiablWinSetup.exe"
            target_exe = dev_dist if dev_dist.exists() else new_exe_path

        current_pid = os.getpid()

        # Формируем надежный Windows cmd-скрипт обновления:
        # 1. Ждет завершения текущего процесса (по PID)
        # 2. Безопасно переименовывает старый EXE в .old (разблокировка NTFS)
        # 3. Перемещает/копирует новый EXE на место целевого
        # 4. Запускает обновленный EXE
        # 5. Очищает временные файлы и удаляет сам cmd-скрипт
        target_name = target_exe.name
        cmd_content = f"""@echo off
chcp 65001 >nul
set "PID={current_pid}"
set "NEW_EXE={new_exe_path}"
set "TARGET_EXE={target_exe}"
set "TARGET_NAME={target_name}"

:wait_loop
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

timeout /t 1 /nobreak >nul

if exist "%TARGET_EXE%.old" del /f /q "%TARGET_EXE%.old" 2>nul
if exist "%TARGET_EXE%" ren "%TARGET_EXE%" "%TARGET_NAME%.old" 2>nul

copy /y "%NEW_EXE%" "%TARGET_EXE%" >nul
if errorlevel 1 (
    move /y "%NEW_EXE%" "%TARGET_EXE%" >nul
)

del /f /q "%NEW_EXE%" 2>nul
del /f /q "%TARGET_EXE%.old" 2>nul

start "" "%TARGET_EXE%"
(goto) 2>nul & del "%~f0"
"""
        updater_cmd_path.write_text(cmd_content, encoding="utf-8")
        logger.info(f"Создан автономный скрипт обновления: {updater_cmd_path}")

        if progress_callback:
            progress_callback(100, "Перезапуск приложения...")

        # Запускаем открепленный процесс cmd.exe
        subprocess.Popen(
            ["cmd.exe", "/c", str(updater_cmd_path)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )

        logger.info("Открепленный процесс обновления запущен. Завершение работы текущего процесса...")

        if exit_callback:
            try:
                exit_callback()
            except Exception as ex:
                logger.warning(f"Error executing exit_callback: {ex}")

        return True, "Обновление готово. Приложение перезапускается..."

    except Exception as e:
        logger.error(f"Ошибка при скачивании и применении обновления: {e}", exc_info=True)
        try:
            if new_exe_path.exists():
                new_exe_path.unlink(missing_ok=True)
            if updater_cmd_path.exists():
                updater_cmd_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"Ошибка обновления: {e}"
