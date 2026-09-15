"""
WinSetup — Утилиты: проверка winget, прав администратора, управление директориями.
"""

import ctypes
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def check_winget() -> bool:
    """Проверяет, доступен ли winget в системе."""
    try:
        result = subprocess.run(
            ["winget", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_winget_version() -> str | None:
    """Возвращает версию winget или None."""
    try:
        result = subprocess.run(
            ["winget", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def is_admin() -> bool:
    """Проверяет, запущен ли процесс с правами администратора."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False


def request_admin_restart():
    """Перезапускает скрипт с запросом прав администратора (UAC)."""
    if is_admin():
        return

    script = sys.argv[0]
    params = " ".join(sys.argv[1:])

    # Если запущен как .py файл
    if script.endswith(".py"):
        executable = sys.executable
        params = f'"{script}" {params}'
    else:
        executable = script
        params = params

    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
    except Exception:
        pass

    sys.exit(0)


def get_download_dir() -> Path:
    """Возвращает директорию для скачивания установщиков."""
    download_dir = Path(tempfile.gettempdir()) / "WinSetup_Downloads"
    return download_dir


def ensure_download_dir() -> Path:
    """Создаёт директорию для скачивания, если её нет, и возвращает путь."""
    download_dir = get_download_dir()
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def cleanup_download_dir():
    """Удаляет временную директорию со скачанными установщиками."""
    import shutil
    download_dir = get_download_dir()
    if download_dir.exists():
        try:
            shutil.rmtree(download_dir, ignore_errors=True)
        except Exception:
            pass


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Настраивает и возвращает логгер приложения."""
    logger = logging.getLogger("WinSetup")
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def format_size(size_bytes: int) -> str:
    """Форматирует размер файла в человекочитаемый вид."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def open_folder(path: Path):
    """Открывает папку в проводнике Windows."""
    try:
        os.startfile(str(path))
    except Exception:
        pass
