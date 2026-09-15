"""
WinSetup — Модуль запуска установщиков.
Запускает скачанные установщики в интерактивном или тихом режиме.
"""

import logging
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.catalog import AppEntry

logger = logging.getLogger("WinSetup")


@dataclass
class InstallResult:
    """Результат установки."""
    app: AppEntry
    success: bool
    error: str = ""
    skipped: bool = False
    cancelled: bool = False


def get_exe_dir() -> Path:
    """Возвращает директорию расположения самой программы ZiablWinSetup."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def get_desktop_path() -> Path:
    """Возвращает актуальный путь к рабочему столу текущего пользователя (с учетом OneDrive / перемещения папок)."""
    # 1. Запрос через системный Win32 KnownFolder CSIDL_DESKTOPDIRECTORY (0x0010)
    try:
        import ctypes
        from ctypes import wintypes
        CSIDL_DESKTOPDIRECTORY = 0x0010
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buf) == 0:
            p = Path(buf.value)
            if p.exists():
                return p
    except Exception:
        pass

    # 2. Проверка OneDrive Desktop
    for env_var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(env_var)
        if od:
            p = Path(od) / "Desktop"
            if p.exists():
                return p

    # 3. Стандартный USERPROFILE\Desktop
    up = os.environ.get("USERPROFILE")
    if up:
        p = Path(up) / "Desktop"
        if p.exists():
            return p

    # 4. Path.home() / Desktop
    p = Path.home() / "Desktop"
    if p.exists():
        return p

    # 5. Папка рядом с программой
    return get_exe_dir()



def create_desktop_shortcut(
    target_path: Path,
    shortcut_name: str,
    working_dir: Path | None = None,
    icon_path: Path | None = None,
) -> Path | None:
    """Создаёт ярлык на рабочем столе пользователя."""
    try:
        desktop = get_desktop_path()
        if not shortcut_name.lower().endswith(".lnk"):
            shortcut_name += ".lnk"
        shortcut_file = desktop / shortcut_name

        work_dir = working_dir or target_path.parent
        target_str = str(target_path.resolve()).replace("'", "''")
        shortcut_str = str(shortcut_file.resolve()).replace("'", "''")
        work_dir_str = str(work_dir.resolve()).replace("'", "''")

        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_str}'); "
            f"$s.TargetPath = '{target_str}'; "
            f"$s.WorkingDirectory = '{work_dir_str}'; "
        )
        if icon_path and icon_path.exists():
            icon_str = str(icon_path.resolve()).replace("'", "''")
            ps_script += f"$s.IconLocation = '{icon_str}'; "
        ps_script += "$s.Save()"

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and shortcut_file.exists():
            logger.info(f"Created desktop shortcut: {shortcut_file} -> {target_path}")
            return shortcut_file
        else:
            logger.warning(f"Failed to create shortcut via PowerShell: {result.stderr}")
            return None
    except Exception as e:
        logger.warning(f"Error creating desktop shortcut: {e}")
        return None


def run_with_elevation(
    file_path: str | Path,
    args: list[str] | None = None,
    cwd: str | Path | None = None,
    on_handle_created=None,
) -> int:
    """
    Запускает исполняемый файл с правами администратора через Windows UAC диалог (verb='runas').
    Синхронно ожидает завершения процесса и возвращает код выхода.
    """
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NOASYNC = 0x00000100
    INFINITE = 0xFFFFFFFF

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    params_str = subprocess.list2cmdline(args) if args else ""
    cwd_str = str(cwd) if cwd else str(Path(file_path).parent)

    sei = SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = str(file_path)
    sei.lpParameters = params_str if params_str else None
    sei.lpDirectory = cwd_str
    sei.nShow = 1  # SW_SHOWNORMAL

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.GetLastError()
        if err == 1223:  # ERROR_CANCELLED: user declined UAC prompt
            raise PermissionError("UAC_CANCELLED")
        raise ctypes.WinError(err)

    hProcess = sei.hProcess
    if hProcess:
        if on_handle_created:
            try:
                on_handle_created(hProcess)
            except Exception:
                pass
        try:
            exit_code = wintypes.DWORD()
            while True:
                res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 300)
                if res != 0x00000102:  # not WAIT_TIMEOUT
                    break
            ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
            return int(exit_code.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(hProcess)
    return 0


class Installer:
    """Менеджер запуска установщиков."""

    def __init__(self, extract_path: Path | None = None):
        self._cancelled = False
        self._cancelled_apps: set[str] = set()
        self._active_processes: dict[str, subprocess.Popen] = {}
        self._active_handles: dict[str, int] = {}
        self._lock = threading.Lock()
        self.extract_path = extract_path or get_desktop_path()

    def cancel(self):
        """Отменяет дальнейшие и текущие установки."""
        with self._lock:
            self._cancelled = True
            for aid, proc in list(self._active_processes.items()):
                self._terminate_proc(proc)
            for aid, handle in list(self._active_handles.items()):
                self._terminate_handle(handle)

    def cancel_app(self, app_id: str):
        """Отменяет установку конкретного приложения и завершает его процесс."""
        with self._lock:
            self._cancelled_apps.add(app_id)
            proc = self._active_processes.get(app_id)
            if proc:
                self._terminate_proc(proc)
            handle = self._active_handles.get(app_id)
            if handle:
                self._terminate_handle(handle)

    def is_app_cancelled(self, app_id: str) -> bool:
        """Проверяет, отменена ли установка приложения."""
        with self._lock:
            return self._cancelled or (app_id in self._cancelled_apps)

    def reset(self):
        """Сбрасывает флаг отмены."""
        with self._lock:
            self._cancelled = False
            self._cancelled_apps.clear()
            self._active_processes.clear()
            self._active_handles.clear()

    def reset_app(self, app_id: str):
        """Сбрасывает флаг отмены для конкретного приложения."""
        with self._lock:
            self._cancelled_apps.discard(app_id)

    @staticmethod
    def _terminate_proc(proc: subprocess.Popen):
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

    @staticmethod
    def _terminate_handle(handle: int):
        try:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(handle, 1)
        except Exception:
            pass

    def run(self, app: AppEntry, installer_path: Path, silent: bool = False, as_admin: bool = False) -> InstallResult:
        """
        Запускает установщик.

        Args:
            app: Описание приложения
            installer_path: Путь к скачанному установщику
            silent: True для тихой установки, False для интерактивной
            as_admin: True для принудительного запуска с правами администратора (UAC)
        """
        if self.is_app_cancelled(app.id):
            return InstallResult(app=app, success=False, error="Отменено", skipped=True, cancelled=True)

        if not installer_path.exists():
            return InstallResult(
                app=app, success=False,
                error=f"Файл установщика не найден: {installer_path}"
            )

        ext = installer_path.suffix.lower()

        try:
            if ext == ".zip":
                return self._handle_zip(app, installer_path)
            elif ext == ".msi":
                return self._run_msi(app, installer_path, silent, as_admin=as_admin)
            elif ext in (".msix", ".msixbundle", ".appx", ".appxbundle"):
                return self._run_msix(app, installer_path)
            else:
                # .exe и всё остальное
                return self._run_exe(app, installer_path, silent, as_admin=as_admin)

        except Exception as e:
            logger.error(f"Error installing {app.name}: {e}")
            return InstallResult(app=app, success=False, error=str(e))

    def _run_exe(self, app: AppEntry, path: Path, silent: bool, as_admin: bool = False) -> InstallResult:
        """Запускает .exe установщик."""
        if self.is_app_cancelled(app.id):
            return InstallResult(app=app, success=False, error="Отменено", cancelled=True)

        args = app.silent_args if (silent and app.silent_args) else []

        def register_handle(h):
            with self._lock:
                self._active_handles[app.id] = h

        CANCEL_CODES = (1, 2, 5, 1223, 1602, -1073741510, 3221225786, -1978335216, -1978335188)

        if as_admin:
            logger.info(f"Running (as admin / UAC): {path} {' '.join(args)}")
            try:
                code = run_with_elevation(path, args, cwd=path.parent, on_handle_created=register_handle)
                if self.is_app_cancelled(app.id):
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                if code in (0, 3010):
                    return InstallResult(app=app, success=True)
                elif code in CANCEL_CODES:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                else:
                    return InstallResult(app=app, success=True, error=f"Код: {code}")
            except PermissionError:
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
            except Exception as e:
                return InstallResult(app=app, success=False, error=str(e))
            finally:
                with self._lock:
                    self._active_handles.pop(app.id, None)

        cmd = [str(path)] + args
        if silent and app.silent_args:
            logger.info(f"Running (silent): {' '.join(cmd)}")
        else:
            logger.info(f"Running (interactive): {cmd[0]}")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(path.parent),
            )
            with self._lock:
                self._active_processes[app.id] = process

            # Ждём завершения установки
            returncode = process.wait()
            with self._lock:
                self._active_processes.pop(app.id, None)

            if self.is_app_cancelled(app.id):
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")

            if returncode in (0, 3010):
                logger.info(f"Installation of {app.name} completed (exit code {returncode})")
                return InstallResult(app=app, success=True)
            elif returncode in CANCEL_CODES:
                logger.warning(f"Installation of {app.name} was cancelled by user (code {returncode})")
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
            else:
                logger.warning(f"Installation of {app.name} failed with code {returncode}")
                return InstallResult(
                    app=app, success=False, cancelled=False,
                    error=f"Установщик завершился с кодом {returncode}"
                )

        except OSError as e:
            # WinError 740: "Запрошенная операция требует повышения" (ERROR_ELEVATION_REQUIRED)
            # Автоматически повышаем права через Windows UAC диалог!
            if getattr(e, "winerror", None) == 740 or "elevation" in str(e).lower():
                logger.info(f"WinError 740 detected for {app.name}. Automatically elevating via UAC...")
                try:
                    code = run_with_elevation(path, args, cwd=path.parent, on_handle_created=register_handle)
                    if self.is_app_cancelled(app.id):
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    if code in (0, 3010):
                        return InstallResult(app=app, success=True)
                    elif code in CANCEL_CODES:
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    else:
                        return InstallResult(app=app, success=False, cancelled=False, error=f"Код: {code}")
                except PermissionError:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
                except Exception as ex:
                    return InstallResult(app=app, success=False, error=str(ex))
                finally:
                    with self._lock:
                        self._active_handles.pop(app.id, None)
            return InstallResult(app=app, success=False, error=str(e))
        finally:
            with self._lock:
                self._active_processes.pop(app.id, None)

    def _run_msi(self, app: AppEntry, path: Path, silent: bool, as_admin: bool = False) -> InstallResult:
        """Запускает .msi установщик через msiexec."""
        if self.is_app_cancelled(app.id):
            return InstallResult(app=app, success=False, error="Отменено", cancelled=True)

        args = ["/i", str(path)]
        if silent:
            args.extend(["/quiet", "/norestart"])

        def register_handle(h):
            with self._lock:
                self._active_handles[app.id] = h

        CANCEL_CODES = (1, 2, 5, 1223, 1602, -1073741510, 3221225786, -1978335216, -1978335188)

        if as_admin:
            logger.info(f"Running MSI as admin: msiexec {' '.join(args)}")
            try:
                code = run_with_elevation("msiexec.exe", args, cwd=path.parent, on_handle_created=register_handle)
                if self.is_app_cancelled(app.id):
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                if code in (0, 3010):
                    return InstallResult(app=app, success=True)
                elif code in CANCEL_CODES:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                return InstallResult(app=app, success=False, error=f"MSI код: {code}")
            except PermissionError:
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
            except Exception as e:
                return InstallResult(app=app, success=False, error=str(e))
            finally:
                with self._lock:
                    self._active_handles.pop(app.id, None)

        cmd = ["msiexec"] + args
        if silent:
            logger.info(f"Running MSI (silent): {' '.join(cmd)}")
        else:
            logger.info(f"Running MSI (interactive): {' '.join(cmd)}")

        try:
            process = subprocess.Popen(cmd)
            with self._lock:
                self._active_processes[app.id] = process

            returncode = process.wait()
            with self._lock:
                self._active_processes.pop(app.id, None)

            if self.is_app_cancelled(app.id):
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")

            if returncode in (0, 3010):
                logger.info(f"MSI installation of {app.name} completed")
                return InstallResult(app=app, success=True)
            elif returncode in CANCEL_CODES:
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
            else:
                return InstallResult(
                    app=app, success=False, cancelled=False,
                    error=f"MSI завершился с кодом {returncode}"
                )

        except OSError as e:
            if getattr(e, "winerror", None) == 740 or "elevation" in str(e).lower():
                logger.info(f"WinError 740 for MSI {app.name}. Elevating via UAC...")
                try:
                    code = run_with_elevation("msiexec.exe", args, cwd=path.parent, on_handle_created=register_handle)
                    if self.is_app_cancelled(app.id):
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    if code in (0, 3010):
                        return InstallResult(app=app, success=True)
                    elif code in CANCEL_CODES:
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    return InstallResult(app=app, success=False, error=f"MSI код: {code}")
                except PermissionError:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
                except Exception as ex:
                    return InstallResult(app=app, success=False, error=str(ex))
                finally:
                    with self._lock:
                        self._active_handles.pop(app.id, None)
            return InstallResult(app=app, success=False, error=str(e))
        except Exception as e:
            return InstallResult(app=app, success=False, error=str(e))
        finally:
            with self._lock:
                self._active_processes.pop(app.id, None)

    def _run_msix(self, app: AppEntry, path: Path) -> InstallResult:
        """Устанавливает .msix/.appx пакет через Add-AppxPackage."""
        try:
            cmd = [
                "powershell", "-Command",
                f'Add-AppxPackage -Path "{path}"'
            ]
            logger.info(f"Installing MSIX: {path.name}")

            process = subprocess.Popen(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _, stderr = process.communicate()

            if process.returncode == 0:
                logger.info(f"MSIX installation of {app.name} completed")
                return InstallResult(app=app, success=True)
            else:
                return InstallResult(
                    app=app, success=False,
                    error=f"MSIX ошибка: {stderr.strip()}"
                )

        except Exception as e:
            return InstallResult(app=app, success=False, error=str(e))

    def _handle_zip(self, app: AppEntry, path: Path) -> InstallResult:
        """Распаковывает ZIP-архив в настраиваемый путь (по умолчанию — рабочий стол)."""
        try:
            # Имя папки = имя архива без расширения
            folder_name = path.stem
            extract_dir = self.extract_path / folder_name
            extract_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Extracting {path.name} to {extract_dir}")

            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(extract_dir)

            logger.info(f"Extracted {app.name} to {extract_dir}")

            # Ищем исполняемые файлы или батники для создания ярлыка на рабочем столе
            bat_files = list(extract_dir.rglob("*.bat")) + list(extract_dir.rglob("*.cmd"))
            exe_files = list(extract_dir.rglob("*.exe"))

            target_to_link = None
            if bat_files:
                # Ищем наиболее релевантные скрипты запуска (особенно для Zapret)
                priority_names = ["general", "discord", "service_install", "start", "run"]
                for p_name in priority_names:
                    for b in bat_files:
                        if p_name in b.stem.lower():
                            target_to_link = b
                            break
                    if target_to_link:
                        break
                if not target_to_link:
                    target_to_link = bat_files[0]
            elif exe_files:
                target_to_link = exe_files[0]

            shortcut_msg = ""
            if target_to_link:
                shortcut_name = f"{app.name} ({target_to_link.stem})" if len(target_to_link.stem) < 25 else app.name
                created = create_desktop_shortcut(
                    target_to_link,
                    shortcut_name,
                    working_dir=target_to_link.parent,
                )
                if created:
                    shortcut_msg = f"  (Ярлык: {created.name})"

            return InstallResult(
                app=app,
                success=True,
                error=f"{extract_dir}{shortcut_msg}",
            )

        except zipfile.BadZipFile:
            return InstallResult(app=app, success=False, error="Повреждённый ZIP-архив")
        except Exception as e:
            return InstallResult(app=app, success=False, error=str(e))
