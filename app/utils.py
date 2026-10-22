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

logger = logging.getLogger("WinSetup")


def ensure_winget_in_path():
    """Добавляет директории WindowsApps в os.environ['PATH'], если их там нет."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        apps_dir = str(Path(localappdata) / "Microsoft" / "WindowsApps")
        if os.path.isdir(apps_dir):
            current_path = os.environ.get("PATH", "")
            if apps_dir.lower() not in current_path.lower():
                os.environ["PATH"] = f"{apps_dir};{current_path}"

    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    windows_apps = Path(program_files) / "WindowsApps"
    if windows_apps.is_dir():
        try:
            for p in windows_apps.glob("Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe"):
                if (p / "winget.exe").is_file():
                    p_str = str(p)
                    current_path = os.environ.get("PATH", "")
                    if p_str.lower() not in current_path.lower():
                        os.environ["PATH"] = f"{p_str};{current_path}"
                    break
        except Exception:
            pass


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


def open_winget_store() -> tuple[bool, str]:
    """
    Открывает страницу App Installer в приложении Microsoft Store.
    Если Microsoft Store отсутствует в системе, автоматически открывает
    официальную веб-страницу в браузере по умолчанию.
    Возвращает (success: bool, opened_via: str) где opened_via = 'store_app' | 'browser' | error text.
    """
    import webbrowser
    web_url = "https://apps.microsoft.com/detail/9nblggh4nns1"

    # Сначала проверяем, зарегистрирован ли протокол ms-windows-store
    try:
        import winreg
        has_protocol = False
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "ms-windows-store"):
                has_protocol = True
        except OSError:
            has_protocol = False

        if has_protocol:
            try:
                os.startfile("ms-windows-store://pdp/?productid=9NBLGGH4NNS1")
                logger.info("Successfully requested ms-windows-store protocol")
                return True, "store_app"
            except Exception as store_err:
                logger.warning(f"Failed to start ms-windows-store protocol despite registry entry: {store_err}")
    except Exception as e:
        logger.warning(f"Error checking ms-windows-store protocol: {e}")

    # Fallback: открытие веб-страницы в браузере
    try:
        logger.info(f"Opening browser fallback for App Installer: {web_url}")
        webbrowser.open(web_url)
        return True, "browser"
    except Exception as e:
        logger.error(f"Failed to open browser fallback: {e}")
        return False, str(e)


def _download_file(
    urls: list[str],
    dest_path: Path,
    progress_cb,
    start_pct: int,
    end_pct: int,
    label: str,
    min_valid_size: int = 1000,
) -> bool:
    """
    Надёжно скачивает файл по списку fallback-URL во временный файл .part
    с отображением прогресса в МБ и процентах.
    """
    import socket
    import urllib.request
    socket.setdefaulttimeout(45)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    part_path = dest_path.with_name(dest_path.name + ".part")

    for url in urls:
        try:
            logger.info(f"Downloading {label} from {url}...")
            if part_path.exists():
                try:
                    part_path.unlink()
                except Exception:
                    pass

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                total_size = resp.headers.get("Content-Length")
                total_size = int(total_size) if total_size else None
                downloaded = 0
                block_size = 131072  # 128 KB chunks

                with open(part_path, "wb") as f:
                    while True:
                        chunk = resp.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size and total_size > 0:
                            ratio = min(1.0, downloaded / total_size)
                            pct = int(start_pct + ratio * (end_pct - start_pct))
                            dl_mb = downloaded / (1024 * 1024)
                            tot_mb = total_size / (1024 * 1024)
                            progress_cb(pct, f"{label}: {dl_mb:.1f} / {tot_mb:.1f} МБ ({int(ratio * 100)}%)")
                        else:
                            dl_mb = downloaded / (1024 * 1024)
                            progress_cb(start_pct, f"{label}: {dl_mb:.1f} МБ")

            if part_path.exists() and part_path.stat().st_size >= min_valid_size:
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except Exception:
                        pass
                part_path.replace(dest_path)
                logger.info(f"Successfully downloaded {label} ({dest_path.stat().st_size} bytes)")
                return True
            else:
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Download attempt failed for {url}: {e}")
            if part_path.exists():
                try:
                    part_path.unlink()
                except Exception:
                    pass
            continue

    return False


def install_winget(progress_cb=None) -> tuple[bool, str]:
    """
    Автоматически скачивает и устанавливает официальный пакет Winget (DesktopAppInstaller).
    Возвращает (success: bool, message_or_version: str).
    """
    cb = progress_cb or (lambda *_: None)

    try:
        cb(5, "Подготовка к загрузке Winget...")
        temp_dir = Path(tempfile.gettempdir()) / "WinSetup_Winget"
        temp_dir.mkdir(parents=True, exist_ok=True)

        bundle_path = temp_dir / "DesktopAppInstaller.msixbundle"
        vclibs_path = temp_dir / "Microsoft.VCLibs.x64.14.00.Desktop.appx"
        vclibs_x86_path = temp_dir / "Microsoft.VCLibs.x86.14.00.Desktop.appx"
        xaml_path = temp_dir / "Microsoft.UI.Xaml.2.8.x64.appx"

        # 0. Убеждаемся, что служба AppXSvc запущена
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "Start-Service AppXSvc -ErrorAction SilentlyContinue"],
                capture_output=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

        # 1. Скачивание основного пакета (msixbundle ~217 МБ)
        winget_urls = [
            "https://aka.ms/getwinget",
            "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle",
        ]
        cb(10, "Скачивание Microsoft.DesktopAppInstaller (~217 МБ)...")
        # Если файл есть, но поврежден или усечен (< 150 МБ), удаляем его
        if bundle_path.exists() and bundle_path.stat().st_size < 150_000_000:
            try:
                bundle_path.unlink()
            except Exception:
                pass

        if not bundle_path.exists() or bundle_path.stat().st_size < 150_000_000:
            ok = _download_file(
                winget_urls,
                bundle_path,
                cb,
                start_pct=10,
                end_pct=70,
                label="Скачивание Winget",
                min_valid_size=150_000_000,
            )
            if not ok:
                return False, "Не удалось скачать пакет DesktopAppInstaller. Проверьте интернет или воспользуйтесь Microsoft Store / ссылкой в браузере."

        # 2. Скачивание зависимостей (VCLibs x64, VCLibs x86 и UI.Xaml)
        dependencies = []

        # VCLibs x64 (~6.7 MB)
        vclibs_urls = [
            "https://aka.ms/Microsoft.VCLibs.x64.14.00.Desktop.appx",
            "https://download.microsoft.com/download/4/7/c/47c6134b-d61f-4024-83bd-b9c9ea951c25/Microsoft.VCLibs.x64.14.00.Desktop.appx",
        ]
        if not vclibs_path.exists() or vclibs_path.stat().st_size < 100_000:
            cb(72, "Скачивание зависимостей (VCLibs x64)...")
            _download_file(
                vclibs_urls,
                vclibs_path,
                cb,
                start_pct=72,
                end_pct=76,
                label="Скачивание VCLibs x64",
                min_valid_size=100_000,
            )
        if vclibs_path.exists() and vclibs_path.stat().st_size > 100_000:
            dependencies.append(str(vclibs_path))

        # VCLibs x86 (~5.9 MB)
        vclibs_x86_urls = [
            "https://aka.ms/Microsoft.VCLibs.x86.14.00.Desktop.appx",
            "https://download.microsoft.com/download/4/7/c/47c6134b-d61f-4024-83bd-b9c9ea951c25/Microsoft.VCLibs.x86.14.00.Desktop.appx",
        ]
        if not vclibs_x86_path.exists() or vclibs_x86_path.stat().st_size < 100_000:
            cb(76, "Скачивание зависимостей (VCLibs x86)...")
            _download_file(
                vclibs_x86_urls,
                vclibs_x86_path,
                cb,
                start_pct=76,
                end_pct=80,
                label="Скачивание VCLibs x86",
                min_valid_size=100_000,
            )
        if vclibs_x86_path.exists() and vclibs_x86_path.stat().st_size > 100_000:
            dependencies.append(str(vclibs_x86_path))

        # UI.Xaml 2.8 (~5.1 MB)
        xaml_urls = [
            "https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx",
            "https://aka.ms/Microsoft.UI.Xaml.2.8.x64.appx",
        ]
        if not xaml_path.exists() or xaml_path.stat().st_size < 100_000:
            cb(80, "Скачивание зависимостей (UI.Xaml)...")
            _download_file(
                xaml_urls,
                xaml_path,
                cb,
                start_pct=80,
                end_pct=84,
                label="Скачивание UI.Xaml",
                min_valid_size=100_000,
            )
        if xaml_path.exists() and xaml_path.stat().st_size > 100_000:
            dependencies.append(str(xaml_path))

        # 3. Установка зависимостей по отдельности
        cb(85, "Установка зависимостей в систему...")
        for dep in dependencies:
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", f'Add-AppxPackage -Path "{dep}" -ErrorAction SilentlyContinue'],
                    capture_output=True,
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as e:
                logger.warning(f"Note installing dependency {dep}: {e}")

        # 4. Установка основного пакета Winget
        cb(88, "Установка Windows Package Manager...")
        ps_cmd = f'Add-AppxPackage -Path "{bundle_path}"'
        if dependencies:
            dep_paths = '", "'.join(dependencies)
            ps_cmd += f' -DependencyPath @("{dep_paths}")'

        logger.info(f"Installing Winget via PowerShell: {ps_cmd}")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if res.returncode != 0:
            logger.warning(f"Add-AppxPackage with dependencies failed: {res.stderr.strip()}")
            logger.info("Retrying Add-AppxPackage directly...")
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", f'Add-AppxPackage -Path "{bundle_path}"'],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

        cb(94, "Проверка готовности Winget...")
        import time
        time.sleep(2)

        ensure_winget_in_path()

        # 5. Проверяем результат
        if check_winget():
            ver = get_winget_version() or "v1.x"
            cb(100, f"Winget {ver} успешно установлен!")
            return True, ver
        else:
            raw_err = res.stderr.strip() if res.stderr else ""
            if "0x80070422" in raw_err or "disabled" in raw_err.lower():
                err_msg = "Служба развёртывания AppX (AppXSvc) отключена в Windows. Включите службу в services.msc."
            elif raw_err:
                err_msg = f"Ошибка PowerShell: {raw_err[:200]}"
            else:
                err_msg = "Пакет установлен, но winget пока не обнаружен в PATH (может потребоваться перезапуск приложения или системы)."
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


def get_file_version(filepath: str | Path) -> str | None:
    """Извлекает версию исполняемого файла PE из ресурсов VersionInfo (Windows)."""
    try:
        from ctypes import wintypes
        path_str = str(filepath)
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path_str, None)
        if not size:
            return None
        res = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path_str, None, size, res):
            return None
        uLen = wintypes.UINT()
        lpBuffer = ctypes.c_void_p()
        if ctypes.windll.version.VerQueryValueW(res, "\\", ctypes.byref(lpBuffer), ctypes.byref(uLen)):
            class VS_FIXEDFILEINFO(ctypes.Structure):
                _fields_ = [
                    ("dwSignature", wintypes.DWORD),
                    ("dwStrucVersion", wintypes.DWORD),
                    ("dwFileVersionMS", wintypes.DWORD),
                    ("dwFileVersionLS", wintypes.DWORD),
                ]
            ffi = VS_FIXEDFILEINFO.from_address(lpBuffer.value)
            major = ffi.dwFileVersionMS >> 16
            minor = ffi.dwFileVersionMS & 0xFFFF
            build = ffi.dwFileVersionLS >> 16
            patch = ffi.dwFileVersionLS & 0xFFFF
            if patch != 0:
                return f"{major}.{minor}.{build}.{patch}"
            elif build != 0:
                return f"{major}.{minor}.{build}"
            return f"{major}.{minor}"
    except Exception:
        pass
    return None


def get_user_documents_dir() -> Path:
    """
    Возвращает действительный путь к папке 'Документы' текущего пользователя
    с учетом возможного перенаправления в OneDrive или изменения реестра Windows.
    """
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            ) as key:
                val, _ = winreg.QueryValueEx(key, "Personal")
                expanded = os.path.expandvars(str(val))
                if os.path.isdir(expanded):
                    return Path(expanded)
        except Exception:
            pass

        for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            od = os.environ.get(var)
            if od:
                od_docs = Path(od) / "Documents"
                if od_docs.is_dir():
                    return od_docs

    profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")
    fallback = Path(profile) / "Documents"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
