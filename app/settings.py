"""
ZiablWinSetup — Модуль пользовательских настроек.
Хранит конфигурацию (список приложений, исключённых из автообновления, тему, язык и др.).
"""

import json
import os
from pathlib import Path

def _get_settings_path() -> Path:
    # Prefer APPDATA for persistent user config across updates
    appdata = os.environ.get("APPDATA")
    if appdata:
        config_dir = Path(appdata) / "ZiablWinSetup"
    else:
        config_dir = Path(__file__).resolve().parent.parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "settings.json"


_DEFAULT_SETTINGS = {
    "ignored_update_apps": ["photoshop", "premiere"],
    "theme": "dark",
    "language": "ru",
    "silent_mode_default": True,
    "extract_mode": "exe_dir",
    "minimize_to_tray_on_close": True,
    "autostart_with_windows": False,
    "auto_check_app_updates": True,
    "auto_check_software_updates": True,
    "auto_clean_leftovers": None,
    "skipped_app_version": "",
    "virustotal_api_key": "",
    "virustotal_keys": [],
    "accent_color": "blue",
    "always_run_as_admin": False,
}


def load_settings() -> dict:
    path = _get_settings_path()
    if not path.exists():
        save_settings(_DEFAULT_SETTINGS)
        return dict(_DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Merge defaults for any missing keys
        for k, v in _DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
        # Очищаем устаревший жестко прописанный путь распаковки, если он остался от прошлых версий
        if "extract_path" in data:
            data.pop("extract_path", None)
            save_settings(data)
        return data
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict) -> bool:
    path = _get_settings_path()
    try:
        # Гарантируем, что персональные жестко заданные пути никогда не записываются в настройки
        clean_settings = dict(settings)
        clean_settings.pop("extract_path", None)
        path.write_text(json.dumps(clean_settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def get_ignored_update_apps() -> list[str]:
    settings = load_settings()
    return list(settings.get("ignored_update_apps", []))


def set_app_ignored_update(app_id: str, ignored: bool) -> list[str]:
    settings = load_settings()
    ignored_list = set(settings.get("ignored_update_apps", []))
    if ignored:
        ignored_list.add(app_id)
    else:
        ignored_list.discard(app_id)
    settings["ignored_update_apps"] = sorted(list(ignored_list))
    save_settings(settings)
    return settings["ignored_update_apps"]


def toggle_app_ignored_update(app_id: str) -> bool:
    settings = load_settings()
    ignored_list = set(settings.get("ignored_update_apps", []))
    if app_id in ignored_list:
        ignored_list.remove(app_id)
        is_ignored = False
    else:
        ignored_list.add(app_id)
        is_ignored = True
    settings["ignored_update_apps"] = sorted(list(ignored_list))
    save_settings(settings)
    return is_ignored


def set_ignored_update_apps(app_ids: list[str]) -> list[str]:
    settings = load_settings()
    settings["ignored_update_apps"] = sorted(list(set(app_ids)))
    save_settings(settings)
    return settings["ignored_update_apps"]


def get_virustotal_api_key() -> str:
    settings = load_settings()
    return str(settings.get("virustotal_api_key", "")).strip()


def set_virustotal_api_key(api_key: str) -> bool:
    settings = load_settings()
    clean_key = api_key.strip()
    settings["virustotal_api_key"] = clean_key
    # Also keep in keys list
    if clean_key:
        keys = list(settings.get("virustotal_keys", []))
        if not any(k.get("key") == clean_key for k in keys):
            keys.insert(0, {"name": "Default Account", "key": clean_key})
            settings["virustotal_keys"] = keys
    return save_settings(settings)


def get_virustotal_keys() -> list[dict[str, str]]:
    """Returns saved VirusTotal keys list: [{'name': '...', 'key': '...'}]"""
    settings = load_settings()
    keys = list(settings.get("virustotal_keys", []))
    active = str(settings.get("virustotal_api_key", "")).strip()
    if active and not any(k.get("key") == active for k in keys):
        keys.insert(0, {"name": "Default Account", "key": active})
        settings["virustotal_keys"] = keys
        save_settings(settings)
    return keys


def save_virustotal_key(name: str, key: str, set_active: bool = True) -> list[dict[str, str]]:
    """Adds or updates a named VirusTotal key."""
    settings = load_settings()
    keys = list(settings.get("virustotal_keys", []))
    clean_name = str(name or "Account").strip()
    clean_key = str(key or "").strip()
    if not clean_key:
        return keys
    existing = next((k for k in keys if k.get("key") == clean_key), None)
    if existing:
        existing["name"] = clean_name
    else:
        keys.append({"name": clean_name, "key": clean_key})
    settings["virustotal_keys"] = keys
    if set_active:
        settings["virustotal_api_key"] = clean_key
    save_settings(settings)
    return keys


def delete_virustotal_key(key: str) -> list[dict[str, str]]:
    """Deletes a saved VirusTotal key."""
    settings = load_settings()
    clean_key = str(key or "").strip()
    keys = [k for k in settings.get("virustotal_keys", []) if k.get("key") != clean_key]
    settings["virustotal_keys"] = keys
    if settings.get("virustotal_api_key", "").strip() == clean_key:
        settings["virustotal_api_key"] = keys[0]["key"] if keys else ""
    save_settings(settings)
    return keys


def set_active_virustotal_key(key: str) -> bool:
    """Sets the active VirusTotal key."""
    settings = load_settings()
    settings["virustotal_api_key"] = str(key or "").strip()
    return save_settings(settings)


def get_accent_color() -> str:
    settings = load_settings()
    return str(settings.get("accent_color", "blue")).lower()


def set_accent_color(accent: str) -> str:
    settings = load_settings()
    valid = {"blue", "purple", "green", "orange", "red"}
    clean_accent = str(accent or "blue").lower()
    if clean_accent not in valid:
        clean_accent = "blue"
    settings["accent_color"] = clean_accent
    save_settings(settings)
    return clean_accent



def is_always_run_as_admin() -> bool:
    """Проверяет, включен ли запуск от имени администратора в настройках или в реестре."""
    settings = load_settings()
    if bool(settings.get("always_run_as_admin", False)):
        return True
    try:
        import sys, winreg
        layers_key = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, layers_key, 0, winreg.KEY_READ) as key:
            exe_path = str(Path(sys.executable).resolve())
            candidates = [exe_path]
            if "python" in Path(exe_path).name.lower():
                dist_exe = Path(os.getcwd()) / "dist" / "ZiablWinSetup.exe"
                if dist_exe.exists():
                    candidates.append(str(dist_exe.resolve()))
            for p in candidates:
                try:
                    val, _ = winreg.QueryValueEx(key, p)
                    if "RUNASADMIN" in str(val).upper():
                        return True
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    return False


def set_always_run_as_admin(enabled: bool) -> bool:
    """Включает или выключает постоянный запуск от имени администратора."""
    settings = load_settings()
    settings["always_run_as_admin"] = bool(enabled)
    save_settings(settings)
    _sync_runasadmin_registry(bool(enabled))
    return True


def _sync_runasadmin_registry(enabled: bool) -> bool:
    r"""Синхронизирует системный флаг ~ RUNASADMIN в AppCompatFlags\Layers для текущего exe."""
    try:
        import sys, winreg
        layers_key = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        exe_path = str(Path(sys.executable).resolve())
        if "python" in Path(exe_path).name.lower():
            candidates = []
            dist_exe = Path(os.getcwd()) / "dist" / "ZiablWinSetup.exe"
            if dist_exe.exists():
                candidates.append(str(dist_exe.resolve()))
        else:
            candidates = [exe_path]
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, layers_key) as key:
            for p in candidates:
                if enabled:
                    winreg.SetValueEx(key, p, 0, winreg.REG_SZ, "~ RUNASADMIN")
                else:
                    try:
                        winreg.DeleteValue(key, p)
                    except FileNotFoundError:
                        pass
        return True
    except Exception:
        return False
