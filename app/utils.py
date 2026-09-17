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


def ensure_winget_in_path():
    """Добавляет директорию WindowsApps в os.environ['PATH'], если её там нет."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        apps_dir = str(Path(localappdata) / "Microsoft" / "WindowsApps")
        if os.path.isdir(apps_dir):
            current_path = os.environ.get("PATH", "")
            if apps_dir.lower() not in current_path.lower():
                os.environ["PATH"] = f"{apps_dir};{current_path}"


def check_winget() -> bool:
    """Проверяет, доступен ли winget в системе."""
    ensure_winget_in_path()
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
    ensure_winget_in_path()
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


def open_winget_store():
    """Открывает страницу App Installer в приложении Microsoft Store."""
    try:
        os.startfile("ms-windows-store://pdp/?productid=9NBLGGH4NNS1")
    except Exception as e:
        logger.warning(f"Failed to open Microsoft Store: {e}")


def install_winget(progress_cb=None) -> tuple[bool, str]:
    """
    Автоматически скачивает и устанавливает официальный пакет Winget (DesktopAppInstaller).
    Возвращает (success: bool, message_or_version: str).
    """
    cb = progress_cb or (lambda *_: None)

    try:
        cb(10, "Получение официальной ссылки на Winget...")

        # 1. Поиск последней версии через GitHub API
        msix_url = "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle"
        try:
            import json
            import urllib.request
            req = urllib.request.Request(
                "https://api.github.com/repos/microsoft/winget-cli/releases/latest",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for asset in data.get("assets", []):
                    if asset.get("name", "").endswith(".msixbundle"):
                        msix_url = asset.get("browser_download_url", msix_url)
                        break
        except Exception as e:
            logger.info(f"Using default fallback URL for winget msixbundle: {e}")

        # 2. Скачивание пакета во временную директорию
        cb(25, "Скачивание Microsoft.DesktopAppInstaller...")
        temp_dir = Path(tempfile.gettempdir()) / "WinSetup_Winget"
        temp_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = temp_dir / "DesktopAppInstaller.msixbundle"

        import urllib.request
        req = urllib.request.Request(msix_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = resp.headers.get("Content-Length")
            total_size = int(total_size) if total_size else None
            downloaded = 0
            block_size = 65536

            with open(bundle_path, "wb") as f:
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        pct = int(25 + (downloaded / total_size) * 45)  # 25% to 70%
                        cb(pct, f"Скачивание... {int((downloaded / total_size) * 100)}%")

        # 3. Скачивание зависимостей VCLibs и UI.Xaml (для систем, где их нет)
        dependencies = []
        try:
            # VCLibs
            vclibs_path = temp_dir / "Microsoft.VCLibs.x64.14.00.Desktop.appx"
            if not vclibs_path.exists():
                cb(72, "Скачивание VCLibs...")
                vclibs_url = "https://aka.ms/Microsoft.VCLibs.x64.14.00.Desktop.appx"
                urllib.request.urlretrieve(vclibs_url, vclibs_path)
            if vclibs_path.exists() and vclibs_path.stat().st_size > 1000:
                dependencies.append(str(vclibs_path))

            # Microsoft.UI.Xaml 2.8
            xaml_path = temp_dir / "Microsoft.UI.Xaml.2.8.x64.appx"
            if not xaml_path.exists():
                cb(78, "Скачивание UI.Xaml...")
                xaml_url = "https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx"
                urllib.request.urlretrieve(xaml_url, xaml_path)
            if xaml_path.exists() and xaml_path.stat().st_size > 1000:
                dependencies.append(str(xaml_path))
        except Exception as e:
            logger.info(f"Optional dependencies download note: {e}")

        # 4. Установка через Add-AppxPackage
        cb(85, "Установка пакета в систему...")
        ps_cmd = f'Add-AppxPackage -Path "{bundle_path}"'
        if dependencies:
            dep_paths = '", "'.join(dependencies)
            ps_cmd += f' -DependencyPath @("{dep_paths}")'

        logger.info(f"Installing Winget via PowerShell: {ps_cmd}")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if res.returncode != 0:
            logger.warning(f"Add-AppxPackage stderr: {res.stderr.strip()}")
            if dependencies:
                logger.info("Retrying Add-AppxPackage without explicit dependencies...")
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", f'Add-AppxPackage -Path "{bundle_path}"'],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )

        cb(95, "Проверка установки Winget...")
        import time
        time.sleep(2)

        # 5. Проверяем результат
        if check_winget():
            ver = get_winget_version() or "v1.x"
            cb(100, f"Winget {ver} успешно установлен!")
            return True, ver
        else:
            err_msg = res.stderr.strip() if res.stderr else "Пакет установлен, но winget не обнаружен в PATH (может потребоваться перезапуск)."
            return False, err_msg

    except Exception as e:
        logger.error(f"Error installing Winget: {e}")
        return False, str(e)


def is_admin() -> bool:
    """Проверяет, запущен ли процесс с правами администратора."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False


def get_clean_env() -> dict[str, str]:
    """
    Возвращает копию os.environ, очищенную от внутренних переменных PyInstaller (_MEI, _PYI).
    Предотвращает загрязнение дочерних и системных процессов (например, explorer.exe).
    """
    env = os.environ.copy()
    keys_to_remove = [k for k in env if k.startswith("_PYI") or k.startswith("_MEI")]
    for k in keys_to_remove:
        env.pop(k, None)
    if "PATH" in env:
        paths = env["PATH"].split(os.pathsep)
        clean_paths = [p for p in paths if "_MEI" not in p]
        env["PATH"] = os.pathsep.join(clean_paths)
    return env


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
