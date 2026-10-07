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
import time
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


def get_locking_processes(file_paths: list[Path | str]) -> list[str]:
    """
    Использует Windows Restart Manager API для быстрого определения процессов,
    блокирующих указанные файлы (например, obs-virtualcam-module64.dll).
    """
    try:
        import ctypes
        from ctypes import wintypes
        rm = ctypes.WinDLL("rstrtmgr", use_last_error=True)
    except Exception:
        return []

    CCH_RM_SESSION_KEY = 32
    CCH_RM_MAX_APP_NAME = 255
    CCH_RM_MAX_SVC_NAME = 63

    class RM_UNIQUE_PROCESS(ctypes.Structure):
        _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]

    class RM_PROCESS_INFO(ctypes.Structure):
        _fields_ = [
            ("Process", RM_UNIQUE_PROCESS),
            ("strAppName", wintypes.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
            ("strServiceShortName", wintypes.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
            ("ApplicationType", wintypes.UINT),
            ("AppStatus", wintypes.ULONG),
            ("TSSessionId", wintypes.DWORD),
            ("bRestartable", wintypes.BOOL)
        ]

    existing = [str(Path(p).resolve()) for p in file_paths if Path(p).exists()]
    if not existing:
        return []

    session_handle = wintypes.DWORD()
    session_key = (wintypes.WCHAR * (CCH_RM_SESSION_KEY + 1))()

    res = rm.RmStartSession(ctypes.byref(session_handle), 0, session_key)
    if res != 0:
        return []

    try:
        arr = (wintypes.LPCWSTR * len(existing))(*existing)
        res = rm.RmRegisterResources(session_handle, len(existing), arr, 0, None, 0, None)
        if res != 0:
            return []

        pnProcInfoNeeded = wintypes.UINT(0)
        pnProcInfo = wintypes.UINT(0)
        pRebootReasons = wintypes.DWORD(0)

        rm.RmGetList(session_handle, ctypes.byref(pnProcInfoNeeded), ctypes.byref(pnProcInfo), None, ctypes.byref(pRebootReasons))
        if pnProcInfoNeeded.value > 0:
            pnProcInfo.value = pnProcInfoNeeded.value
            proc_info_array = (RM_PROCESS_INFO * pnProcInfo.value)()
            res = rm.RmGetList(session_handle, ctypes.byref(pnProcInfoNeeded), ctypes.byref(pnProcInfo), proc_info_array, ctypes.byref(pRebootReasons))
            if res == 0:
                names = []
                for i in range(pnProcInfo.value):
                    name = proc_info_array[i].strAppName
                    if name and name not in names:
                        names.append(name)
                return names
    except Exception:
        pass
    finally:
        try:
            rm.RmEndSession(session_handle)
        except Exception:
            pass
    return []


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
        self.extract_path = extract_path or get_exe_dir()

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

    def run(self, app: AppEntry, installer_path: Path, silent: bool = False, as_admin: bool = False, version: str = "") -> InstallResult:
        """
        Запускает установщик.

        Args:
            app: Описание приложения
            installer_path: Путь к скачанному установщику
            silent: True для тихой установки, False для интерактивной
            as_admin: True для принудительного запуска с правами администратора (UAC)
            version: Версия приложения (для сохранения в метаданных портативных программ)
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
                return self._handle_zip(app, installer_path, version=version)
            elif ext == ".msi":
                return self._run_msi(app, installer_path, silent, as_admin=as_admin)
            elif ext in (".msix", ".msixbundle", ".appx", ".appxbundle"):
                return self._run_msix(app, installer_path)
            elif app.installer_type == "portable" or self.is_portable_executable(app, installer_path):
                # Если в системе уже установлен GPU-Z в Program Files, обновляем установленную программу на месте!
                if app.id == "gpuz" and (Path(r"C:\Program Files (x86)\GPU-Z\GPU-Z.exe").exists() or Path(r"C:\Program Files\GPU-Z\GPU-Z.exe").exists()):
                    logger.info("Found installed GPU-Z in Program Files. Running in-place silent installer update...")
                    return self._run_exe(app, installer_path, silent=True, as_admin=True)
                return self._handle_portable(app, installer_path, launch=(not silent), version=version)
            else:
                # .exe и всё остальное
                return self._run_exe(app, installer_path, silent, as_admin=as_admin)

        except Exception as e:
            logger.error(f"Error installing {app.name}: {e}")
            return InstallResult(app=app, success=False, error=str(e))

    def _format_installer_error(self, app: AppEntry, code: int, installer_path: Path | None = None) -> str:
        """Расшифровывает коды возврата установщиков в понятные пользователю сообщения."""
        if code == 6:
            # Код 6 характерен для NSIS/OBS Studio: packageInUseByApplication
            files_to_check = []
            if app.id in ("obs", "obs-studio"):
                files_to_check = [
                    Path(r"C:\Program Files\obs-studio\data\obs-plugins\win-dshow\obs-virtualcam-module64.dll"),
                    Path(r"C:\Program Files\obs-studio\data\obs-plugins\win-dshow\obs-virtualcam-module32.dll"),
                    Path(r"C:\Program Files\obs-studio\data\obs-plugins\win-capture\graphics-hook64.dll"),
                    Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"),
                ]
            locking = get_locking_processes(files_to_check) if files_to_check else []
            if locking:
                procs_str = ", ".join(locking)
                return f"Файлы программы (виртуальная камера) заняты: {procs_str} (Код 6). Закройте эти программы и повторите попытку."
            return "Файлы программы (виртуальная камера или хуки захвата) заняты другим приложением, например Chrome или Discord (Код 6). Закройте их перед обновлением."

        elif code == 1618:
            return "Уже выполняется другая установка Windows Installer (msiexec). Дождитесь её окончания (Код 1618)."
        elif code == 1603:
            return "Ошибка Windows Installer (Код 1603): файлы заблокированы или недостаточно прав."
        elif code == 1602:
            return "Установка отменена пользователем (Код 1602)."
        elif code == 1223:
            return "Установка отменена в окне контроля учетных записей (UAC)."
        elif code == 5:
            return "Отказано в доступе (Код 5). Запустите программу от имени администратора или проверьте антивирус."
        elif code in (11341828, 11341829, 0xAD1004, 0xAD1005):
            return f"Ошибка AnyDesk (Код {code}): требуются права администратора или служба AnyDesk заблокирована."
        elif code in (1, 2):
            return f"Установщик прерван или сообщил об ошибке (Код {code})."
        else:
            return f"Код: {code}"

    def _run_exe(self, app: AppEntry, path: Path, silent: bool, as_admin: bool = False) -> InstallResult:
        """Запускает .exe установщик."""
        if self.is_app_cancelled(app.id):
            return InstallResult(app=app, success=False, error="Отменено", cancelled=True)

        args = app.silent_args if (silent and app.silent_args) else []

        # Перед установкой/обновлением завершаем активные процессы программы,
        # чтобы установщик не завершился ошибкой блокировки (например, OBS Studio obs64.exe)
        if silent:
            self._terminate_app_processes(app, src_path=path)

        def register_handle(h):
            with self._lock:
                self._active_handles[app.id] = h

        CANCEL_CODES = (1, 2, 5, 1223, 1602, -1073741510, 3221225786, -1978335216, -1978335188)
        ELEVATION_CODES = (5, 11341828, 11341829, 0xAD1004, 0xAD1005)

        is_obs = app.id in ("obs", "obs-studio")
        needs_admin = as_admin or is_obs or app.id in ("anydesk", "gpuz", "python") or any("program files" in str(a).lower() for a in args)

        if needs_admin:
            logger.info(f"Running (as admin / UAC): {path} {' '.join(args)}")
            obs_cmd_path = None
            try:
                if is_obs:
                    # OBS Studio использует виртуальную камеру (obs-virtualcam-module64.dll),
                    # которую загружают Electron (Antigravity), браузеры и мессенджеры.
                    # Создаем временный CMD-раннер с правами администратора, который безопасно
                    # открепляет DirectShow фильтр и переименовывает заблокированные DLL в .old.
                    # После этого NSIS создает новый файл без конфликтов и не падает с Кодом 6.
                    import tempfile
                    import time
                    obs_runner_content = f"""@echo off
set "DSHOW_DIR=C:\\Program Files\\obs-studio\\data\\obs-plugins\\win-dshow"
if exist "%DSHOW_DIR%\\obs-virtualcam-module64.dll" (
    regsvr32.exe /u /s "%DSHOW_DIR%\\obs-virtualcam-module64.dll"
    if exist "%DSHOW_DIR%\\obs-virtualcam-module64.dll.old" del /f /q "%DSHOW_DIR%\\obs-virtualcam-module64.dll.old" 2>nul
    move /y "%DSHOW_DIR%\\obs-virtualcam-module64.dll" "%DSHOW_DIR%\\obs-virtualcam-module64.dll.old" 2>nul
)
if exist "%DSHOW_DIR%\\obs-virtualcam-module32.dll" (
    regsvr32.exe /u /s "%DSHOW_DIR%\\obs-virtualcam-module32.dll"
    if exist "%DSHOW_DIR%\\obs-virtualcam-module32.dll.old" del /f /q "%DSHOW_DIR%\\obs-virtualcam-module32.dll.old" 2>nul
    move /y "%DSHOW_DIR%\\obs-virtualcam-module32.dll" "%DSHOW_DIR%\\obs-virtualcam-module32.dll.old" 2>nul
)
"{path}" {subprocess.list2cmdline(args)}
exit /b %errorlevel%
"""
                    temp_dir = Path(tempfile.gettempdir())
                    obs_cmd_path = temp_dir / f"obs_elevated_runner_{int(time.time())}.cmd"
                    obs_cmd_path.write_text(obs_runner_content, encoding="ascii")
                    code = run_with_elevation("cmd.exe", ["/c", str(obs_cmd_path)], cwd=path.parent, on_handle_created=register_handle)
                else:
                    code = run_with_elevation(path, args, cwd=path.parent, on_handle_created=register_handle)

                if self.is_app_cancelled(app.id):
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                if code in (0, 3010):
                    if app.id == "anydesk":
                        try:
                            subprocess.run(["net", "start", "AnyDesk"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        except Exception:
                            pass
                    if is_obs:
                        # Перерегистрируем новую установленную виртуальную камеру OBS
                        new_vcam = Path(r"C:\Program Files\obs-studio\data\obs-plugins\win-dshow\obs-virtualcam-module64.dll")
                        if new_vcam.exists():
                            try:
                                subprocess.run(["regsvr32.exe", "/i", "/s", str(new_vcam)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                            except Exception:
                                pass
                    return InstallResult(app=app, success=True)
                elif code in CANCEL_CODES:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                else:
                    return InstallResult(
                        app=app, success=False, cancelled=False,
                        error=self._format_installer_error(app, code, path)
                    )
            except PermissionError:
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
            except Exception as e:
                return InstallResult(app=app, success=False, error=str(e))
            finally:
                if obs_cmd_path and obs_cmd_path.exists():
                    try:
                        obs_cmd_path.unlink(missing_ok=True)
                    except Exception:
                        pass
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
                if app.id == "anydesk":
                    try:
                        subprocess.run(["net", "start", "AnyDesk"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    except Exception:
                        pass
                logger.info(f"Installation of {app.name} completed (exit code {returncode})")
                return InstallResult(app=app, success=True)
            elif returncode in ELEVATION_CODES:
                logger.info(f"Installation of {app.name} exited with code {returncode} (elevation required). Retrying with UAC elevation...")
                try:
                    code = run_with_elevation(path, args, cwd=path.parent, on_handle_created=register_handle)
                    if self.is_app_cancelled(app.id):
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    if code in (0, 3010):
                        if app.id == "anydesk":
                            try:
                                subprocess.run(["net", "start", "AnyDesk"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                            except Exception:
                                pass
                        return InstallResult(app=app, success=True)
                    elif code in CANCEL_CODES:
                        return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
                    else:
                        return InstallResult(
                            app=app, success=False, cancelled=False,
                            error=self._format_installer_error(app, code, path)
                        )
                except PermissionError:
                    return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена в окне UAC")
                except Exception as ex:
                    return InstallResult(app=app, success=False, error=str(ex))
                finally:
                    with self._lock:
                        self._active_handles.pop(app.id, None)
            elif returncode in CANCEL_CODES:
                logger.warning(f"Installation of {app.name} was cancelled by user (code {returncode})")
                return InstallResult(app=app, success=False, cancelled=True, error="Установка отменена пользователем")
            else:
                logger.warning(f"Installation of {app.name} failed with code {returncode}")
                return InstallResult(
                    app=app, success=False, cancelled=False,
                    error=self._format_installer_error(app, returncode, path)
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
                        return InstallResult(
                            app=app, success=False, cancelled=False,
                            error=self._format_installer_error(app, code, path)
                        )
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
            self._terminate_app_processes(app, src_path=path)

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
                return InstallResult(app=app, success=False, error=self._format_installer_error(app, code, path))
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
                    error=self._format_installer_error(app, returncode, path)
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
                    return InstallResult(app=app, success=False, error=self._format_installer_error(app, code, path))
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

    @staticmethod
    def _terminate_app_processes(app: AppEntry, dest_exe: Path | None = None, src_path: Path | None = None, dest_dir: Path | None = None):
        """
        Принудительно закрывает запущенные процессы приложения перед обновлением или заменой файлов,
        предотвращая ошибку WinError 32 (файл заблокирован другим процессом).
        """
        names_to_kill = set()
        if dest_exe:
            names_to_kill.add(dest_exe.name)
            names_to_kill.add(f"{dest_exe.stem}.exe")
        names_to_kill.add(f"{app.name}.exe")
        names_to_kill.add(f"{app.id}.exe")

        if app.id == "anydesk":
            try:
                subprocess.run(["net", "stop", "AnyDesk"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

        # Дополнительные известные имена исполняемых файлов для портативных утилит и программ
        known_aliases = {
            "anydesk": ["AnyDesk.exe"],
            "tgwsproxy": ["tg-ws-proxy.exe", "tg_ws_proxy.exe", "tg-ws-proxy-windows.exe", "winws.exe"],
            "gpuz": ["GPU-Z.exe", "TechPowerUp GPU-Z.exe"],
            "operaproxy": ["opera-proxy.exe", "opera-proxy-windows-amd64.exe", "Opera Proxy (Alexey71).exe"],
            "zapret": ["winws.exe", "zapret.exe", "blockcheck.exe"],
            "obs": ["obs64.exe", "obs32.exe", "obs.exe", "obs-browser-page.exe", "obs-ffmpeg-mux.exe"],
            "obs-studio": ["obs64.exe", "obs32.exe", "obs.exe", "obs-browser-page.exe", "obs-ffmpeg-mux.exe"],
            "obsidian": ["Obsidian.exe"],
            "telegram": ["Telegram.exe"],
            "discord": ["Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe"],
            "steam": ["steam.exe", "steamwebhelper.exe"],
            "vscode": ["Code.exe"],
            "vlc": ["vlc.exe"],
            "git": ["git.exe", "git-bash.exe", "bash.exe"],
            "todoist": ["Todoist.exe"],
            "chrome": ["chrome.exe"],
            "firefox": ["firefox.exe"],
            "edge": ["msedge.exe"],
            "qbittorrent": ["qbittorrent.exe"],
            "7zip": ["7zFM.exe", "7zG.exe", "7z.exe"],
            "notepadplusplus": ["notepad++.exe"],
            "sharex": ["ShareX.exe"],
        }
        for alias in known_aliases.get(app.id, []):
            names_to_kill.add(alias)

        for proc_name in names_to_kill:
            if not proc_name.lower().endswith(".exe"):
                proc_name += ".exe"
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/IM", proc_name],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass

        if dest_dir and dest_dir.exists():
            for exe in dest_dir.glob("*.exe"):
                if not exe.name.endswith(".old"):
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/IM", exe.name],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    except Exception:
                        pass

        # Небольшая пауза, чтобы Windows освободила дескрипторы файлов
        time.sleep(0.25)

    def _handle_zip(self, app: AppEntry, path: Path, version: str = "") -> InstallResult:
        """Распаковывает ZIP-архив в настраиваемый путь (по умолчанию — рабочий стол)."""
        try:
            # Имя папки = имя архива без расширения
            folder_name = path.stem
            extract_dir = self.extract_path / folder_name
            extract_dir.mkdir(parents=True, exist_ok=True)

            self._terminate_app_processes(app, dest_dir=extract_dir)

            logger.info(f"Extracting {path.name} to {extract_dir}")

            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(extract_dir)

            logger.info(f"Extracted {app.name} to {extract_dir}")

            if version:
                try:
                    (extract_dir / ".version").write_text(version.strip(), encoding="utf-8")
                except Exception:
                    pass

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

    def is_portable_executable(self, app: AppEntry, path: Path) -> bool:
        """
        Определяет, является ли исполняемый файл портативной утилитой,
        а не традиционным инсталлятором (NSIS, Inno Setup, WiX и др.).
        """
        if app.installer_type == "portable":
            return True
        if app.installer_type in ("zip", "msi") or path.suffix.lower() in (".msi", ".zip", ".msix", ".appx"):
            return False

        # Если заданы аргументы для тихой установки — это явно инсталлятор
        if app.silent_args:
            return False

        # Проверка ключевых слов в имени файла
        stem = path.stem.lower()
        if any(w in stem for w in ("setup", "install", "installer", "update", "patch")):
            return False

        # Эвристическая проверка PE сигнатур инсталляторов
        try:
            with open(path, "rb") as f:
                header = f.read(1024 * 256)
            installer_sigs = [
                b"Inno Setup", b"NullsoftInst", b"InstallShield",
                b"WiX.Bootstrapper", b"Wise Installation", b"Advanced Installer"
            ]
            if any(sig in header for sig in installer_sigs):
                return False
        except Exception:
            pass

        return True

    def _handle_portable(self, app: AppEntry, path: Path, launch: bool = True, version: str = "") -> InstallResult:
        """
        Обрабатывает запуск и размещение портативной программы:
        1. Завершает активные процессы утилиты в диспетчере задач, если они запущены.
        2. Копирует .exe в директорию пользователя (extract_path / app.name).
        3. Сохраняет файл версии .version для отслеживания обновлений.
        4. Создает или обновляет ярлык на Рабочем столе.
        5. При необходимости (если launch=True) запускает новую версию.
        """
        try:
            dest_dir = self.extract_path / app.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_exe = dest_dir / f"{app.name}.exe"

            logger.info(f"Terminating running instances of portable app {app.name} before copy")
            self._terminate_app_processes(app, dest_exe=dest_exe, src_path=path, dest_dir=dest_dir)

            logger.info(f"Placing portable app {app.name} to {dest_exe}")

            copied = False
            last_err = None
            for attempt in range(5):
                try:
                    # Удаляем старые .old файлы
                    for old_f in dest_dir.glob("*.old"):
                        try:
                            old_f.unlink()
                        except Exception:
                            pass

                    shutil.copy2(path, dest_exe)
                    copied = True
                    break
                except PermissionError as pe:
                    last_err = pe
                    logger.warning(f"File {dest_exe} locked on attempt {attempt + 1}, killing processes by path...")
                    try:
                        escaped_path = str(dest_exe).replace("'", "''")
                        ps_cmd = f"Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -eq '{escaped_path}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
                        subprocess.run(
                            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    except Exception:
                        pass
                    time.sleep(0.3)
                except Exception as e:
                    last_err = e
                    time.sleep(0.2)

            if not copied:
                # Fallback: переименование заблокированного файла в .old с последующим копированием
                try:
                    old_path = dest_dir / f"{app.name}.{int(time.time())}.old"
                    dest_exe.rename(old_path)
                    shutil.copy2(path, dest_exe)
                    copied = True
                except Exception:
                    if last_err:
                        raise last_err

            # Сохраняем версию в .version для детектора и апдейтера
            if version:
                try:
                    (dest_dir / ".version").write_text(version.strip(), encoding="utf-8")
                except Exception as ve:
                    logger.debug(f"Could not write .version for {app.name}: {ve}")

            shortcut = create_desktop_shortcut(
                dest_exe,
                shortcut_name=app.name,
                working_dir=dest_dir,
            )
            shortcut_msg = f" (Ярлык: {shortcut.name})" if shortcut else ""

            if launch:
                try:
                    os.startfile(str(dest_exe))
                    logger.info(f"Launched portable app {app.name} via os.startfile")
                except Exception:
                    try:
                        creationflags = subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0
                        subprocess.Popen(
                            [str(dest_exe)],
                            cwd=str(dest_dir),
                            creationflags=creationflags,
                            close_fds=True,
                        )
                        logger.info(f"Launched portable app {app.name} via Popen")
                    except Exception as e:
                        logger.warning(f"Could not launch {dest_exe}: {e}")

            return InstallResult(
                app=app,
                success=True,
                error=f"{dest_exe}{shortcut_msg}",
            )
        except Exception as e:
            logger.error(f"Error handling portable app {app.name}: {e}")
            return InstallResult(app=app, success=False, error=str(e))


