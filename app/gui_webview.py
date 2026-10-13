"""
ZiablWinSetup — Запуск графического интерфейса на базе Edge WebView2 (Chromium).
Обеспечивает 144Hz DirectX аппаратное ускорение, отсутствие мерцания при Alt+Tab и плавный ресайз.
"""

import logging
import os
import sys
from pathlib import Path

import webview

from app.web_api import AppBridge
from app.i18n import i18n
from app.settings import load_settings
from app.tray import SystemTrayManager

logger = logging.getLogger("WinSetup")


import ctypes
from ctypes import wintypes
import threading
import time

def trim_app_memory():
    """Освобождает Working Set физической памяти для Python и всех дочерних процессов WebView2."""
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    if sys.platform != "win32":
        return

    try:
        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        k32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        # Очищаем память текущего процесса (Python)
        h_cur = k32.GetCurrentProcess()
        psapi.EmptyWorkingSet(h_cur)

        # Находим всех потомков текущего процесса (Edge WebView2)
        current_pid = os.getpid()
        snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        parents = {}
        if k32.Process32First(snap, ctypes.byref(entry)):
            while True:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                if not k32.Process32Next(snap, ctypes.byref(entry)):
                    break
        k32.CloseHandle(snap)

        descendants = []
        to_visit = [current_pid]
        while to_visit:
            curr = to_visit.pop(0)
            for pid, ppid in parents.items():
                if ppid == curr and pid not in descendants:
                    descendants.append(pid)
                    to_visit.append(pid)

        # Очищаем Working Set всех дочерних процессов WebView2
        for cpid in descendants:
            h = k32.OpenProcess(0x1F0FFF, False, cpid)
            if h:
                psapi.EmptyWorkingSet(h)
                k32.CloseHandle(h)
    except Exception as e:
        logger.debug(f"trim_app_memory error: {e}")


def _start_memory_optimizer():
    """Запускает периодическую очистку рабочей памяти приложения."""
    def worker():
        time.sleep(5)  # Ожидаем завершения начального рендеринга
        trim_app_memory()
        while True:
            time.sleep(60)
            trim_app_memory()
    t = threading.Thread(target=worker, daemon=True)
    t.start()


def get_ui_path() -> Path:
    """Определяет путь к файлу index.html (работает как в исходниках, так и внутри PyInstaller bundle)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
        candidate = base_dir / "app" / "ui" / "index.html"
        if candidate.exists():
            return candidate
        candidate2 = base_dir / "ui" / "index.html"
        if candidate2.exists():
            return candidate2

    # Режим разработки / исходного кода
    here = Path(__file__).resolve().parent
    candidate = here / "ui" / "index.html"
    if candidate.exists():
        return candidate

    return here.parent / "app" / "ui" / "index.html"


def run_app(start_in_tray: bool = False):
    """Запускает главное окно приложения с максимальной скоростью загрузки."""
    html_path = get_ui_path()
    logger.info(f"Loading UI from: {html_path} (start_in_tray={start_in_tray})")

    # Флаги Chromium для Edge WebView2: исключаем избыточное потребление RAM GPU-процессом
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--disable-features=CalculateNativeWinOcclusion,ElasticOverscroll "
        "--disable-gpu-rasterization "
        "--disable-gpu-memory-buffer-video-frames "
        "--renderer-process-limit=1 "
        "--enable-low-end-device-mode "
        "--js-flags=--max-old-space-size=128 "
        "--disable-backgrounding-occluded-windows=false"
    )

    # Разрешаем прямую загрузку файлов без запуска локального HTTP-сервера Bottle
    webview.settings["ALLOW_FILE_URLS"] = True

    # Настраиваем постоянный кэш WebView2, чтобы не пересоздавать профиль на каждом старте
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    cache_dir = Path(local_app_data) / "ZiablWinSetup" / "webview_cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    bridge = AppBridge()

    # Загружаем через file:// URI напрямую в Chromium (0 мс задержки, без открытия сокетов)
    window = webview.create_window(
        title=i18n.t("app_title"),
        url=html_path.resolve().as_uri(),
        js_api=bridge,
        width=1120,
        height=760,
        min_size=(900, 600),
        background_color="#181818",
        easy_drag=False,
        hidden=start_in_tray,
    )
    bridge.set_window(window)

    # Инициализация системного трея
    tray_manager = SystemTrayManager(window=window, on_quit_callback=bridge.quit_app)
    if start_in_tray:
        tray_manager._is_visible = False
    bridge.set_tray_manager(tray_manager)
    tray_manager.start()

    # Подключаем SingleInstanceGuard к функции активации окна
    from app.single_instance import single_instance_guard
    single_instance_guard.set_activate_callback(tray_manager.show_window)
    single_instance_guard.start_pipe_server()

    def on_closing():
        if bridge.is_quitting():
            tray_manager.stop()
            single_instance_guard.cleanup()
            return True

        settings = load_settings()
        if settings.get("minimize_to_tray_on_close", True):
            tray_manager.hide_window(show_notify=True)
            return False

        if bridge.is_busy():
            try:
                import ctypes
                title = "ZiablWinSetup — Подтверждение выхода" if i18n.lang == "ru" else "ZiablWinSetup — Exit Confirmation"
                text = (
                    "В данный момент выполняется скачивание, установка или обновление программ.\n\n"
                    "Прерывание процесса может привести к повреждению файлов или неполной установке.\n\n"
                    "Вы действительно хотите прервать работу и закрыть программу?"
                    if i18n.lang == "ru" else
                    "A download, installation, or update operation is currently in progress.\n\n"
                    "Interrupting this process may cause corrupted files or incomplete installation.\n\n"
                    "Are you sure you want to abort and exit?"
                )
                # MB_YESNO (0x04) | MB_ICONWARNING (0x30) | MB_DEFBUTTON2 (0x100)
                res = ctypes.windll.user32.MessageBoxW(0, text, title, 0x00000004 | 0x00000030 | 0x00000100)
                if res != 6:  # 6 is IDYES
                    return False
            except Exception as e:
                logger.error(f"Error in on_closing confirmation dialog: {e}")

        tray_manager.stop()
        single_instance_guard.cleanup()
        return True

    def on_closed():
        tray_manager.stop()
        single_instance_guard.cleanup()

    window.events.closing += on_closing
    window.events.closed += on_closed

    # Запуск фонового сборщика памяти
    _start_memory_optimizer()

    # Запуск с движком EdgeChromium (DirectX GPU) с сохраненным кэшем
    try:
        webview.start(
            debug=False,
            storage_path=str(cache_dir),
            private_mode=False,
            http_server=False,
        )
    finally:
        single_instance_guard.cleanup()
