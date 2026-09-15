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
        return data
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict) -> bool:
    path = _get_settings_path()
    try:
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
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
