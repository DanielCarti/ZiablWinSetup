"""
ZiablWinSetup — Модуль контроля единственного экземпляра (Single Instance Guard).
Предотвращает запуск дубликатов и параллельных копий приложения,
автоматически выводя существующее окно на передний план через Win32 IPC (Named Pipe).
"""

import ctypes
from ctypes import wintypes
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable

logger = logging.getLogger("WinSetup")

MUTEX_NAME = "Local\\ZiablWinSetup_SingleInstance_Mutex_v1"
PIPE_NAME = r"\\.\pipe\ZiablWinSetup_SingleInstance_IPC_v1"

# Win32 Constants
ERROR_ALREADY_EXISTS = 183
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
INVALID_HANDLE_VALUE = -1
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260)
    ]


def force_foreground_window(hwnd: int):
    """Надежно выводит окно на передний план в Windows с обходом ограничений фокуса."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd != hwnd:
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
            curr_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            if fore_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, fore_tid, True)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(curr_tid, fore_tid, False)
            else:
                user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception:
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def find_existing_app_window() -> int | None:
    """Ищет окно запущенного экземпляра ZiablWinSetup."""
    user32 = ctypes.windll.user32
    target_hwnds = []

    def enum_windows_proc(hwnd, lParam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if "ZiablWinSetup" in title:
                target_hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
    return target_hwnds[0] if target_hwnds else None


def get_other_app_processes() -> list[tuple[int, str]]:
    """Находит другие запущенные процессы ZiablWinSetup в текущей пользовательской сессии."""
    kernel32 = ctypes.windll.kernel32
    current_pid = os.getpid()
    current_session = wintypes.DWORD()
    kernel32.ProcessIdToSessionId(current_pid, ctypes.byref(current_session))

    hSnap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hSnap == INVALID_HANDLE_VALUE:
        return []

    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

    my_parent_pid = 0
    all_procs = []

    if kernel32.Process32First(hSnap, ctypes.byref(pe)):
        while True:
            pid = pe.th32ProcessID
            ppid = pe.th32ParentProcessID
            exe_name = pe.szExeFile.decode("cp1251", errors="ignore")
            if pid == current_pid:
                my_parent_pid = ppid
            all_procs.append((pid, ppid, exe_name))
            if not kernel32.Process32Next(hSnap, ctypes.byref(pe)):
                break

    kernel32.CloseHandle(hSnap)

    other_pids = []
    for pid, ppid, exe_name in all_procs:
        # Исключаем текущий процесс и его собственный PyInstaller bootloader
        if pid in (current_pid, my_parent_pid):
            continue
        if "ziabl" in exe_name.lower():
            sess = wintypes.DWORD()
            if kernel32.ProcessIdToSessionId(pid, ctypes.byref(sess)) and sess.value == current_session.value:
                other_pids.append((pid, exe_name))

    return other_pids


class SingleInstanceGuard:
    """Обеспечивает работу только одного экземпляра программы."""

    def __init__(self):
        self._mutex_handle = None
        self._pipe_server_thread = None
        self._is_server_running = False
        self._on_activate: Callable[[], None] | None = None

    def set_activate_callback(self, callback: Callable[[], None]):
        """Регистрирует функцию восстановления окна (например, tray_manager.show_window)."""
        self._on_activate = callback

    def send_activate_to_existing(self) -> bool:
        """Отправляет сигнал активации уже работающему экземпляру через Named Pipe."""
        kernel32 = ctypes.windll.kernel32
        hClient = kernel32.CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        if hClient in (-1, 0xFFFFFFFFFFFFFFFF, 0):
            return False

        try:
            msg = b"ACTIVATE\n"
            written = wintypes.DWORD()
            kernel32.WriteFile(hClient, msg, len(msg), ctypes.byref(written), None)
            return True
        finally:
            kernel32.CloseHandle(hClient)

    def start_pipe_server(self):
        """Запускает фоновый сервер IPC Named Pipe для приема сигналов от повторных запусков."""
        if self._is_server_running:
            return
        self._is_server_running = True

        def server_worker():
            kernel32 = ctypes.windll.kernel32
            logger.info("Запущен IPC сервер единого экземпляра (Named Pipe).")
            while self._is_server_running:
                hPipe = kernel32.CreateNamedPipeW(
                    PIPE_NAME,
                    PIPE_ACCESS_DUPLEX,
                    PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                    1,
                    1024,
                    1024,
                    0,
                    None
                )
                if hPipe in (-1, 0xFFFFFFFFFFFFFFFF, 0):
                    time.sleep(1.0)
                    continue

                try:
                    connected = kernel32.ConnectNamedPipe(hPipe, None) or (kernel32.GetLastError() == 535)
                    if connected and self._is_server_running:
                        buff = ctypes.create_string_buffer(1024)
                        bytes_read = wintypes.DWORD()
                        if kernel32.ReadFile(hPipe, buff, 1024, ctypes.byref(bytes_read), None):
                            msg = buff.value.decode("utf-8", errors="ignore").strip()
                            if "ACTIVATE" in msg:
                                logger.info("Получен IPC сигнал активации от другого экземпляра программы.")
                                if self._on_activate:
                                    try:
                                        self._on_activate()
                                    except Exception as ex:
                                        logger.error(f"Ошибка вызова activate callback: {ex}")
                        kernel32.DisconnectNamedPipe(hPipe)
                finally:
                    kernel32.CloseHandle(hPipe)

        self._pipe_server_thread = threading.Thread(target=server_worker, daemon=True)
        self._pipe_server_thread.start()

    def check_and_acquire(self) -> bool:
        """
        Проверяет, запущен ли уже экземпляр приложения.
        Возвращает True, если запуск разрешен (первый экземпляр).
        Возвращает False, если дубликат обнаружен (экземпляр уже работает).
        """
        kernel32 = ctypes.windll.kernel32

        # 1. Попытка создания мьютекса единого экземпляра
        self._mutex_handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        last_error = kernel32.GetLastError()

        if last_error == ERROR_ALREADY_EXISTS:
            logger.warning("Обнаружен запущенный экземпляр приложения через Named Mutex.")

            # Активируем существующее окно через IPC
            activated = self.send_activate_to_existing()
            if not activated:
                hwnd = find_existing_app_window()
                if hwnd:
                    force_foreground_window(hwnd)

            # Сообщаем пользователю
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Приложение ZiablWinSetup уже запущено и работает на компьютере.\n\n"
                    "Окно существующей копии выведено на передний план (или находится в системном трее).",
                    "ZiablWinSetup — Уже запущено",
                    0x40 | 0x10000  # MB_ICONINFORMATION | MB_TOPMOST
                )
            except Exception:
                pass

            return False

        # 2. Проверка запущенных старых копий (без поддержки мьютекса)
        other_procs = get_other_app_processes()
        if other_procs:
            count = len(other_procs)
            logger.warning(f"Обнаружено {count} старых копий ZiablWinSetup в памяти.")

            try:
                res = ctypes.windll.user32.MessageBoxW(
                    0,
                    f"Обнаружена ранее запущенная копия программы ZiablWinSetup в памяти ({count} процессов).\n\n"
                    "Завершить предыдущие копии и запустить новую версию?",
                    "ZiablWinSetup — Уже запущено",
                    0x24 | 0x10000  # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
                )
            except Exception:
                res = 6  # По умолчанию завершаем старые при ошибке диалога

            if res == 6:  # IDYES
                for pid, exe_name in other_procs:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        logger.info(f"Завершен предыдущий процесс {exe_name} (PID: {pid})")
                    except Exception as e:
                        logger.warning(f"Не удалось завершить PID {pid}: {e}")
                time.sleep(0.4)
            else:
                # Пользователь отказался закрывать старую копию
                return False

        return True

    def cleanup(self):
        """Освобождает мьютекс и останавливает IPC сервер при выходе."""
        self._is_server_running = False
        if self._mutex_handle and self._mutex_handle not in (-1, 0xFFFFFFFFFFFFFFFF, 0):
            try:
                ctypes.windll.kernel32.ReleaseMutex(self._mutex_handle)
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None


single_instance_guard = SingleInstanceGuard()
