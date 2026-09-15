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

logger = logging.getLogger("WinSetup")


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


def run_app():
    """Запускает главное окно приложения с максимальной скоростью загрузки."""
    html_path = get_ui_path()
    logger.info(f"Loading UI from: {html_path}")

    # Флаги Chromium для Edge WebView2: исключаем зависания при ресайзе/разворачивании окна
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--disable-features=CalculateNativeWinOcclusion,ElasticOverscroll "
        "--disable-backgrounding-occluded-windows "
        "--disable-renderer-backgrounding "
        "--disable-gpu-process-crash-limit"
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
    )
    bridge.set_window(window)

    def on_closing():
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
        return True

    window.events.closing += on_closing

    # Запуск с движком EdgeChromium (DirectX GPU) с сохраненным кэшем
    webview.start(
        debug=False,
        storage_path=str(cache_dir),
        private_mode=False,
        http_server=False,
    )
