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
from typing import Callable

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
        }


def _restart_explorer():
    """Перезапуск explorer.exe для немедленного применения твиков проводника."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "explorer.exe"], capture_output=True, creationflags=NO_WINDOW)
        subprocess.Popen(["explorer.exe"], creationflags=NO_WINDOW)
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

def _check_torrent_ads_applied() -> bool:
    appdata = os.environ.get("APPDATA", "")
    checked_any = False
    for client in ["BitTorrent", "uTorrent"]:
        settings_file = Path(appdata) / client / "settings.dat"
        if settings_file.exists():
            checked_any = True
            try:
                data = settings_file.read_bytes()
                if b"offers.left_rail_offer_enabledi1e" in data or b"offers.sponsored_torrent_offer_enabledi1e" in data:
                    return False
                if b"offers.left_rail_offer_enabledi0e" in data and b"offers.sponsored_torrent_offer_enabledi0e" in data:
                    continue
                return False
            except Exception:
                pass
    return checked_any


def _apply_torrent_ads() -> tuple[bool, str]:
    appdata = os.environ.get("APPDATA", "")
    for proc in ["bittorrent.exe", "utorrent.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True, creationflags=NO_WINDOW)

    ad_keys = [
        b"offers.left_rail_offer_enabled",
        b"offers.sponsored_torrent_offer_enabled",
        b"gui.show_plus_upsell",
        b"gui.show_notices",
        b"offers.content_offer_autoexec",
        b"bt.enable_pulse",
        b"offers.featured_content_badge_enabled",
        b"offers.featured_content_notifications_enabled",
        b"offers.featured_content_rss_enabled",
    ]

    found_clients = []
    for client in ["BitTorrent", "uTorrent"]:
        c_dir = Path(appdata) / client
        settings_file = c_dir / "settings.dat"
        if settings_file.exists():
            bak_file = c_dir / "settings.dat.bak"
            try:
                shutil.copy2(settings_file, bak_file)
                data = settings_file.read_bytes()
                new_data = data
                for k in ad_keys:
                    new_data = new_data.replace(k + b"i1e", k + b"i0e")
                settings_file.write_bytes(new_data)
                found_clients.append(client)
            except Exception as e:
                return False, f"Ошибка записи {client}: {e}"

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
                restored.append(client)
            except Exception:
                pass
        elif settings_file.exists():
            try:
                data = settings_file.read_bytes()
                data = data.replace(b"offers.left_rail_offer_enabledi0e", b"offers.left_rail_offer_enabledi1e")
                data = data.replace(b"offers.sponsored_torrent_offer_enabledi0e", b"offers.sponsored_torrent_offer_enabledi1e")
                settings_file.write_bytes(data)
                restored.append(client)
            except Exception:
                pass

    if not restored:
        return False, "Резервные копии настроек не найдены."
    return True, f"Настройки по умолчанию восстановлены для: {', '.join(restored)}."


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
        icon="⚡",
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
]


def get_all_tweaks(lang: str = "ru") -> list[dict]:
    return [t.to_dict(lang) for t in TWEAKS]


def apply_tweak_by_id(tweak_id: str) -> dict:
    for t in TWEAKS:
        if t.id == tweak_id:
            ok, msg = t.apply()
            return {"success": ok, "message": msg, "applied": t.is_applied(), "type": t.type}
    return {"success": False, "message": f"Твик '{tweak_id}' не найден."}


def revert_tweak_by_id(tweak_id: str) -> dict:
    for t in TWEAKS:
        if t.id == tweak_id:
            ok, msg = t.revert()
            return {"success": ok, "message": msg, "applied": t.is_applied(), "type": t.type}
    return {"success": False, "message": f"Твик '{tweak_id}' не найден."}
