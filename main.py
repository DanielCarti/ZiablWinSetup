"""
ZiablWinSetup — Точка входа.
Запускает GUI-приложение для массовой установки софта.
"""

import sys
import os

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Защита от утечки служебных переменных PyInstaller в дочерние процессы (self-updater, winget и др.)
for _var in list(os.environ.keys()):
    if _var.startswith(("_PYI", "_MEI", "PYTHONHOME", "PYTHONPATH", "PYINSTALLER")):
        os.environ.pop(_var, None)

# Защита от 'lost sys.stdin/stdout/stderr' в оконном режиме PyInstaller (console=False)
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from app.utils import setup_logging, is_admin


def main():
    # Проверка единственного экземпляра приложения (Single Instance Guard)
    from app.single_instance import single_instance_guard
    if not single_instance_guard.check_and_acquire():
        sys.exit(0)

    # Настраиваем логирование
    logger = setup_logging()

    # Очистка временных файлов от предыдущих самообновлений (*.old, *.bak)
    try:
        from app.self_updater import cleanup_old_files
        cleanup_old_files()
    except Exception as e:
        logger.debug(f"Cleanup old update files error: {e}")

    logger.info("=" * 50)
    logger.info("ZiablWinSetup запускается...")
    logger.info(f"Python {sys.version}")
    logger.info(f"Права администратора: {'Да' if is_admin() else 'Нет'}")
    logger.info("=" * 50)

    if not is_admin():
        logger.warning(
            "Запущено без прав администратора. "
            "Некоторые установщики могут потребовать UAC-подтверждение."
        )

    # Запуск в скрытом режиме трея при автозапуске Windows
    start_in_tray = "--tray" in sys.argv or "--minimized" in sys.argv
    if start_in_tray:
        logger.info("Запуск приложения в фоновом режиме (в системном трее)...")

    # Запускаем современный аппаратный GUI (Edge WebView2)
    try:
        from app.gui_webview import run_app
        run_app(start_in_tray=start_in_tray)
    except Exception as e:
        logger.error(f"Критическая ошибка запуска GUI: {e}", exc_info=True)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Критическая ошибка запуска ZiablWinSetup:\n\n{e}",
                "ZiablWinSetup - Ошибка",
                0x10,
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
