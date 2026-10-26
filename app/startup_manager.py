"""
ZiablWinSetup — Менеджер автозагрузки Windows.
Обеспечивает обнаружение ВСЕХ точек автозапуска программ в системе:
1. Реестр HKCU и HKLM (Run, RunOnce, WOW6432Node 32-bit).
2. Системные и пользовательские папки «Автозагрузка» (Startup folders).
3. Интеграция с системным механизмом включения/отключения Windows (StartupApproved).
4. Запланированные задачи планировщика Windows (Task Scheduler) при входе пользователя.
5. Автоматическое извлечение издателя (Publisher) через Win32 VersionInfo.
"""

import base64
import csv
import ctypes
from ctypes import wintypes
import hashlib
import io
import logging
import os
import re
import subprocess
import winreg
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger("WinSetup")
shlwapi = getattr(ctypes.windll, "shlwapi", None)

# Ключи реестра Windows для автозапуска
REG_RUN_LOCATIONS = [
    {
        "root": winreg.HKEY_CURRENT_USER,
        "root_name": "HKCU",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\Run",
        "approved_sub_key": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "source_type": "registry_user",
        "label": "Реестр (HKCU Run)",
    },
    {
        "root": winreg.HKEY_CURRENT_USER,
        "root_name": "HKCU",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "active_sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_user",
        "label": "Реестр (HKCU RunOnce)",
    },
    {
        "root": winreg.HKEY_CURRENT_USER,
        "root_name": "HKCU",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce_Disabled",
        "active_sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_user",
        "label": "Реестр (HKCU RunOnce, откл.)",
        "is_disabled": True,
    },
    {
        "root": winreg.HKEY_CURRENT_USER,
        "root_name": "HKCU",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run",
        "approved_sub_key": None,
        "source_type": "registry_user",
        "label": "Реестр (HKCU Policies Run)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\Run",
        "approved_sub_key": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "source_type": "registry_machine",
        "label": "Реестр (HKLM Run)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "active_sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM RunOnce)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce_Disabled",
        "active_sub_key": r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM RunOnce, откл.)",
        "is_disabled": True,
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM Policies Run)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        "approved_sub_key": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32",
        "source_type": "registry_machine",
        "label": "Реестр (HKLM 32-bit Run)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
        "active_sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM 32-bit RunOnce)",
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce_Disabled",
        "active_sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM 32-bit RunOnce, откл.)",
        "is_disabled": True,
    },
    {
        "root": winreg.HKEY_LOCAL_MACHINE,
        "root_name": "HKLM",
        "sub_key": r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run",
        "approved_sub_key": None,
        "source_type": "registry_machine",
        "label": "Реестр (HKLM 32-bit Policies Run)",
    },
]

# Папки автозагрузки Windows
STARTUP_FOLDERS = [
    {
        "path": Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")),
        "root": winreg.HKEY_CURRENT_USER,
        "approved_sub_key": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder",
        "source_type": "startup_folder",
        "label": "Папка автозапуска (Пользователь)",
    },
    {
        "path": Path(os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup")),
        "root": winreg.HKEY_LOCAL_MACHINE,
        "approved_sub_key": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder",
        "source_type": "startup_folder",
        "label": "Папка автозапуска (Общая)",
    },
]


def extract_executable_path(command: str) -> str:
    """Извлекает реальный путь к .exe из строки команды с аргументами и кавычками."""
    if not command:
        return ""
    expanded = os.path.expandvars(command.strip())

    # 1. Если строка начинается с кавычки "C:\path\app.exe" ...
    if expanded.startswith('"'):
        end_q = expanded.find('"', 1)
        if end_q != -1:
            candidate = expanded[1:end_q]
            if os.path.exists(candidate):
                return candidate
            return candidate

    # 2. Если весь путь существует без аргументов
    if os.path.exists(expanded):
        return expanded

    # 2.1 Специальная обработка служб-оберток (например Wallpaper Engine: wallpaperservice32.exe -p "...\wallpaper32.exe")
    if "wallpaperservice" in expanded.lower():
        m_target = re.search(r'([A-Za-z]:\\[^:\*\?\"\<\>\|]*?wallpaper\d*\.exe)\b', expanded, re.IGNORECASE)
        if m_target and os.path.exists(m_target.group(1)):
            return m_target.group(1)

    # 3. Ищем первое совпадение .exe
    m = re.search(r"([A-Za-z]:\\[^:\*\?\"\<\>\|]*?\.exe)\b", expanded, re.IGNORECASE)
    if m:
        candidate = m.group(1)
        if os.path.exists(candidate):
            return candidate

    # 4. Берем первое слово (до пробела)
    first_part = expanded.split(" ", 1)[0].strip('"')
    if os.path.exists(first_part):
        return first_part

    return first_part


def get_file_publisher(filepath: str) -> str:
    """Извлекает имя издателя (CompanyName) из ресурсов версии исполняемого файла."""
    if not filepath or not os.path.exists(filepath):
        return ""
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(filepath, 0, size, buf):
            return ""

        # Проверяем стандартные языковые блоки: 0409 (EN), 0419 (RU), 0000 (Neutral)
        for code in ["040904b0", "041904b0", "000004b0", "040904e4", "041904e4"]:
            subblock = f"\\StringFileInfo\\{code}\\CompanyName"
            val_ptr = wintypes.LPWSTR()
            val_len = wintypes.UINT()
            if ctypes.windll.version.VerQueryValueW(buf, subblock, ctypes.byref(val_ptr), ctypes.byref(val_len)) and val_ptr.value:
                return val_ptr.value.strip()
    except Exception:
        pass
    return ""


def get_file_description(filepath: str) -> str:
    """Извлекает описание программы (FileDescription) из ресурсов версии файла."""
    if not filepath or not os.path.exists(filepath):
        return ""
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(filepath, 0, size, buf):
            return ""

        for code in ["040904b0", "041904b0", "000004b0", "040904e4", "041904e4"]:
            subblock = f"\\StringFileInfo\\{code}\\FileDescription"
            val_ptr = wintypes.LPWSTR()
            val_len = wintypes.UINT()
            if ctypes.windll.version.VerQueryValueW(buf, subblock, ctypes.byref(val_ptr), ctypes.byref(val_len)) and val_ptr.value:
                return val_ptr.value.strip()
    except Exception:
        pass
    return ""


def _is_approved_enabled(root_hkey, approved_key_path: str | None, item_name: str) -> bool:
    """
    Проверяет статус элемента автозапуска в ключе StartupApproved.
    Если запись отсутствует или первый байт четный (0x02, 0x06) — включено.
    Если первый байт нечетный (0x03, 0x01) — отключено пользователем.
    """
    if not approved_key_path:
        return True
    try:
        with winreg.OpenKey(root_hkey, approved_key_path, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, item_name)
            if isinstance(val, (bytes, bytearray)) and len(val) > 0:
                # Четный байт (2, 6) = Enabled; нечетный (3, 1) = Disabled
                return (val[0] % 2 == 0)
    except FileNotFoundError:
        return True
    except Exception:
        return True
    return True


def _run_elevated_ps(ps_command: str) -> bool:
    """Выполняет команду PowerShell с повышением прав через Windows UAC диалог."""
    try:
        from app.installer import run_with_elevation
        code = run_with_elevation(
            "powershell.exe",
            ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_command]
        )
        return code == 0
    except PermissionError:
        logger.info("UAC запрос отменён пользователем.")
        return False
    except Exception as e:
        logger.warning(f"Ошибка выполнения команды с повышением прав: {e}")
        return False


def _set_approved_status(root_hkey, approved_key_path: str, item_name: str, enable: bool) -> bool:
    """Записывает статус включено/отключено в системный ключ StartupApproved с UAC-повышением при необходимости."""
    if not approved_key_path:
        return False
    try:
        # Пытаемся напрямую
        with winreg.CreateKeyEx(root_hkey, approved_key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ) as key:
            byte_status = b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" if enable else b"\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            winreg.SetValueEx(key, item_name, 0, winreg.REG_BINARY, byte_status)
        return True
    except PermissionError:
        # Недостаточно прав (например HKLM без прав администратора) -> UAC
        root_str = "HKLM" if root_hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
        ps_bytes = "0x02,0,0,0,0,0,0,0,0,0,0,0" if enable else "0x03,0,0,0,0,0,0,0,0,0,0,0"
        escaped_item = item_name.replace("'", "''")
        ps_cmd = (
            f"New-Item -Path '{root_str}:\\{approved_key_path}' -Force -ErrorAction SilentlyContinue; "
            f"Set-ItemProperty -Path '{root_str}:\\{approved_key_path}' -Name '{escaped_item}' "
            f"-Value ([byte[]]({ps_bytes})) -Type Binary -Force"
        )
        return _run_elevated_ps(ps_cmd)
    except Exception as e:
        logger.error(f"Ошибка записи в StartupApproved ({approved_key_path}, {item_name}): {e}")
        return False


def _move_reg_value(root_hkey, src_sub_key: str, dst_sub_key: str, val_name: str) -> bool:
    """
    Перемещает параметр реестра между разделами (например, RunOnce <-> RunOnce_Disabled).
    При необходимости запрашивает права администратора через UAC.
    """
    try:
        with winreg.OpenKey(root_hkey, src_sub_key, 0, winreg.KEY_READ) as src_k:
            val_data, val_type = winreg.QueryValueEx(src_k, val_name)
        with winreg.CreateKeyEx(root_hkey, dst_sub_key, 0, winreg.KEY_SET_VALUE) as dst_k:
            winreg.SetValueEx(dst_k, val_name, 0, val_type, val_data)
        with winreg.OpenKey(root_hkey, src_sub_key, 0, winreg.KEY_SET_VALUE) as src_k:
            winreg.DeleteValue(src_k, val_name)
        return True
    except PermissionError:
        root_str = "HKLM" if root_hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
        escaped_val = val_name.replace("'", "''")
        ps_cmd = (
            f"New-Item -Path '{root_str}:\\{dst_sub_key}' -Force -ErrorAction SilentlyContinue; "
            f"$v = (Get-ItemProperty -Path '{root_str}:\\{src_sub_key}' -Name '{escaped_val}' -ErrorAction Stop).'{escaped_val}'; "
            f"Set-ItemProperty -Path '{root_str}:\\{dst_sub_key}' -Name '{escaped_val}' -Value $v -Force; "
            f"Remove-ItemProperty -Path '{root_str}:\\{src_sub_key}' -Name '{escaped_val}' -Force"
        )
        return _run_elevated_ps(ps_cmd)
    except Exception as e:
        logger.error(f"Ошибка перемещения значения реестра {val_name}: {e}")
        return False


def _resolve_shortcut_target(lnk_path: Path) -> str:
    """Извлекает целевой путь из .lnk файла."""
    try:
        # Быстрый бинарный парсинг или PowerShell WScript.Shell
        ps_cmd = f"$sh = New-Object -ComObject WScript.Shell; $sc = $sh.CreateShortcut('{lnk_path}'); $sc.TargetPath"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        target = res.stdout.strip()
        if target:
            return target
    except Exception:
        pass
_ICON_CACHE: dict[str, str] = {}


def extract_file_icon_base64(filepath: str) -> str:
    """
    Извлекает оригинальную иконку Windows приложения в формате PNG Base64 Data URL.
    Поддерживает исполняемые файлы (.exe), библиотеки (.dll) и ярлыки (.lnk).
    """
    if not filepath:
        return ""
    if filepath in _ICON_CACHE:
        return _ICON_CACHE[filepath]
    if not os.path.exists(filepath):
        _ICON_CACHE[filepath] = ""
        return ""

    try:
        from PIL import Image

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon", wintypes.BOOL),
                ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80),
            ]

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        shell32 = ctypes.windll.shell32

        user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
        user32.GetIconInfo.restype = wintypes.BOOL
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.GetDIBits.argtypes = [
            wintypes.HDC,
            wintypes.HBITMAP,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.c_void_p,
            ctypes.POINTER(BITMAPINFOHEADER),
            wintypes.UINT,
        ]
        gdi32.GetDIBits.restype = wintypes.BOOL

        sfi = SHFILEINFOW()
        SHGFI_ICON = 0x000000100
        SHGFI_LARGEICON = 0x000000000
        res = shell32.SHGetFileInfoW(
            filepath, 0, ctypes.byref(sfi), ctypes.sizeof(SHFILEINFOW), SHGFI_ICON | SHGFI_LARGEICON
        )
        if not res or not sfi.hIcon:
            _ICON_CACHE[filepath] = ""
            return ""

        hicon = sfi.hIcon
        icon_info = ICONINFO()
        if not user32.GetIconInfo(hicon, ctypes.byref(icon_info)):
            user32.DestroyIcon(hicon)
            _ICON_CACHE[filepath] = ""
            return ""

        hdc = user32.GetDC(0)
        hmemdc = gdi32.CreateCompatibleDC(hdc)
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)

        gdi32.GetDIBits(hmemdc, icon_info.hbmColor, 0, 0, None, ctypes.byref(bmi), 0)
        w = bmi.biWidth
        h = abs(bmi.biHeight)
        if w <= 0 or h <= 0:
            gdi32.DeleteDC(hmemdc)
            user32.ReleaseDC(0, hdc)
            if icon_info.hbmColor:
                gdi32.DeleteObject(icon_info.hbmColor)
            if icon_info.hbmMask:
                gdi32.DeleteObject(icon_info.hbmMask)
            user32.DestroyIcon(hicon)
            _ICON_CACHE[filepath] = ""
            return ""

        bmi.biHeight = -h
        bmi.biBitCount = 32
        bmi.biCompression = 0
        buf_size = w * h * 4
        buf = (ctypes.c_ubyte * buf_size)()
        gdi32.GetDIBits(hmemdc, icon_info.hbmColor, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteDC(hmemdc)
        user32.ReleaseDC(0, hdc)
        if icon_info.hbmColor:
            gdi32.DeleteObject(icon_info.hbmColor)
        if icon_info.hbmMask:
            gdi32.DeleteObject(icon_info.hbmMask)
        user32.DestroyIcon(hicon)

        img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
        extrema = img.getextrema()
        if len(extrema) >= 4 and extrema[3] == (0, 0):
            r, g, b, _ = img.split()
            img = Image.merge("RGBA", (r, g, b, Image.new("L", (w, h), 255)))

        out = io.BytesIO()
        img.save(out, format="PNG")
        b64 = "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
        _ICON_CACHE[filepath] = b64
        return b64
    except Exception as e:
        logger.debug(f"Error extracting icon for {filepath}: {e}")
        _ICON_CACHE[filepath] = ""
        return ""


def _resolve_resource_string(res_str: str) -> str:
    """Разрешает строки ресурсов вида @{Package?ms-resource://...} или ms-resource:..."""
    if not res_str or not shlwapi:
        return res_str
    if not (res_str.startswith("@") or res_str.startswith("ms-resource:")):
        return res_str
    buf = ctypes.create_unicode_buffer(1024)
    try:
        if shlwapi.SHLoadIndirectString(res_str, buf, 1024, None) == 0 and buf.value:
            return buf.value.strip()
    except Exception:
        pass
    return res_str


def _find_package_info(family_name: str) -> dict[str, Any]:
    """Находит сведения о пакете UWP (папка, манифест, exe, логотип, издатель) по имени семейства."""
    parts = family_name.split("_")
    if len(parts) != 2:
        return {}
    name_prefix, pub_id = parts[0], parts[1]
    packages_key = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\PackageRepository\Packages"

    manifest_folder = None
    best_folder = None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, packages_key) as k:
            num_keys, _, _ = winreg.QueryInfoKey(k)
            for i in range(num_keys):
                sub = winreg.EnumKey(k, i)
                # Пропускаем сплит-пакеты ресурсов (_split.)
                if "_split." in sub:
                    continue
                if sub.startswith(name_prefix + "_") and sub.endswith("_" + pub_id):
                    try:
                        with winreg.OpenKey(k, sub) as pk:
                            p, _ = winreg.QueryValueEx(pk, "Path")
                            if os.path.exists(p):
                                best_folder = p
                                if os.path.exists(os.path.join(p, "AppxManifest.xml")):
                                    manifest_folder = p
                                    break
                    except OSError:
                        pass
    except Exception:
        pass

    folder = manifest_folder or best_folder
    if not folder:
        return {}

    info: dict[str, Any] = {
        "folder": folder,
        "display_name": "",
        "publisher": "",
        "exe_path": "",
        "logo_path": "",
        "task_names": {},
    }

    mf_path = os.path.join(folder, "AppxManifest.xml")
    if os.path.exists(mf_path):
        try:
            tree = ET.parse(mf_path)
            root = tree.getroot()
            props = root.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Properties")
            if props is not None:
                for c in props:
                    t = c.tag.split("}")[-1]
                    if t == "PublisherDisplayName" and c.text:
                        info["publisher"] = c.text
                    elif t == "DisplayName" and c.text:
                        info["display_name"] = c.text
                    elif t == "Logo" and c.text:
                        info["logo_path"] = os.path.join(folder, c.text)

            for app in root.iter("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Application"):
                ex = app.attrib.get("Executable")
                if ex:
                    full_ex = os.path.normpath(os.path.join(folder, ex))
                    if os.path.exists(full_ex) and not info["exe_path"]:
                        info["exe_path"] = full_ex
                for elem in app.iter():
                    if elem.tag.endswith("StartupTask"):
                        tid = elem.attrib.get("TaskId")
                        dn = elem.attrib.get("DisplayName")
                        if tid and dn:
                            info["task_names"][tid] = dn
        except Exception as e:
            logger.debug(f"Ошибка парсинга AppxManifest {mf_path}: {e}")

    return info


def _scan_uwp_startup_items() -> list[dict[str, Any]]:
    """Сканирует элементы автозапуска современных UWP/Store приложений (windows.startupTask)."""
    items: list[dict[str, Any]] = []
    base_key = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData"
    hkey = winreg.HKEY_CURRENT_USER

    try:
        with winreg.OpenKey(hkey, base_key) as k:
            n_pkgs, _, _ = winreg.QueryInfoKey(k)
            for i in range(n_pkgs):
                pkg_family = winreg.EnumKey(k, i)
                pkg_path = f"{base_key}\\{pkg_family}"

                # Проверяем SplashScreen для локализованного имени
                splash_name = ""
                splash_path = f"{pkg_path}\\SplashScreen"
                try:
                    with winreg.OpenKey(hkey, splash_path) as spk:
                        n_sp, _, _ = winreg.QueryInfoKey(spk)
                        for s_i in range(n_sp):
                            app_sub = winreg.EnumKey(spk, s_i)
                            try:
                                with winreg.OpenKey(spk, app_sub) as apk:
                                    raw_app_name, _ = winreg.QueryValueEx(apk, "AppName")
                                    resolved = _resolve_resource_string(raw_app_name)
                                    if resolved and not resolved.startswith("@") and not resolved.startswith("ms-resource:"):
                                        splash_name = resolved
                                        break
                            except OSError:
                                pass
                except OSError:
                    pass

                try:
                    with winreg.OpenKey(hkey, pkg_path) as pk:
                        n_tasks, _, _ = winreg.QueryInfoKey(pk)
                        for j in range(n_tasks):
                            task_id = winreg.EnumKey(pk, j)
                            if task_id in ("HAM", "PSR", "Schemas", "SplashScreen"):
                                continue

                            task_path = f"{pkg_path}\\{task_id}"
                            try:
                                with winreg.OpenKey(hkey, task_path) as tk:
                                    try:
                                        state, _ = winreg.QueryValueEx(tk, "State")
                                    except FileNotFoundError:
                                        continue

                                    enabled = (state == 2)
                                    pkg_info = _find_package_info(pkg_family)
                                    folder = pkg_info.get("folder", "")
                                    exe_path = pkg_info.get("exe_path", "")
                                    pub = pkg_info.get("publisher", "")

                                    task_disp = pkg_info.get("task_names", {}).get(task_id, "")
                                    resolved_task_disp = _resolve_resource_string(task_disp) if task_disp else ""
                                    manifest_disp = _resolve_resource_string(pkg_info.get("display_name", ""))

                                    display_name = ""
                                    for candidate in [splash_name, resolved_task_disp, manifest_disp]:
                                        if candidate and not candidate.startswith("@") and not candidate.startswith("ms-resource:"):
                                            display_name = candidate
                                            break

                                    if not display_name and exe_path:
                                        display_name = get_file_description(exe_path)

                                    if not display_name:
                                        display_name = pkg_family.split("_")[0]
                                        if display_name.startswith("Microsoft."):
                                            display_name = display_name.replace("Microsoft.", "")

                                    if not pub and exe_path:
                                        pub = get_file_publisher(exe_path)

                                    icon_data = extract_file_icon_base64(exe_path) if exe_path else ""

                                    item_uid = f"uwp_{pkg_family}_{task_id}"
                                    clean_id = hashlib.md5(item_uid.encode("utf-8")).hexdigest()[:12]

                                    items.append({
                                        "id": clean_id,
                                        "name": display_name,
                                        "raw_name": f"{pkg_family}!{task_id}",
                                        "display_name": display_name,
                                        "publisher": pub or "Microsoft Store",
                                        "command": f"UWP: {pkg_family} ({task_id})",
                                        "file_path": exe_path or folder,
                                        "file_exists": bool(exe_path and os.path.exists(exe_path)),
                                        "source_type": "uwp_startup",
                                        "source_label": "Магазин Windows (UWP)",
                                        "location": f"AppModel: {pkg_family}",
                                        "pkg_family": pkg_family,
                                        "task_id": task_id,
                                        "approved_key": None,
                                        "root_hkey_name": "HKCU",
                                        "enabled": enabled,
                                        "can_toggle": True,
                                        "can_delete": True,
                                        "icon_data": icon_data,
                                    })
                            except OSError:
                                pass
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка сканирования UWP автозапуска: {e}")

    return items


def _scan_services_startup_items() -> list[dict[str, Any]]:
    """Сканирует сторонние автозапускаемые службы Windows (например Wallpaper Engine, AnyDesk, VPN)."""
    items: list[dict[str, Any]] = []
    services_key = r"SYSTEM\CurrentControlSet\Services"
    hkey = winreg.HKEY_LOCAL_MACHINE

    try:
        with winreg.OpenKey(hkey, services_key) as k:
            n_sub, _, _ = winreg.QueryInfoKey(k)
            for i in range(n_sub):
                s_name = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(k, s_name) as sk:
                        try:
                            start_type, _ = winreg.QueryValueEx(sk, "Start")
                            if start_type not in (2, 4):  # 2: Auto, 4: Disabled
                                continue
                            img_path, _ = winreg.QueryValueEx(sk, "ImagePath")
                        except FileNotFoundError:
                            continue

                        img_lower = img_path.lower()
                        # Исключаем системные службы ядра Windows
                        if any(x in img_lower for x in [
                            "system32\\svchost.exe",
                            "system32\\lsass.exe",
                            "system32\\services.exe",
                            "system32\\csrss.exe",
                            "system32\\smss.exe",
                            "system32\\spoolsv.exe",
                            "system32\\sppsvc.exe",
                            "system32\\vmnat.exe",
                            "system32\\vmnetdhcp.exe",
                        ]):
                            continue
                        if "system32\\drivers\\" in img_lower or img_lower.endswith(".sys"):
                            continue
                        if img_lower.startswith("\\systemroot\\system32\\") or img_lower.startswith("system32\\"):
                            continue

                        try:
                            disp_name, _ = winreg.QueryValueEx(sk, "DisplayName")
                            disp_name = _resolve_resource_string(disp_name)
                        except FileNotFoundError:
                            disp_name = s_name

                        # Ищем реальный исполняемый файл (в т.ч. обертки вроде wallpaperservice)
                        target_exe = None
                        if "wallpaperservice" in img_lower:
                            m = re.search(r'([A-Za-z]:\\[^:\*\?\"\<\>\|]*?wallpaper\d*\.exe)\b', img_path, re.IGNORECASE)
                            if m and os.path.exists(m.group(1)):
                                target_exe = m.group(1)

                        exe_path = target_exe or extract_executable_path(img_path)
                        pub = get_file_publisher(exe_path)
                        desc = get_file_description(exe_path)

                        # Исключаем встроенные системные компоненты Microsoft Windows в system32
                        if pub and any(m in pub.lower() for m in ["microsoft windows", "microsoft corporation"]) and ("windows\\system32" in exe_path.lower() or "windows\\syswow64" in exe_path.lower()):
                            continue

                        # Исключаем службы обновлений Windows Defender
                        if s_name.lower() in ("windefend", "mdcoresvc"):
                            continue

                        enabled = (start_type == 2)
                        icon_data = extract_file_icon_base64(exe_path)

                        item_id = f"service_{s_name}"
                        clean_id = hashlib.md5(item_id.encode("utf-8")).hexdigest()[:12]

                        clean_disp = disp_name or desc or s_name
                        if clean_disp.startswith("@"):
                            clean_disp = desc or s_name

                        items.append({
                            "id": clean_id,
                            "name": clean_disp,
                            "raw_name": s_name,
                            "service_name": s_name,
                            "display_name": clean_disp,
                            "publisher": pub or "Служба Windows",
                            "command": img_path,
                            "file_path": exe_path,
                            "file_exists": bool(exe_path and os.path.exists(exe_path)),
                            "source_type": "windows_service",
                            "source_label": "Служба Windows",
                            "location": f"Service: {s_name}",
                            "approved_key": None,
                            "root_hkey_name": "HKLM",
                            "enabled": enabled,
                            "can_toggle": True,
                            "can_delete": True,
                            "icon_data": icon_data,
                        })
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка сканирования служб Windows: {e}")

    return items



_HIGH_IMPACT_PATTERNS = {
    "discord", "steam", "epic", "riot", "battle.net", "chrome", "firefox", "opera",
    "browser", "msedge", "yandex", "brave", "torrent", "wallpaper", "adobe",
    "creative cloud", "virtualbox", "vmware", "docker", "wsl", "onedrive",
    "dropbox", "slack", "teams", "spotify", "antivirus", "kaspersky", "drweb"
}

_LOW_IMPACT_PATTERNS = {
    "tray", "helper", "hotkey", "volume", "audio", "synaptics", "realtek",
    "notification", "print", "mouse", "keyboard", "bluetooth", "brightness"
}


def _calculate_startup_impact(item: dict[str, Any]) -> dict[str, str]:
    """
    Calculates estimated startup impact similar to Windows Task Manager.
    Returns:
    - 'impact': 'high' | 'medium' | 'low' | 'none'
    - 'impact_ru': 'Высокое' | 'Среднее' | 'Низкое' | 'Не замерено'
    - 'impact_en': 'High' | 'Medium' | 'Low' | 'Not measured'
    """
    search_text = f"{item.get('name', '')} {item.get('display_name', '')} {item.get('command', '')} {item.get('file_path', '')}".lower()
    fp = item.get("file_path", "")
    file_size = 0
    try:
        if fp and os.path.exists(fp):
            file_size = os.path.getsize(fp)
    except Exception:
        pass

    if any(p in search_text for p in _HIGH_IMPACT_PATTERNS) or file_size > 25 * 1024 * 1024:
        return {
            "impact": "high",
            "impact_ru": "Высокое",
            "impact_en": "High",
        }

    if any(p in search_text for p in _LOW_IMPACT_PATTERNS) or (0 < file_size < 3 * 1024 * 1024) or item.get("source_type") == "service_delayed":
        return {
            "impact": "low",
            "impact_ru": "Низкое",
            "impact_en": "Low",
        }

    return {
        "impact": "medium",
        "impact_ru": "Среднее",
        "impact_en": "Medium",
    }

class StartupManager:
    """Менеджер автозагрузки Windows (реестр, папки, планировщик)."""

    @staticmethod
    def get_all_items() -> list[dict[str, Any]]:
        """Сканирует и возвращает все обнаруженные элементы автозапуска."""
        items: list[dict[str, Any]] = []

        # 1. Сканирование реестра (HKCU и HKLM)
        for loc in REG_RUN_LOCATIONS:
            try:
                with winreg.OpenKey(loc["root"], loc["sub_key"], 0, winreg.KEY_READ) as key:
                    index = 0
                    while True:
                        try:
                            name, cmd, _ = winreg.EnumValue(key, index)
                            index += 1
                            if not name:
                                continue

                            if loc.get("is_disabled"):
                                enabled = False
                            else:
                                enabled = _is_approved_enabled(loc["root"], loc["approved_sub_key"], name)

                            exe_path = extract_executable_path(cmd)
                            file_exists = bool(exe_path and os.path.exists(exe_path))
                            pub = get_file_publisher(exe_path)
                            desc = get_file_description(exe_path)

                            # Уникальный ID для API (используем active_sub_key для стабильного ID при переключении)
                            active_sub = loc.get("active_sub_key", loc["sub_key"])
                            item_id = f"{loc['root_name']}_{active_sub}_{name}"
                            clean_id = hashlib.md5(item_id.encode("utf-8")).hexdigest()[:12]

                            icon_data = extract_file_icon_base64(exe_path)

                            items.append({
                                "id": clean_id,
                                "name": name,
                                "raw_name": name,
                                "display_name": desc or name,
                                "publisher": pub or "Не указан",
                                "command": cmd,
                                "file_path": exe_path,
                                "file_exists": file_exists,
                                "source_type": loc["source_type"],
                                "source_label": loc["label"],
                                "location": f"{loc['root_name']}\\{loc['sub_key']}",
                                "sub_key": loc["sub_key"],
                                "active_sub_key": active_sub,
                                "approved_key": loc["approved_sub_key"],
                                "root_hkey_name": loc["root_name"],
                                "enabled": enabled,
                                "can_toggle": True,
                                "can_delete": True,
                                "icon_data": icon_data,
                            })
                        except OSError:
                            break
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"Ошибка чтения ветки реестра {loc['sub_key']}: {e}")

        # 2. Сканирование папок автозапуска
        for folder_info in STARTUP_FOLDERS:
            folder_path: Path = folder_info["path"]
            if not folder_path.exists():
                continue

            try:
                for file_entry in folder_path.iterdir():
                    if file_entry.is_dir() or file_entry.name.lower() == "desktop.ini":
                        continue

                    # Проверяем имя файла
                    item_name = file_entry.name
                    target_path = str(file_entry)
                    if file_entry.suffix.lower() == ".lnk":
                        target_path = _resolve_shortcut_target(file_entry)

                    exe_path = extract_executable_path(target_path)
                    file_exists = bool(exe_path and os.path.exists(exe_path))
                    pub = get_file_publisher(exe_path)
                    desc = get_file_description(exe_path)
                    enabled = _is_approved_enabled(folder_info["root"], folder_info["approved_sub_key"], item_name)

                    item_id = f"folder_{folder_path}_{item_name}"
                    clean_id = hashlib.md5(item_id.encode("utf-8")).hexdigest()[:12]

                    icon_data = extract_file_icon_base64(str(file_entry)) or extract_file_icon_base64(exe_path)

                    items.append({
                        "id": clean_id,
                        "name": file_entry.stem,
                        "raw_name": item_name,
                        "display_name": desc or file_entry.stem,
                        "publisher": pub or "Не указан",
                        "command": target_path,
                        "file_path": exe_path,
                        "file_exists": file_exists,
                        "source_type": folder_info["source_type"],
                        "source_label": folder_info["label"],
                        "location": str(folder_path),
                        "approved_key": folder_info["approved_sub_key"],
                        "root_hkey_name": "HKCU" if folder_info["root"] == winreg.HKEY_CURRENT_USER else "HKLM",
                        "enabled": enabled,
                        "can_toggle": True,
                        "can_delete": True,
                        "icon_data": icon_data,
                    })
            except Exception as e:
                logger.warning(f"Ошибка сканирования папки автозапуска {folder_path}: {e}")

        # 3. Сканирование планировщика задач (Task Scheduler — сторонние задачи при входе)
        try:
            p = subprocess.run(
                ["schtasks", "/query", "/fo", "CSV", "/v"],
                capture_output=True,
                text=True,
                encoding="cp866",
                errors="replace",
                timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if p.stdout.strip():
                lines = p.stdout.strip().splitlines()
                reader = csv.reader(lines)
                header = next(reader, None)
                seen_tasks: set[str] = set()

                for row in reader:
                    if len(row) < 9:
                        continue

                    # Извлекаем значения с поддержкой как позиций, так и локализованных имен
                    task_name = row[1].strip() if len(row) > 1 else ""
                    state = row[3].strip() if len(row) > 3 else ""
                    author = row[7].strip() if len(row) > 7 else ""
                    cmd = row[8].strip() if len(row) > 8 else ""
                    sched = row[17].strip() if len(row) > 17 else ""

                    if not task_name or task_name.startswith("\\Microsoft\\Windows"):
                        continue
                    if task_name in seen_tasks:
                        continue

                    # Отбираем задачи, запускающиеся при входе/старте или принадлежащие сторонним приложениям
                    is_startup = any(k in sched.lower() for k in ["logon", "start up", "startup", "вход", "запуск"])
                    is_app_updater = any(s in cmd.lower() or s in task_name.lower() for s in [
                        "update", "discord", "telegram", "adobe", "steam", "edge", "chrome",
                        "yandex", "browser", "tray", "client", "amnezia", "onedrive", "wallpaper", "pcmanager"
                    ])

                    if is_startup or is_app_updater:
                        seen_tasks.add(task_name)
                        exe_path = extract_executable_path(cmd)
                        file_exists = bool(exe_path and os.path.exists(exe_path))
                        pub = get_file_publisher(exe_path) or author.replace("ZIABL-REDMIBOOK\\", "").strip()
                        desc = get_file_description(exe_path)
                        enabled = (state.lower() not in ("disabled", "отключено"))

                        clean_name = task_name.lstrip("\\")
                        item_id = f"schtask_{task_name}"
                        clean_id = hashlib.md5(item_id.encode("utf-8")).hexdigest()[:12]

                        icon_data = extract_file_icon_base64(exe_path)

                        items.append({
                            "id": clean_id,
                            "name": clean_name,
                            "raw_name": task_name,
                            "display_name": desc or clean_name,
                            "publisher": pub or "Планировщик задач",
                            "command": cmd,
                            "file_path": exe_path,
                            "file_exists": file_exists,
                            "source_type": "scheduled_task",
                            "source_label": "Планировщик задач",
                            "location": f"Task: {task_name}",
                            "approved_key": None,
                            "root_hkey_name": None,
                            "enabled": enabled,
                            "can_toggle": True,
                            "can_delete": True,
                            "icon_data": icon_data,
                        })
        except Exception as e:
            logger.warning(f"Ошибка чтения задач планировщика: {e}")

        # 4. Сканирование UWP/Store приложений (windows.startupTask)
        try:
            uwp_items = _scan_uwp_startup_items()
            items.extend(uwp_items)
        except Exception as e:
            logger.warning(f"Ошибка получения UWP автозагрузки: {e}")

        # 5. Сканирование сторонних служб автозапуска (Windows Services)
        try:
            service_items = _scan_services_startup_items()
            items.extend(service_items)
        except Exception as e:
            logger.warning(f"Ошибка получения служб автозапуска: {e}")

        # Расчет нагрузки при автозапуске (Startup Impact) как в Диспетчере задач Windows
        for it in items:
            imp_info = _calculate_startup_impact(it)
            it["impact"] = imp_info["impact"]
            it["impact_ru"] = imp_info["impact_ru"]
            it["impact_en"] = imp_info["impact_en"]

        return items

    @classmethod
    def toggle_item(cls, item_id: str, enable: bool) -> tuple[bool, str]:
        """Включает или отключает выбранный элемент автозапуска."""
        all_items = cls.get_all_items()
        target = next((item for item in all_items if item["id"] == item_id), None)
        if not target:
            return False, "Элемент не найден в списке автозапуска."

        source_type = target["source_type"]

        # Реестр или Папка автозапуска
        if source_type in ("registry_user", "registry_machine", "startup_folder"):
            approved_key = target.get("approved_key")
            root_name = target.get("root_hkey_name", "HKCU")
            root_hkey = winreg.HKEY_LOCAL_MACHINE if root_name == "HKLM" else winreg.HKEY_CURRENT_USER

            if approved_key:
                ok = _set_approved_status(root_hkey, approved_key, target["raw_name"], enable)
                if ok:
                    state_str = "включен" if enable else "отключен"
                    return True, f"Автозапуск «{target['name']}» успешно {state_str}."
                return False, f"Не удалось обновить статус в StartupApproved для {target['name']}."
            else:
                # Ветки без StartupApproved (например RunOnce): перемещаем значение между активной веткой и _Disabled
                active_sub = target.get("active_sub_key") or target.get("sub_key", "").replace("_Disabled", "")
                if not active_sub:
                    loc_str = target.get("location", "")
                    active_sub = loc_str.split("\\", 1)[1] if "\\" in loc_str else loc_str
                    active_sub = active_sub.replace("_Disabled", "")
                disabled_sub = f"{active_sub}_Disabled"

                src_sub = disabled_sub if enable else active_sub
                dst_sub = active_sub if enable else disabled_sub

                ok = _move_reg_value(root_hkey, src_sub, dst_sub, target["raw_name"])
                if ok:
                    state_str = "включен" if enable else "отключен"
                    return True, f"Автозапуск «{target['name']}» успешно {state_str}."
                return False, f"Не удалось изменить состояние для «{target['name']}»."

        # Планировщик задач (Task Scheduler)
        if source_type == "scheduled_task":
            action_flag = "/enable" if enable else "/disable"
            task_name = target["raw_name"]
            res = subprocess.run(
                ["schtasks", "/change", "/tn", task_name, action_flag],
                capture_output=True,
                text=True,
                encoding="cp866",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                state_str = "включена" if enable else "отключена"
                return True, f"Задача «{target['name']}» успешно {state_str}."

            # Попытка с повышением прав через UAC
            err_output = (res.stderr or "") + " " + (res.stdout or "")
            if any(w in err_output.lower() for w in ["доступ", "denied", "администр", "privilege"]):
                ps_cmd = f"schtasks /change /tn '{task_name}' {action_flag}"
                if _run_elevated_ps(ps_cmd):
                    state_str = "включена" if enable else "отключена"
                    return True, f"Задача «{target['name']}» успешно {state_str}."

            return False, f"Ошибка schtasks: {res.stderr.strip() or res.stdout.strip()}"

        # Магазин Windows (UWP / MSIX)
        if source_type == "uwp_startup":
            pkg_family = target.get("pkg_family")
            task_id = target.get("task_id")
            if not pkg_family or not task_id:
                return False, "Недостаточно данных для переключения UWP приложения."
            reg_path = rf"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData\{pkg_family}\{task_id}"
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:
                    # 2 = Enabled, 1 = Disabled
                    winreg.SetValueEx(k, "State", 0, winreg.REG_DWORD, 2 if enable else 1)
                    winreg.SetValueEx(k, "UserEnabledStartupOnce", 0, winreg.REG_DWORD, 1 if enable else 0)
                state_str = "включен" if enable else "отключен"
                return True, f"Автозапуск «{target['name']}» успешно {state_str}."
            except Exception as e:
                return False, f"Ошибка переключения UWP автозапуска: {e}"

        # Службы Windows (Services)
        if source_type == "windows_service":
            svc_name = target.get("service_name") or target.get("raw_name")
            if not svc_name:
                return False, "Не указано имя службы."

            start_arg = "auto" if enable else "disabled"
            res = subprocess.run(
                ["sc.exe", "config", svc_name, f"start={start_arg}"],
                capture_output=True,
                text=True,
                encoding="cp866",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if res.returncode == 0:
                if not enable:
                    subprocess.run(["net.exe", "stop", svc_name, "/y"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                state_str = "включена" if enable else "отключена"
                return True, f"Служба «{target['name']}» успешно {state_str}."

            # Попытка 1: через PowerShell с UAC-повышением прав
            ps_cmd = f"Set-Service -Name '{svc_name}' -StartupType {('Automatic' if enable else 'Disabled')}"
            if _run_elevated_ps(ps_cmd):
                if not enable:
                    _run_elevated_ps(f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue")
                state_str = "включена" if enable else "отключена"
                return True, f"Служба «{target['name']}» успешно {state_str}."

            # Попытка 2: Для защищённых служб (GamingServices и др.), у которых закрыт доступ к ChangeServiceConfig
            # Меняем параметр Start напрямую в системном реестре HKLM\SYSTEM\CurrentControlSet\Services\<svc_name>
            # Start: 2 = Automatic, 4 = Disabled
            reg_val = 2 if enable else 4
            reg_ps = f"Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\{svc_name}' -Name 'Start' -Value {reg_val} -Force"
            if _run_elevated_ps(reg_ps):
                if not enable:
                    _run_elevated_ps(f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue")
                state_str = "включена" if enable else "отключена"
                return True, f"Служба «{target['name']}» успешно {state_str} (через системный реестр)."

            err_msg = res.stderr.strip() or res.stdout.strip()
            return False, f"Ошибка переключения службы {svc_name}: {err_msg}"

        return False, "Неподдерживаемый тип элемента для переключения."

    @classmethod
    def delete_item(cls, item_id: str) -> tuple[bool, str]:
        """Удаляет запись автозапуска из системы."""
        all_items = cls.get_all_items()
        target = next((item for item in all_items if item["id"] == item_id), None)
        if not target:
            return False, "Элемент не найден в списке автозапуска."

        source_type = target["source_type"]

        # Магазин Windows (UWP)
        if source_type == "uwp_startup":
            # Для UWP удаление отключает автозапуск (State = 1)
            return cls.toggle_item(item_id, False)

        # Службы Windows
        if source_type == "windows_service":
            # Безопасное «удаление» службы из автозапуска = остановка и отключение (Disabled)
            svc_name = target.get("service_name") or target.get("raw_name")
            ps_cmd = f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue; Set-Service -Name '{svc_name}' -StartupType Disabled"
            if _run_elevated_ps(ps_cmd):
                return True, f"Служба «{target['name']}» остановлена и отключена из автозапуска."
            return cls.toggle_item(item_id, False)

        # Реестр
        if source_type in ("registry_user", "registry_machine"):
            loc_str = target.get("location", "")
            root_name = target.get("root_hkey_name", "HKCU")
            root_hkey = winreg.HKEY_LOCAL_MACHINE if root_name == "HKLM" else winreg.HKEY_CURRENT_USER
            sub_key = target.get("sub_key") or (loc_str.split("\\", 1)[1] if "\\" in loc_str else loc_str)

            try:
                with winreg.OpenKey(root_hkey, sub_key, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, target["raw_name"])
            except PermissionError:
                root_str = "HKLM" if root_hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
                escaped_item = target["raw_name"].replace("'", "''")
                ps_cmd = f"Remove-ItemProperty -Path '{root_str}:\\{sub_key}' -Name '{escaped_item}' -Force -ErrorAction SilentlyContinue"
                if not _run_elevated_ps(ps_cmd):
                    return False, f"Не удалось удалить запись из реестра (требуются права администратора)."
            except Exception as e:
                return False, f"Не удалось удалить запись из реестра: {e}"

            # Также удаляем из StartupApproved если есть
            approved_key = target.get("approved_key")
            if approved_key:
                try:
                    with winreg.OpenKey(root_hkey, approved_key, 0, winreg.KEY_SET_VALUE) as app_key:
                        winreg.DeleteValue(app_key, target["raw_name"])
                except PermissionError:
                    root_str = "HKLM" if root_hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
                    escaped_item = target["raw_name"].replace("'", "''")
                    ps_cmd = f"Remove-ItemProperty -Path '{root_str}:\\{approved_key}' -Name '{escaped_item}' -Force -ErrorAction SilentlyContinue"
                    _run_elevated_ps(ps_cmd)
                except Exception:
                    pass

            return True, f"Запись «{target['name']}» успешно удалена из реестра."

        # Папка автозапуска
        if source_type == "startup_folder":
            folder = Path(target.get("location", ""))
            file_path = folder / target["raw_name"]
            try:
                if file_path.exists():
                    file_path.unlink()
                return True, f"Файл «{target['raw_name']}» успешно удален из автозапуска."
            except Exception as e:
                return False, f"Не удалось удалить файл: {e}"

        # Планировщик задач
        if source_type == "scheduled_task":
            task_name = target["raw_name"]
            res = subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
                text=True,
                encoding="cp866",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                return True, f"Задача «{target['name']}» успешно удалена из планировщика."

            err_output = (res.stderr or "") + " " + (res.stdout or "")
            if any(w in err_output.lower() for w in ["доступ", "denied", "администр", "privilege"]):
                ps_cmd = f"schtasks /delete /tn '{task_name}' /f"
                if _run_elevated_ps(ps_cmd):
                    return True, f"Задача «{target['name']}» успешно удалена из планировщика."

            return False, f"Ошибка удаления задачи: {res.stderr.strip() or res.stdout.strip()}"

        return False, "Неподдерживаемый тип записи для удаления."

    @classmethod
    def open_folder(cls, item_id: str) -> tuple[bool, str]:
        """Открывает папку с исполняемым файлом или ярлыком в Проводнике Windows с подсветкой файла."""
        all_items = cls.get_all_items()
        target = next((item for item in all_items if item["id"] == item_id), None)
        if not target:
            return False, "Элемент не найден."

        file_path = target.get("file_path") or target.get("command")
        if file_path and os.path.exists(file_path):
            try:
                subprocess.Popen(f'explorer.exe /select,"{file_path}"')
                return True, f"Папка открыта: {file_path}"
            except Exception as e:
                return False, f"Ошибка открытия Проводника: {e}"

        # Если файл не существует, пробуем открыть папку автозапуска
        if target.get("source_type") == "startup_folder":
            loc = target.get("location")
            if loc and os.path.exists(loc):
                try:
                    os.startfile(loc)
                    return True, f"Открыта папка: {loc}"
                except Exception as e:
                    return False, str(e)

        return False, f"Файл не найден на диске: {file_path}"

    @classmethod
    def add_custom_item(cls, name: str, exe_path: str, args: str = "") -> tuple[bool, str]:
        """Добавляет исполняемый файл в автозагрузку пользователя (HKCU Run)."""
        name = name.strip()
        exe_path = exe_path.strip().strip('"')
        args = args.strip()

        if not name:
            return False, "Укажите название программы."
        if not exe_path or not os.path.exists(exe_path):
            return False, f"Указанный файл не существует: {exe_path}"

        full_cmd = f'"{exe_path}"'
        if args:
            full_cmd += f" {args}"

        sub_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, full_cmd)
            return True, f"Программа «{name}» успешно добавлена в автозапуск!"
        except Exception as e:
            return False, f"Не удалось добавить запись в реестр: {e}"
