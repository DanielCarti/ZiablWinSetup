"""
ZiablWinSetup — Модуль управления автозапуском самого приложения.
Позволяет включать/отключать запуск ZiablWinSetup при старте Windows через реестр HKCU\\...\\Run.
"""

import logging
import os
import sys
import winreg
from pathlib import Path

logger = logging.getLogger("WinSetup")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "ZiablWinSetup"


def get_app_launch_command() -> str:
    """Возвращает корректную команду запуска приложения с аргументом --tray."""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --tray'
    else:
        python_exe = Path(sys.executable).resolve()
        # Если есть pythonw.exe рядом, предпочтительнее запускать без консольного окна
        pythonw_exe = python_exe.parent / "pythonw.exe"
        if pythonw_exe.exists():
            python_exe = pythonw_exe
        main_py = (Path(__file__).resolve().parent.parent / "main.py").resolve()
        return f'"{python_exe}" "{main_py}" --tray'


def is_app_autostart_enabled() -> bool:
    """Проверяет, включен ли автозапуск ZiablWinSetup в реестре HKCU\\...\\Run."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_RUN_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Ошибка проверки автозапуска приложения: {e}")
        return False


def set_app_autostart(enabled: bool) -> bool:
    """Включает или выключает автозапуск ZiablWinSetup при входе в Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ) as key:
            if enabled:
                cmd = get_app_launch_command()
                winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, cmd)
                logger.info(f"Автозапуск включен: {APP_RUN_NAME} -> {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_RUN_NAME)
                    logger.info(f"Автозапуск отключен: {APP_RUN_NAME}")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        logger.error(f"Ошибка изменения автозапуска приложения: {e}")
        return False
