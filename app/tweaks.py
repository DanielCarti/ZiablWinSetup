"""
ZiablWinSetup — Модуль системных твиков и полезных фичей для программ.
Предоставляет безопасное включение, отключение и проверку статуса полезных настроек.
Все фоновые вызовы изолированы и никогда не открывают консольных окон.
"""

import ctypes
from ctypes import wintypes
import os
import re
import shutil
import subprocess
import sys
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.utils import get_clean_env

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


@dataclass
class TweakEntry:
    id: str
    name: str
    name_en: str
    description: str
    description_en: str
    category: str
    icon: str
    is_applied: Callable[[], bool]
    apply: Callable[[], tuple[bool, str]]
    revert: Callable[[], tuple[bool, str]]
    type: str = "toggle"  # "toggle" (Вкл/Выкл) или "action" (Очистить/Выполнить)
    action_text: str = ""
    action_text_en: str = ""
    is_available: Callable[[], bool] = lambda: True
    unavailable_reason: str = ""
    unavailable_reason_en: str = ""

    def to_dict(self, lang: str = "ru") -> dict:
        available = self.is_available()
        return {
            "id": self.id,
            "name": self.name if lang != "en" else self.name_en,
            "description": self.description if lang != "en" else self.description_en,
            "category": self.category,
            "icon": self.icon,
            "applied": self.is_applied() if available else False,
            "available": available,
            "unavailable_reason": (self.unavailable_reason if lang != "en" else self.unavailable_reason_en) if not available else "",
            "type": self.type,
            "action_text": (self.action_text if lang != "en" else self.action_text_en) if self.action_text else "",
        }


def _restart_explorer():
    """Перезапуск explorer.exe с чистым окружением (без переменных PyInstaller _MEI)."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "explorer.exe"], capture_output=True, creationflags=NO_WINDOW)
        import time
        time.sleep(0.5)
        # Запуск через WMI Win32_Process Create гарантирует чистую интерактивную сессию пользователя без наследования _MEI
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='explorer.exe'}"],
            capture_output=True,
            creationflags=NO_WINDOW,
        )
    except Exception:
        pass


def _is_win11() -> bool:
    """Проверяет, работает ли система под управлением Windows 11 (билд 22000+)."""
    try:
        ver = sys.getwindowsversion()
        return ver.major >= 10 and ver.build >= 22000
    except Exception:
        return True


def _is_torrent_available() -> bool:
    """Проверяет, установлен ли BitTorrent или uTorrent на компьютере пользователя."""
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "C:\\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    for client in ["BitTorrent", "uTorrent"]:
        if (Path(appdata) / client).exists():
            return True
        if (Path(localappdata) / client).exists():
            return True
        if (Path(pf) / client).exists() or (Path(pfx86) / client).exists():
            return True
    return False


# ==========================================
# 1. ТВИК: Отключение рекламы в uTorrent и BitTorrent
# ==========================================

def _bdecode(data: bytes):
    """Декодирует данные формата Bencode в структуры Python."""
    def decode_val(idx: int):
        b = data[idx:idx+1]
        if b == b"i":
            end = data.index(b"e", idx)
            return int(data[idx+1:end]), end + 1
        elif b == b"l":
            res = []
            idx += 1
            while data[idx:idx+1] != b"e":
                val, idx = decode_val(idx)
                res.append(val)
            return res, idx + 1
        elif b == b"d":
            res = {}
            idx += 1
            while data[idx:idx+1] != b"e":
                key, idx = decode_val(idx)
                val, idx = decode_val(idx)
                res[key] = val
            return res, idx + 1
        elif b.isdigit():
            colon = data.index(b":", idx)
            length = int(data[idx:colon])
            start = colon + 1
            return data[start:start+length], start + length
        raise ValueError(f"Unknown bencode byte {b} at {idx}")
    val, _ = decode_val(0)
    return val


def _bencode(val: Any) -> bytes:
    """Кодирует структуры Python в формат Bencode."""
    if isinstance(val, int):
        return b"i" + str(val).encode("ascii") + b"e"
    elif isinstance(val, bytes):
        return str(len(val)).encode("ascii") + b":" + val
    elif isinstance(val, str):
        b = val.encode("utf-8")
        return str(len(b)).encode("ascii") + b":" + b
    elif isinstance(val, list):
        return b"l" + b"".join(_bencode(x) for x in val) + b"e"
    elif isinstance(val, dict):
        items = sorted(val.items(), key=lambda kv: kv[0] if isinstance(kv[0], bytes) else str(kv[0]).encode("utf-8"))
        res = [b"d"]
        for k, v in items:
            res.append(_bencode(k))
            res.append(_bencode(v))
        res.append(b"e")
        return b"".join(res)
    raise TypeError(f"Unsupported bencode type {type(val)}")


def _check_torrent_ads_applied() -> bool:
    appdata = os.environ.get("APPDATA", "")
    checked_any = False
    for client in ["BitTorrent", "uTorrent"]:
        settings_file = Path(appdata) / client / "settings.dat"
        if settings_file.exists():
            checked_any = True
            try:
                data = settings_file.read_bytes()
                d = _bdecode(data)
                if isinstance(d, dict):
                    # Если adUrl пустой и основные флаги рекламы сброшены в 0
                    ad_url = d.get(b"offers.adUrl", None)
                    left_rail = d.get(b"offers.left_rail_offer_enabled", 1)
                    upsell = d.get(b"gui.show_plus_upsell", 1)
                    if ad_url == b"" or (left_rail == 0 and upsell == 0):
                        return True
            except Exception:
                pass
    return False


def _apply_torrent_ads() -> tuple[bool, str]:
    appdata = os.environ.get("APPDATA", "")
    for proc in ["bittorrent.exe", "utorrent.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True, creationflags=NO_WINDOW)

    found_clients = []
    for client in ["BitTorrent", "uTorrent"]:
        c_dir = Path(appdata) / client
        settings_file = c_dir / "settings.dat"
        if settings_file.exists():
            try:
                data = settings_file.read_bytes()
                bak_file = c_dir / "settings.dat.bak"
                if not bak_file.exists():
                    shutil.copy2(settings_file, bak_file)

                d = _bdecode(data)
                if not isinstance(d, dict):
                    continue

                # Отключаем все рекламные URL и баннеры
                d[b"offers.adUrl"] = b""
                d[b"offers.featured_content_url"] = b""
                d[b"offers.tronTV_url"] = b""
                d[b"offers.left_rail_offer_enabled"] = 0
                d[b"offers.sponsored_torrent_offer_enabled"] = 0
                d[b"gui.show_plus_upsell"] = 0
                d[b"gui.plus_upsell_foreground"] = 0
                d[b"gui.show_notices"] = 0
                d[b"offers.content_offer_autoexec"] = 0
                d[b"bt.enable_pulse"] = 0
                d[b"offers.featured_content_badge_enabled"] = 0
                d[b"offers.featured_content_notifications_enabled"] = 0
                d[b"offers.featured_content_rss_enabled"] = 0
                # Удаляем старый .fileguard хеш, чтобы клиент принял измененные настройки и пересчитал хеш
                d.pop(b".fileguard", None)

                encoded = _bencode(d)
                settings_file.write_bytes(encoded)

                old_file = c_dir / "settings.dat.old"
                if old_file.exists():
                    try:
                        old_d = _bdecode(old_file.read_bytes())
                        if isinstance(old_d, dict):
                            old_d[b"offers.adUrl"] = b""
                            old_d[b"offers.left_rail_offer_enabled"] = 0
                            old_d[b"offers.sponsored_torrent_offer_enabled"] = 0
                            old_d[b"gui.show_plus_upsell"] = 0
                            old_d.pop(b".fileguard", None)
                            old_file.write_bytes(_bencode(old_d))
                    except Exception:
                        pass

                found_clients.append(client)
            except Exception as e:
                return False, f"Ошибка записи настроек {client}: {e}"

    if not found_clients:
        return False, "Клиенты BitTorrent или uTorrent не найдены в системе."
    return True, f"Реклама успешно отключена для: {', '.join(found_clients)}!"


def _revert_torrent_ads() -> tuple[bool, str]:
    appdata = os.environ.get("APPDATA", "")
    for proc in ["bittorrent.exe", "utorrent.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True, creationflags=NO_WINDOW)

    restored = []
    for client in ["BitTorrent", "uTorrent"]:
        c_dir = Path(appdata) / client
        settings_file = c_dir / "settings.dat"
        bak_file = c_dir / "settings.dat.bak"

        if bak_file.exists():
            try:
                shutil.copy2(bak_file, settings_file)
                bak_file.unlink(missing_ok=True)
                restored.append(client)
                continue
            except Exception:
                pass

        if settings_file.exists():
            try:
                data = settings_file.read_bytes()
                d = _bdecode(data)
                if isinstance(d, dict):
                    d[b"offers.adUrl"] = b"https://video.rainberrytv.com/utclassic/wrapper.html?bucket=classic-row+display"
                    d[b"offers.featured_content_url"] = b"http://trontv.com/#!/?p=classic"
                    d[b"offers.tronTV_url"] = b"http://trontv.com/#!/?p=classic"
                    d[b"offers.left_rail_offer_enabled"] = 1
                    d[b"offers.sponsored_torrent_offer_enabled"] = 1
                    d[b"gui.show_plus_upsell"] = 1
                    d[b"gui.plus_upsell_foreground"] = 1
                    d.pop(b".fileguard", None)
                    settings_file.write_bytes(_bencode(d))
                    restored.append(client)
            except Exception:
                pass

    if not restored:
        return False, "Клиенты BitTorrent или uTorrent не найдены."
    return True, f"Оригинальные настройки рекламы восстановлены для: {', '.join(restored)}."


# ==========================================
# 2. ТВИК: Классическое меню Windows 11
# ==========================================

_WIN11_MENU_KEY = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"

def _check_classic_menu() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN11_MENU_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "")
            return True
    except OSError:
        return False


def _apply_classic_menu() -> tuple[bool, str]:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN11_MENU_KEY) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "")
        _restart_explorer()
        return True, "Классическое контекстное меню Windows 11 включено!"
    except Exception as e:
        return False, f"Ошибка: {e}"


def _revert_classic_menu() -> tuple[bool, str]:
    try:
        root_clsid = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _WIN11_MENU_KEY)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, root_clsid)
        _restart_explorer()
        return True, "Стандартное меню Windows 11 восстановлено."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ==========================================
# 3. ТВИК: Отображение расширений файлов
# ==========================================

_EXPLORER_ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"

def _check_file_ext() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADVANCED_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "HideFileExt")
            return val == 0
    except OSError:
        return False


def _apply_file_ext() -> tuple[bool, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADVANCED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "HideFileExt", 0, winreg.REG_DWORD, 0)
        _restart_explorer()
        return True, "Отображение расширений файлов включено!"
    except Exception as e:
        return False, f"Ошибка: {e}"


def _revert_file_ext() -> tuple[bool, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADVANCED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "HideFileExt", 0, winreg.REG_DWORD, 1)
        _restart_explorer()
        return True, "Расширения файлов скрыты."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ==========================================
# 4. ТВИК: Схема «Максимальная производительность» (Ultimate Performance)
# ==========================================

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _get_active_power_scheme_info() -> tuple[str, str]:
    """Возвращает (guid, friendly_name) активной схемы электропитания через Win32 API."""
    try:
        powrprof = ctypes.windll.powrprof
        pActiveGuid = ctypes.POINTER(_GUID)()
        if powrprof.PowerGetActiveScheme(None, ctypes.byref(pActiveGuid)) == 0 and pActiveGuid:
            g = pActiveGuid.contents
            guid_str = f"{g.Data1:08x}-{g.Data2:04x}-{g.Data3:04x}-" + "".join(f"{b:02x}" for b in g.Data4[:2]) + "-" + "".join(f"{b:02x}" for b in g.Data4[2:])
            buf_size = wintypes.DWORD(512)
            buf = (ctypes.c_byte * 512)()
            name = ""
            if powrprof.PowerReadFriendlyName(None, pActiveGuid, None, None, buf, ctypes.byref(buf_size)) == 0:
                name = ctypes.wstring_at(buf)
            return guid_str.lower(), name.lower()
    except Exception:
        pass

    # Fallback to powercfg
    try:
        res = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, creationflags=NO_WINDOW)
        out = res.stdout.decode("cp866", errors="ignore")
        m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", out)
        guid_str = m.group(1).lower() if m else ""
        return guid_str, out.lower()
    except Exception:
        return "", ""


def _find_ultimate_perf_guid() -> str:
    """Ищет существующий GUID схемы 'Максимальная производительность' в системе."""
    try:
        res = subprocess.run(["powercfg", "/list"], capture_output=True, creationflags=NO_WINDOW)
        out = res.stdout.decode("cp866", errors="ignore")
        for line in out.splitlines():
            line_l = line.lower()
            if any(k in line_l for k in ["максимальная", "ultimate"]):
                m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", line)
                if m:
                    return m.group(1).lower()
    except Exception:
        pass
    return ""


def _check_ultimate_perf() -> bool:
    guid, name = _get_active_power_scheme_info()
    if any(k in name for k in ["максимальная", "ultimate"]):
        return True
    return False


def _apply_ultimate_perf() -> tuple[bool, str]:
    try:
        target_guid = _find_ultimate_perf_guid()
        if not target_guid:
            # Duplicate Microsoft Ultimate Performance template scheme
            res = subprocess.run(
                ["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61"],
                capture_output=True,
                creationflags=NO_WINDOW,
            )
            out = res.stdout.decode("cp866", errors="ignore")
            m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", out)
            if m:
                target_guid = m.group(1).lower()
            else:
                target_guid = _find_ultimate_perf_guid()

        if not target_guid:
            return False, "Не удалось сгенерировать схему максимальной производительности."

        # Activate the scheme
        act_res = subprocess.run(
            ["powercfg", "-setactive", target_guid],
            capture_output=True,
            creationflags=NO_WINDOW,
        )
        if act_res.returncode == 0 or _check_ultimate_perf():
            return True, "Схема «Максимальная производительность» успешно активирована!"
        return False, f"Не удалось активировать схему {target_guid}."
    except Exception as e:
        return False, f"Ошибка активации: {e}"


def _revert_ultimate_perf() -> tuple[bool, str]:
    try:
        # Reset to Balanced (381b4222-f694-41f0-9685-ff5bb260df2e) silently
        subprocess.run(
            ["powercfg", "-setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"],
            capture_output=True,
            creationflags=NO_WINDOW,
        )
        return True, "Схема питания переключена на сбалансированную."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ==========================================
# 5. ТВИК: Отключение рекламы и подсказок в меню «Пуск»
# ==========================================

_CONTENT_DELIVERY_KEY = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"

def _check_disable_start_ads() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CONTENT_DELIVERY_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "SystemPaneSuggestionsEnabled")
            return val == 0
    except OSError:
        return False


def _apply_disable_start_ads() -> tuple[bool, str]:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CONTENT_DELIVERY_KEY) as key:
            winreg.SetValueEx(key, "SystemPaneSuggestionsEnabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "SubscribedContent-338388Enabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "SubscribedContent-338389Enabled", 0, winreg.REG_DWORD, 0)
        return True, "Реклама и предложения в меню «Пуск» отключены!"
    except Exception as e:
        return False, f"Ошибка: {e}"


def _revert_disable_start_ads() -> tuple[bool, str]:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CONTENT_DELIVERY_KEY) as key:
            winreg.SetValueEx(key, "SystemPaneSuggestionsEnabled", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "SubscribedContent-338388Enabled", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "SubscribedContent-338389Enabled", 0, winreg.REG_DWORD, 1)
        return True, "Стандартные подсказки меню «Пуск» включены."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ==========================================
# 6. ОЧИСТКА: Кэш Steam (загрузки, шейдеры, веб-кэш)
# ==========================================

def _find_steam_path() -> Path | None:
    # 1. Registry HKCU
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            val, _ = winreg.QueryValueEx(k, "SteamPath")
            p = Path(val)
            if p.exists():
                return p
    except Exception:
        pass
    # 2. Common drive paths
    for drive in ["C:", "D:", "E:", "F:"]:
        p = Path(f"{drive}/Program Files (x86)/Steam")
        if p.exists():
            return p
        p = Path(f"{drive}/Steam")
        if p.exists():
            return p
    return None


def _clean_steam_cache() -> tuple[bool, str]:
    steam_path = _find_steam_path()
    local_steam = Path(os.environ.get("LOCALAPPDATA", "")) / "Steam"

    if not steam_path and not local_steam.exists():
        return False, "Клиент Steam не найден в системе."

    subprocess.run(["taskkill", "/F", "/IM", "steam.exe"], capture_output=True, creationflags=NO_WINDOW)

    freed = 0
    files_deleted = 0

    targets: list[Path] = []
    if steam_path and steam_path.exists():
        targets.extend([
            steam_path / "appcache",
            steam_path / "steamapps" / "downloading",
            steam_path / "steamapps" / "temp",
            steam_path / "steamapps" / "shadercache",
            steam_path / "dumps",
        ])
    if local_steam.exists():
        targets.extend([
            local_steam / "htmlcache",
            local_steam / "widevine",
        ])

    for target in targets:
        if target.exists():
            for f in list(target.glob("**/*")):
                if f.is_file():
                    try:
                        sz = f.stat().st_size
                        f.unlink()
                        freed += sz
                        files_deleted += 1
                    except Exception:
                        pass

    mb = round(freed / (1024 * 1024), 1)
    return True, f"Кэш Steam очищен! Освобождено {mb} МБ ({files_deleted} файлов)."


# ==========================================
# 7. ОЧИСТКА: Кэш медиа Telegram (все аккаунты + WebView)
# ==========================================

def _clean_telegram_cache() -> tuple[bool, str]:
    appdata = os.environ.get("APPDATA", "")
    tdata = Path(appdata) / "Telegram Desktop" / "tdata"
    if not tdata.exists():
        return False, "Папка Telegram Desktop не найдена."

    subprocess.run(["taskkill", "/F", "/IM", "Telegram.exe"], capture_output=True, creationflags=NO_WINDOW)

    freed = 0
    files_deleted = 0

    # Scan user_data, user_data#2, user_data#3, etc.
    user_data_dirs = list(tdata.glob("user_data*"))
    if not user_data_dirs:
        user_data_dirs = [tdata / "user_data"]

    targets = []
    for ud in user_data_dirs:
        targets.extend([
            ud / "cache",
            ud / "media_cache",
            ud / "wvbots",
            ud / "wvother",
        ])
    targets.extend([
        tdata / "temp",
        tdata / "dumps",
    ])

    for target in targets:
        if target.exists():
            for f in list(target.glob("**/*")):
                if f.is_file():
                    try:
                        sz = f.stat().st_size
                        f.unlink()
                        freed += sz
                        files_deleted += 1
                    except Exception:
                        pass

    mb = round(freed / (1024 * 1024), 1)
    return True, f"Медиа-кэш Telegram очищен! Освобождено {mb} МБ ({files_deleted} файлов)."


def _clean_winsetup_installers() -> tuple[bool, str]:
    """
    Удаляет все .exe, .msi, .zip и дистрибутивы, скачанные нашей программой (ZiablWinSetup).
    Очищает временный кэш WinSetup_Downloads и WinSetup_Winget,
    а также удаляет временные файлы автообновления и старые/дублирующие копии самой ZiablWinSetup
    (.old, .bak, ZiablWinSetup (1).exe в папке приложения и Downloads),
    никогда не затрагивая текущий запущенный экземпляр программы.
    """
    import os
    import re
    import sys
    import tempfile
    from app.utils import get_download_dir, format_size

    try:
        running_exe = Path(sys.executable).resolve()
    except Exception:
        running_exe = None

    temp_root = Path(tempfile.gettempdir())
    dirs_to_clean = [
        get_download_dir(),  # WinSetup_Downloads
        temp_root / "WinSetup_Winget",
    ]
    deleted_files = 0
    total_freed = 0

    # 1. Кэш установщиков WinSetup_Downloads и WinSetup_Winget
    for d in dirs_to_clean:
        if not d.exists():
            continue
        for item in list(d.rglob("*")):
            if item.is_file():
                try:
                    if running_exe and item.resolve() == running_exe:
                        continue
                    sz = item.stat().st_size
                    item.unlink(missing_ok=True)
                    deleted_files += 1
                    total_freed += sz
                except Exception:
                    pass
        for item in sorted(list(d.rglob("*")), key=lambda p: len(str(p)), reverse=True):
            if item.is_dir():
                try:
                    item.rmdir()
                except Exception:
                    pass

    # 2. Временные файлы автообновления ZiablWinSetup в %TEMP%
    try:
        for item in temp_root.iterdir():
            if not item.is_file():
                continue
            name_lower = item.name.lower()
            if (name_lower.startswith("ziablwinsetup_new_") or 
                name_lower.startswith("ziabl_update_") or 
                name_lower.startswith("ziablwinsetup_setup_")):
                try:
                    if running_exe and item.resolve() == running_exe:
                        continue
                    sz = item.stat().st_size
                    item.unlink(missing_ok=True)
                    deleted_files += 1
                    total_freed += sz
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Старые копии и дубликаты ZiablWinSetup (.old, .bak, (1).exe, копия) в Downloads и папке запуска
    search_dirs = set()
    try:
        search_dirs.add(Path.home() / "Downloads")
    except Exception:
        pass
    if running_exe:
        try:
            exe_dir = running_exe.parent
            if exe_dir.exists():
                search_dirs.add(exe_dir)
        except Exception:
            pass

    dup_pattern = re.compile(r"^ziablwinsetup.*\s*(\(\d+\)|[-_]copy|[-_]копия)\.exe$", re.IGNORECASE)
    old_exts = {".old", ".bak", ".tmp"}

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        try:
            for item in s_dir.iterdir():
                if not item.is_file():
                    continue
                name_lower = item.name.lower()
                if not name_lower.startswith("ziablwinsetup"):
                    continue

                # Абсолютная защита: никогда не удалять текущий запущенный exe
                try:
                    if running_exe and item.resolve() == running_exe:
                        continue
                except Exception:
                    continue

                should_delete = False
                # Старые версии и бэкапы: ZiablWinSetup.exe.old, ZiablWinSetup.old, ZiablWinSetup.bak
                if any(name_lower.endswith(ext) for ext in old_exts):
                    should_delete = True
                # Дубликаты скачиваний: ZiablWinSetup (1).exe, ZiablWinSetup - копия.exe
                elif dup_pattern.match(name_lower):
                    should_delete = True

                if should_delete:
                    try:
                        sz = item.stat().st_size
                        item.unlink(missing_ok=True)
                        deleted_files += 1
                        total_freed += sz
                    except Exception:
                        pass
        except Exception:
            pass

    if deleted_files == 0:
        return True, "Кэш установщиков уже пуст (файлы .exe и старые копии не найдены)."
    return True, f"Успешно удалено {deleted_files} файлов инсталляторов и старых копий (освобождено {format_size(total_freed)} памяти)."


# ==========================================
# 8. ТВИК: Отключение индексации (Windows Search) для SSD
# ==========================================

_WSEARCH_KEY = r"SYSTEM\CurrentControlSet\Services\WSearch"


def _check_indexing_disabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WSEARCH_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "Start")
            return val == 4
    except Exception:
        try:
            res = subprocess.run(["sc.exe", "qc", "WSearch"], capture_output=True, text=True, creationflags=NO_WINDOW)
            return "DISABLED" in res.stdout.upper()
        except Exception:
            return False


def _apply_indexing_disabled() -> tuple[bool, str]:
    try:
        subprocess.run(["sc.exe", "stop", "WSearch"], capture_output=True, creationflags=NO_WINDOW)
        res = subprocess.run(["sc.exe", "config", "WSearch", "start=disabled"], capture_output=True, text=True, creationflags=NO_WINDOW)
        if res.returncode == 0 or _check_indexing_disabled():
            return True, "Служба индексации (Windows Search) отключена. Нагрузка на SSD снижена!"
        cmd = "sc.exe stop WSearch && sc.exe config WSearch start=disabled"
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {cmd}", None, 0)
        if ret > 32:
            return True, "Запрос на отключение службы индексации отправлен с правами Администратора."
        return False, "Не удалось изменить конфигурацию службы (требуются права администратора)."
    except Exception as e:
        return False, f"Ошибка отключения индексации: {e}"


def _revert_indexing_disabled() -> tuple[bool, str]:
    try:
        res = subprocess.run(["sc.exe", "config", "WSearch", "start=delayed-auto"], capture_output=True, text=True, creationflags=NO_WINDOW)
        subprocess.run(["sc.exe", "start", "WSearch"], capture_output=True, creationflags=NO_WINDOW)
        if res.returncode == 0 or not _check_indexing_disabled():
            return True, "Служба индексации (Windows Search) включена в автозапуск и запущена."
        cmd = "sc.exe config WSearch start=delayed-auto && sc.exe start WSearch"
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {cmd}", None, 0)
        if ret > 32:
            return True, "Запрос на включение службы индексации отправлен с правами Администратора."
        return False, "Не удалось запустить службу индексации."
    except Exception as e:
        return False, f"Ошибка включения индексации: {e}"


# ==========================================
# 9. ТВИК: Скрыть строку поиска на панели задач
# ==========================================

_SEARCHBOX_KEY = r"Software\Microsoft\Windows\CurrentVersion\Search"


def _check_taskbar_search_hidden() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SEARCHBOX_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "SearchboxTaskbarMode")
            return val == 0
    except Exception:
        return False


def _apply_taskbar_search_hidden() -> tuple[bool, str]:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SEARCHBOX_KEY) as key:
            winreg.SetValueEx(key, "SearchboxTaskbarMode", 0, winreg.REG_DWORD, 0)
        _restart_explorer()
        return True, "Строка поиска на панели задач скрыта."
    except Exception as e:
        return False, f"Ошибка изменения реестра: {e}"


def _revert_taskbar_search_hidden() -> tuple[bool, str]:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SEARCHBOX_KEY) as key:
            # Режим 2 — полноценное «Поле поиска» (Search box)
            winreg.SetValueEx(key, "SearchboxTaskbarMode", 0, winreg.REG_DWORD, 2)
        _restart_explorer()
        return True, "Отображение поиска (поле поиска) на панели задач восстановлено."
    except Exception as e:
        return False, f"Ошибка изменения реестра: {e}"


# ==========================================
# 10. ТВИК: Кнопка Пуск и значки панели задач слева (Windows 11)
# ==========================================

_EXPLORER_ADV_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


def _check_taskbar_align_left() -> bool:
    if not _is_win11():
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADV_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "TaskbarAl")
            return val == 0
    except Exception:
        return False


def _apply_taskbar_align_left() -> tuple[bool, str]:
    if not _is_win11():
        return False, "Панель задач уже выровнена по левому краю в этой версии Windows."
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADV_KEY) as key:
            winreg.SetValueEx(key, "TaskbarAl", 0, winreg.REG_DWORD, 0)
        return True, "Кнопка «Пуск» и значки перемещены в левый угол панели задач."
    except Exception as e:
        return False, f"Ошибка изменения реестра: {e}"


def _revert_taskbar_align_left() -> tuple[bool, str]:
    if not _is_win11():
        return False, "Действие доступно только в Windows 11."
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _EXPLORER_ADV_KEY) as key:
            winreg.SetValueEx(key, "TaskbarAl", 0, winreg.REG_DWORD, 1)
        return True, "Панель задач возвращена в центр."
    except Exception as e:
        return False, f"Ошибка изменения реестра: {e}"


def get_sfc_status_file() -> Path:
    import tempfile
    return Path(tempfile.gettempdir()) / "ziabl_sfc_status.txt"


def get_dism_status_file() -> Path:
    import tempfile
    return Path(tempfile.gettempdir()) / "ziabl_dism_status.txt"


def _run_sfc_scan() -> tuple[bool, str, str]:
    """Запуск проверки целостности системных файлов Windows (sfc /scannow)."""
    try:
        sf = get_sfc_status_file()
        try:
            sf.unlink(missing_ok=True)
        except Exception:
            pass
        sf_str = str(sf.resolve()).replace("/", "\\")

        title = "ZiablWinSetup - System File Checker (sfc /scannow)"
        cmd = (
            f'title {title} && color 0b && '
            f'echo ======================================================== && '
            f'echo [ZiablWinSetup] System File Checker (sfc /scannow) && '
            f'echo Scans and repairs integrity of Windows system files && '
            f'echo ======================================================== && echo. && '
            f'sfc.exe /scannow & (if errorlevel 1 (echo COMPLETED_REPAIRED > "{sf_str}") else (echo COMPLETED_SUCCESS > "{sf_str}")) && '
            f'echo. && echo -------------------------------------------------------- && '
            f'echo Scan finished. Press any key to exit... && pause >nul'
        )
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c "{cmd}"', None, 1)
        if ret > 32:
            return (
                True,
                "⏳ Консоль sfc /scannow запущена от имени Администратора. Ожидание завершения...",
                "⏳ sfc /scannow console launched as Administrator. Waiting for completion...",
            )
        return (
            False,
            "Не удалось запустить sfc /scannow (требуются права администратора).",
            "Failed to launch sfc /scannow (Administrator rights required).",
        )
    except Exception as e:
        return False, f"Ошибка запуска sfc /scannow: {e}", f"Error launching sfc /scannow: {e}"


def _run_dism_restore_health() -> tuple[bool, str, str]:
    """Восстановление хранилища компонентов Windows через DISM /Online /Cleanup-Image /RestoreHealth."""
    try:
        df = get_dism_status_file()
        try:
            df.unlink(missing_ok=True)
        except Exception:
            pass
        df_str = str(df.resolve()).replace("/", "\\")

        title = "ZiablWinSetup - Restore Component Store Health (DISM)"
        cmd = (
            f'title {title} && color 0a && '
            f'echo ======================================================== && '
            f'echo [ZiablWinSetup] Component Store Health Restore (DISM) && '
            f'echo Repairs Windows system image component corruption && '
            f'echo ======================================================== && echo. && '
            f'dism.exe /Online /Cleanup-Image /RestoreHealth & (if errorlevel 1 (echo COMPLETED_ERROR > "{df_str}") else (echo COMPLETED_SUCCESS > "{df_str}")) && '
            f'echo. && echo -------------------------------------------------------- && '
            f'echo Restore finished. Press any key to exit... && pause >nul'
        )
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c "{cmd}"', None, 1)
        if ret > 32:
            return (
                True,
                "⏳ Консоль DISM RestoreHealth запущена от имени Администратора. Ожидание завершения...",
                "⏳ DISM RestoreHealth console launched as Administrator. Waiting for completion...",
            )
        return (
            False,
            "Не удалось запустить DISM RestoreHealth (требуются права администратора).",
            "Failed to launch DISM RestoreHealth (Administrator rights required).",
        )
    except Exception as e:
        return False, f"Ошибка запуска DISM RestoreHealth: {e}", f"Error launching DISM RestoreHealth: {e}"


# ==========================================
# РЕЕСТР ВСЕХ ТВproperties
# ==========================================

TWEAKS: list[TweakEntry] = [
    TweakEntry(
        id="torrent_ads",
        name="Отключение рекламы в BitTorrent и uTorrent",
        name_en="Disable BitTorrent & uTorrent Ads",
        description="Полностью выключает рекламные баннеры, всплывающие видео и спонсорские блоки в интерфейсе торрент-клиента без сторонних программ.",
        description_en="Completely disables ad banners, video popups, and sponsored content in BitTorrent and uTorrent without third-party patches.",
        category="apps",
        icon="🚫",
        is_applied=_check_torrent_ads_applied,
        apply=_apply_torrent_ads,
        revert=_revert_torrent_ads,
        type="toggle",
        is_available=_is_torrent_available,
        unavailable_reason="BitTorrent или uTorrent не установлены",
        unavailable_reason_en="Neither BitTorrent nor uTorrent is installed",
    ),
    TweakEntry(
        id="win11_classic_menu",
        name="Классическое контекстное меню Windows 11",
        name_en="Windows 11 Classic Context Menu",
        description="Возвращает полноценное меню по правому клику мыши без необходимости нажимать «Показать дополнительные параметры».",
        description_en="Restores full right-click context menu without needing to click 'Show more options'.",
        category="system",
        icon="🪟",
        is_applied=_check_classic_menu,
        apply=_apply_classic_menu,
        revert=_revert_classic_menu,
        type="toggle",
        is_available=_is_win11,
        unavailable_reason="Доступно только в Windows 11",
        unavailable_reason_en="Available on Windows 11 only",
    ),
    TweakEntry(
        id="taskbar_align_left",
        name="Кнопка «Пуск» слева (как в Windows 10)",
        name_en="Align Start Button to Left",
        description="Перемещает кнопку «Пуск» и значки панели задач в левый угол, возвращая привычный классический вид Windows 10.",
        description_en="Moves the Start button and taskbar icons to the left corner, restoring the classic Windows 10 layout.",
        category="system",
        icon="📌",
        is_applied=_check_taskbar_align_left,
        apply=_apply_taskbar_align_left,
        revert=_revert_taskbar_align_left,
        type="toggle",
        is_available=_is_win11,
        unavailable_reason="Доступно только в Windows 11",
        unavailable_reason_en="Available on Windows 11 only",
    ),
    TweakEntry(
        id="hide_taskbar_search",
        name="Скрыть строку поиска на панели задач",
        name_en="Hide Taskbar Search Box",
        description="Убирает громоздкое поле поиска с панели задач, освобождая полезное место для открытых окон и программ.",
        description_en="Hides the bulky search box from the taskbar, freeing up space for active window icons.",
        category="system",
        icon="🔍",
        is_applied=_check_taskbar_search_hidden,
        apply=_apply_taskbar_search_hidden,
        revert=_revert_taskbar_search_hidden,
        type="toggle",
    ),
    TweakEntry(
        id="disable_indexing_ssd",
        name="Отключение службы индексации (для SSD)",
        name_en="Disable Search Indexing (for SSD)",
        description="Отключает постоянное фоновое чтение и запись индексатора Windows Search. Продлевает ресурс ячеек SSD (TBW) и снижает нагрузку на CPU.",
        description_en="Disables background Windows Search indexing service to preserve SSD write endurance (TBW) and reduce background CPU usage.",
        category="perf",
        icon="⚡",
        is_applied=_check_indexing_disabled,
        apply=_apply_indexing_disabled,
        revert=_revert_indexing_disabled,
        type="toggle",
    ),
    TweakEntry(
        id="show_file_ext",
        name="Отображение расширений файлов",
        name_en="Show File Extensions",
        description="Показывает реальные расширения файлов (.exe, .bat, .zip) в Проводнике Windows для безопасности и защиты от вирусов.",
        description_en="Shows file extensions in Windows Explorer for better security and awareness.",
        category="system",
        icon="📁",
        is_applied=_check_file_ext,
        apply=_apply_file_ext,
        revert=_revert_file_ext,
        type="toggle",
    ),
    TweakEntry(
        id="ultimate_perf",
        name="Схема «Максимальная производительность»",
        name_en="Ultimate Performance Power Plan",
        description="Активирует скрытую схему питания от Microsoft, отключающую задержки троттлинга процессора для максимального отклика в играх.",
        description_en="Activates Microsoft hidden Ultimate Performance plan to minimize CPU latencies.",
        category="perf",
        icon="🚀",
        is_applied=_check_ultimate_perf,
        apply=_apply_ultimate_perf,
        revert=_revert_ultimate_perf,
        type="toggle",
    ),
    TweakEntry(
        id="disable_start_ads",
        name="Отключение рекламы в меню «Пуск»",
        name_en="Disable Start Menu Recommendations",
        description="Отключает рекламу приложений, навязчивые предложения и подсказки в меню «Пуск» Windows 10/11.",
        description_en="Disables app promotions, suggestions, and tips in the Windows Start menu.",
        category="system",
        icon="🔇",
        is_applied=_check_disable_start_ads,
        apply=_apply_disable_start_ads,
        revert=_revert_disable_start_ads,
        type="toggle",
    ),
    TweakEntry(
        id="clean_steam_cache",
        name="Очистить кэш загрузок и шейдеров Steam",
        name_en="Clean Steam Download & Shader Cache",
        description="Устраняет зависания при обновлении и запуске игр в Steam, очищает временный htmlcache, шейдеры и освобождает гигабайты памяти.",
        description_en="Fixes game update/launch stalls in Steam, cleans temporary web and shader cache, and frees disk space.",
        category="cleanup",
        icon="🎮",
        is_applied=lambda: False,
        apply=_clean_steam_cache,
        revert=lambda: (True, "Действие очистки не требует отката."),
        type="action",
        is_available=lambda: bool(_find_steam_path() or (Path(os.environ.get("LOCALAPPDATA", "")) / "Steam").exists()),
        unavailable_reason="Steam не установлен",
        unavailable_reason_en="Steam is not installed",
    ),
    TweakEntry(
        id="clean_telegram_cache",
        name="Очистить медиа-кэш Telegram Desktop",
        name_en="Clean Telegram Media Cache",
        description="Очищает все временные фото, видео, стикеры и кэш встроенных ботов/мини-аппов во всех аккаунтах. Все данные остаются в облаке Telegram.",
        description_en="Cleans cached media, stickers, and mini-apps webview cache across all user accounts. Cloud data is untouched.",
        category="cleanup",
        icon="💬",
        is_applied=lambda: False,
        apply=_clean_telegram_cache,
        revert=lambda: (True, "Действие очистки не требует отката."),
        type="action",
        is_available=lambda: (Path(os.environ.get("APPDATA", "")) / "Telegram Desktop" / "tdata").exists(),
        unavailable_reason="Telegram Desktop не установлен",
        unavailable_reason_en="Telegram Desktop is not installed",
    ),
    TweakEntry(
        id="clean_winsetup_installers",
        name="Очистить скачанные установщики (.exe) и старые копии",
        name_en="Clean Downloaded Installers (.exe) & Old Copies",
        description="Удаляет скачанные инсталляторы программ, временные файлы автообновления и старые/дублирующие копии ZiablWinSetup (.old, (1).exe в Загрузках). Запущенное приложение защищено.",
        description_en="Removes downloaded program installers, update temp files, and old copies/duplicates of ZiablWinSetup (.old, (1).exe). The running app is protected.",
        category="cleanup",
        icon="🗑️",
        is_applied=lambda: False,
        apply=_clean_winsetup_installers,
        revert=lambda: (True, "Действие очистки не требует отката."),
        type="action",
        is_available=lambda: True,
    ),
    TweakEntry(
        id="clean_registry",
        name="Очистка и оптимизация реестра Windows",
        name_en="Clean & Optimize Windows Registry",
        description="Поиск недействительных путей, битых деинсталляторов и устаревшего кэша с созданием резервной копии .reg перед исправлением.",
        description_en="Scans invalid paths, orphaned uninstallers, and obsolete cache with automatic .reg backup before repair.",
        category="cleanup",
        icon="🧹",
        is_applied=lambda: False,
        apply=lambda: (True, "Открыто окно очистки реестра."),
        revert=lambda: (True, "Действие очистки не требует отката."),
        type="action",
        is_available=lambda: True,
    ),
    TweakEntry(
        id="repair_system_files",
        name="Восстановление файлов Windows (sfc /scannow)",
        name_en="System File Checker (sfc /scannow)",
        description="Сканирует целостность всех защищенных системных файлов Windows и автоматически восстанавливает поврежденные или отсутствующие компоненты.",
        description_en="Scans the integrity of all protected Windows system files and repairs corrupted or missing components automatically.",
        category="system",
        icon="🛡️",
        is_applied=lambda: False,
        apply=_run_sfc_scan,
        revert=lambda: (True, "Действие проверки не требует отката."),
        type="action",
        action_text="Запустить сканирование",
        action_text_en="Start Scan",
        is_available=lambda: True,
    ),
    TweakEntry(
        id="restore_health_dism",
        name="Восстановление хранилища компонентов (DISM)",
        name_en="Restore Component Store Health (DISM)",
        description="Запускает DISM /Online /Cleanup-Image /RestoreHealth для устранения повреждений системного образа Windows.",
        description_en="Runs DISM /Online /Cleanup-Image /RestoreHealth to repair Windows system image component store corruption.",
        category="system",
        icon="🩹",
        is_applied=lambda: False,
        apply=_run_dism_restore_health,
        revert=lambda: (True, "Действие восстановления не требует отката."),
        type="action",
        action_text="Восстановить образ",
        action_text_en="Restore Health",
        is_available=lambda: True,
    ),
]


def get_all_tweaks(lang: str = "ru") -> list[dict]:
    return [t.to_dict(lang) for t in TWEAKS]


def apply_tweak_by_id(tweak_id: str, lang: str = "ru") -> dict:
    for t in TWEAKS:
        if t.id == tweak_id:
            res = t.apply()
            if isinstance(res, tuple) and len(res) == 3:
                ok, msg_ru, msg_en = res
                msg = msg_en if lang == "en" else msg_ru
            else:
                ok, msg = res
                msg_ru = msg
                msg_en = msg
            return {
                "success": ok,
                "message": msg,
                "message_ru": msg_ru,
                "message_en": msg_en,
                "applied": t.is_applied(),
                "type": t.type
            }
    return {"success": False, "message": f"Твик '{tweak_id}' не найден."}


def revert_tweak_by_id(tweak_id: str, lang: str = "ru") -> dict:
    for t in TWEAKS:
        if t.id == tweak_id:
            res = t.revert()
            if isinstance(res, tuple) and len(res) == 3:
                ok, msg_ru, msg_en = res
                msg = msg_en if lang == "en" else msg_ru
            else:
                ok, msg = res
                msg_ru = msg
                msg_en = msg
            return {
                "success": ok,
                "message": msg,
                "message_ru": msg_ru,
                "message_en": msg_en,
                "applied": t.is_applied(),
                "type": t.type
            }
    return {"success": False, "message": f"Твик '{tweak_id}' не найден."}
