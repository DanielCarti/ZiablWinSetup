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
        exe_path = Path(sys.executable).resolve()
        exe_dir = exe_path.parent
        specific_old = exe_path.with_name(f"{exe_path.name}.old")
        if specific_old.exists():
            try:
                specific_old.unlink(missing_ok=True)
                logger.info(f"Удален старый файл обновления: {specific_old}")
            except Exception:
                pass
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
        logger.warning(f"Не удалось проверить обновления приложения через GitHub API: {e}. Пробуем веб-страницы...")
        try:
            web_url = f"https://github.com/{GITHUB_REPO}/releases"
            web_req = urllib.request.Request(web_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(web_req, timeout=7) as web_resp:
                web_html = web_resp.read().decode("utf-8", errors="ignore")
            tags = re.findall(rf"/{GITHUB_REPO}/releases/tag/([^\" >]+)", web_html)
            if tags:
                tag_name = tags[0].strip()
                latest_ver = tag_name.lstrip("vV").strip()
                download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_name}/ZiablWinSetup.exe"
                has_update = is_newer_version(latest_ver, current_version)
                logger.info(f"Веб-проверка: версия v{latest_ver}, обновление доступно: {has_update}")
                return {
                    "success": True,
                    "update_available": has_update,
                    "current_version": current_version,
                    "latest_version": latest_ver,
                    "tag_name": tag_name,
                    "release_title": f"ZiablWinSetup v{latest_ver}",
                    "release_notes": "Обновление стабильности и компонентов программы.",
                    "download_url": download_url,
                    "file_size": 0,
                    "published_at": "",
                    "html_url": f"https://github.com/{GITHUB_REPO}/releases/tag/{tag_name}",
                }
        except Exception as web_ex:
            logger.warning(f"Веб-проверка релизов также завершилась с ошибкой: {web_ex}")

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
    updater_ps1_path = temp_dir / f"ziabl_update_{timestamp}.ps1"
    updater_vbs_path = temp_dir / f"ziabl_update_{timestamp}.vbs"

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

        # Формируем абсолютно бесшумный автономный PowerShell-скрипт обновления:
        # 1. Ждет чистого завершения текущего процесса (по PID)
        # 2. Безопасно перемещает старый EXE в .old (разблокировка NTFS без дескрипторных конфликтов)
        # 3. Копирует новый EXE на место целевого с повторными попытками
        # 4. Запускает обновленный EXE в его рабочей директории
        # 5. Очищает временные файлы
        new_exe_ps = str(new_exe_path).replace("'", "''")
        target_exe_ps = str(target_exe).replace("'", "''")
        vbs_ps = str(updater_vbs_path).replace("'", "''")
        ps1_ps = str(updater_ps1_path).replace("'", "''")
        ps1_vbs = str(updater_ps1_path).replace('"', '""')

        ps_content = f"""$ErrorActionPreference = 'SilentlyContinue'

# 1. Ожидаем чистого и полного завершения ВСЕХ процессов старого приложения (и дочернего Python, и родительского PyInstaller bootloader)
$targetPid = {current_pid}
$targetPath = '{target_exe_ps}'
$targetStem = [System.IO.Path]::GetFileNameWithoutExtension($targetPath)
$timeout = [DateTime]::UtcNow.AddSeconds(30)

# Сначала ждем прямой PID вызывающего процесса
while ((Get-Process -Id $targetPid -ErrorAction SilentlyContinue) -and ([DateTime]::UtcNow -lt $timeout)) {{
    Start-Sleep -Milliseconds 250
}}

# Затем ждем завершения родительского bootloader и любых сопутствующих процессов данного exe
while ([DateTime]::UtcNow -lt $timeout) {{
    $procs = Get-Process -Name $targetStem -ErrorAction SilentlyContinue | Where-Object {{
        try {{ $_.Path -eq $targetPath }} catch {{ $true }}
    }}
    if (-not $procs) {{
        break
    }}
    Start-Sleep -Milliseconds 300
}}

# Пауза для окончательного освобождения файловых дескрипторов Windows и очистки каталога _MEI
Start-Sleep -Milliseconds 1200

# 2. Безопасная замена исполняемого файла с повторными попытками
$newExe = '{new_exe_ps}'
$targetExe = '{target_exe_ps}'
$targetOld = "$targetExe.old"
$replaced = $false

for ($i = 0; $i -lt 30; $i++) {{
    try {{
        if (Test-Path -LiteralPath $targetOld) {{
            Remove-Item -LiteralPath $targetOld -Force -ErrorAction SilentlyContinue
        }}
        if (Test-Path -LiteralPath $targetExe) {{
            Move-Item -LiteralPath $targetExe -Destination $targetOld -Force -ErrorAction Stop
        }}
        Copy-Item -LiteralPath $newExe -Destination $targetExe -Force -ErrorAction Stop
        $replaced = $true
        break
    }} catch {{
        Start-Sleep -Milliseconds 300
    }}
}}

# 3. Перезапуск обновленного приложения
if ($replaced -and (Test-Path -LiteralPath $targetExe)) {{
    # Снимаем метку Zone.Identifier (Mark-of-the-Web), чтобы Windows Defender и SmartScreen не блокировали чтение архива PyInstaller
    Unblock-File -LiteralPath $targetExe -ErrorAction SilentlyContinue

    # КРИТИЧЕСКИ ВАЖНО для PyInstaller:
    # Удаляем переменные _MEIPASS2, _MEIPASS, PYTHONHOME, PYTHONPATH из окружения PowerShell!
    # Если _MEIPASS2 остается в окружении, bootloader PyInstaller считает процесс дочерним
    # воркером и пытается загрузить DLL из старого (уже удаленного) временного каталога _MEIxxxxxx!
    Remove-Item env:_MEIPASS2 -ErrorAction SilentlyContinue
    Remove-Item env:_MEIPASS -ErrorAction SilentlyContinue
    Remove-Item env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item env:PYTHONPATH -ErrorAction SilentlyContinue
    [System.Environment]::SetEnvironmentVariable('_MEIPASS2', $null, [System.EnvironmentVariableTarget]::Process)
    [System.Environment]::SetEnvironmentVariable('_MEIPASS', $null, [System.EnvironmentVariableTarget]::Process)
    [System.Environment]::SetEnvironmentVariable('PYTHONHOME', $null, [System.EnvironmentVariableTarget]::Process)
    [System.Environment]::SetEnvironmentVariable('PYTHONPATH', $null, [System.EnvironmentVariableTarget]::Process)

    # Пауза для окончательной фиксации на диске NTFS и антивирусного сканирования
    Start-Sleep -Milliseconds 1200

    $workDir = Split-Path -Parent $targetExe

    # Запускаем приложение через оболочку Windows Shell (explorer.exe),
    # что гарантирует абсолютно чистое пользовательское окружение рабочего стола,
    # полностью изолированное от скрипта обновления:
    try {{
        $shell = New-Object -ComObject Shell.Application
        $shell.ShellExecute($targetExe, "", $workDir, "open", 1)
    }} catch {{
        Start-Process -FilePath $targetExe -WorkingDirectory $workDir
    }}
}}

# 4. Очистка временных файлов
Start-Sleep -Seconds 2
Remove-Item -LiteralPath $newExe -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $targetOld -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '{vbs_ps}' -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '{ps1_ps}' -Force -ErrorAction SilentlyContinue
"""
        updater_ps1_path.write_text(ps_content, encoding="utf-8")

        vbs_content = f'Set objShell = CreateObject("WScript.Shell")\nobjShell.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{ps1_vbs}""", 0, False\n'
        updater_vbs_path.write_text(vbs_content, encoding="ascii")
        logger.info(f"Созданы автономные скрипты обновления: {updater_ps1_path}, {updater_vbs_path}")

        if progress_callback:
            progress_callback(100, "Перезапуск приложения...")

        # Формируем очищенное окружение для процессов обновления,
        # исключая любые переменные PyInstaller
        clean_env = os.environ.copy()
        for env_var in ("_MEIPASS2", "_MEIPASS", "PYTHONHOME", "PYTHONPATH", "PYINSTALLER_STRICT_UNLOAD"):
            clean_env.pop(env_var, None)

        # Запускаем открепленный процесс обновления.
        # wscript.exe является GUI-подсистемой (IMAGE_SUBSYSTEM_WINDOWS_GUI),
        # поэтому Windows принципиально не создает консольных окон cmd/find.exe.
        launched = False
        try:
            subprocess.Popen(
                ["wscript.exe", "//B", "//Nologo", str(updater_vbs_path)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
                env=clean_env,
            )
            launched = True
            logger.info("Открепленный процесс обновления запущен через wscript.exe")
        except Exception as ex:
            logger.warning(f"Не удалось запустить через wscript ({ex}), резервный запуск powershell.exe...")

        if not launched:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(updater_ps1_path),
                ],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
                env=clean_env,
            )
            logger.info("Открепленный процесс обновления запущен через powershell.exe")

        logger.info("Процесс обновления запущен. Завершение работы текущего процесса...")

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
            if updater_ps1_path.exists():
                updater_ps1_path.unlink(missing_ok=True)
            if updater_vbs_path.exists():
                updater_vbs_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"Ошибка обновления: {e}"
