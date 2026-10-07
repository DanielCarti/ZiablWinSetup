"""
ZiablWinSetup — Модуль проверки обновлений.
Проверяет обновления через winget для репозиторных программ
и через GitHub Releases API для портативных/гитхаб утилит.
"""

import json
import logging
import re
import subprocess
import urllib.request
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.catalog import get_catalog, AppEntry
from app.detector import detect_installed_apps

logger = logging.getLogger("updater")


def _get_github_latest_version(repo: str) -> str | None:
    """Получает последний тег/версию релиза с GitHub."""
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "ZiablWinSetup/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            return tag.lstrip("v").strip()
    except Exception as e:
        logger.debug(f"GitHub release check failed for {repo}: {e}")
        # Fallback: scrape releases page
        try:
            url = f"https://github.com/{repo}/releases"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                pattern = rf"/{repo}/releases/tag/([^\"'>]+)"
                m = re.search(pattern, html)
                if m:
                    return m.group(1).lstrip("v").strip()
        except Exception:
            pass
    return None


def parse_version_tuple(ver_str: str) -> tuple[int, ...]:
    """Преобразует строку версии в кортеж чисел ('1.11.0' -> (1, 11))."""
    if not ver_str:
        return ()
    cleaned = ver_str.lstrip("vV").strip()
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return ()
    nums = [int(p) for p in parts]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()
    return tuple(nums)


def is_newer_version(latest_ver: str, current_ver: str) -> bool:
    """
    Проверяет, является ли latest_ver строго новее current_ver.
    Игнорирует ложные несовпадения (1.11 vs 1.11.0) и строки 'Portable'/'Unknown'.
    """
    if not latest_ver or not current_ver:
        return False
    clean_curr = current_ver.strip().lower()
    if clean_curr in ("portable", "unknown", "installed"):
        return False
    t_latest = parse_version_tuple(latest_ver)
    t_current = parse_version_tuple(current_ver)
    if not t_latest or not t_current:
        return False
    max_len = max(len(t_latest), len(t_current))
    l_padded = t_latest + (0,) * (max_len - len(t_latest))
    c_padded = t_current + (0,) * (max_len - len(t_current))
    return l_padded > c_padded


def parse_winget_upgrade_output(output: str) -> dict[str, dict]:
    """
    Парсит вывод 'winget upgrade'.
    Возвращает словарь {winget_id: {"name": ..., "version": ..., "available": ...}}
    """
    upgrades = {}
    lines = output.splitlines()
    header_idx = -1
    for i, line in enumerate(lines):
        if "---" in line and len(line) > 10:
            header_idx = i
            break

    if header_idx == -1:
        return upgrades

    # Parse rows after dashes
    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        parts = re.split(r"\s{2,}", line)
        if len(parts) >= 4:
            name = parts[0]
            pkg_id = parts[1]
            ver = parts[2]
            avail = parts[3]
            upgrades[pkg_id.lower()] = {
                "name": name,
                "pkg_id": pkg_id,
                "version": ver,
                "available": avail,
            }
    return upgrades


def check_updates_sync(installed: dict[str, dict[str, Any]] | None = None) -> dict[str, dict]:
    """
    Выполняет полную проверку обновлений:
    1. Winget upgrade для установленных программ.
    2. GitHub API для утилит с github_repo.
    Возвращает {app_id: {"name": ..., "current_version": ..., "available_version": ..., "source": ...}}
    """
    results = {}
    if installed is None:
        installed = detect_installed_apps()
    catalog = get_catalog()
    catalog_by_id = {app.id: app for app in catalog}
    catalog_by_winget = {app.winget_id.lower(): app for app in catalog if app.winget_id}

    # 1. Winget upgrade check
    try:
        proc = subprocess.run(
            ["winget", "upgrade"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        winget_upgrades = parse_winget_upgrade_output(proc.stdout)
        for wid, up_info in winget_upgrades.items():
            app = catalog_by_winget.get(wid)
            if not app:
                # Fallback: поиск по совпадению имени или идентификатора
                up_name_l = up_info["name"].lower()
                for c_app in catalog:
                    if c_app.id == "python":
                        if "launcher" in up_name_l or "launcher" in wid:
                            continue
                        if wid.startswith("python.python.") or ("python 3" in up_name_l):
                            app = c_app
                            break
                    c_name_l = c_app.name.lower()
                    if c_name_l in up_name_l or up_name_l in c_name_l:
                        app = c_app
                        break
            if app:
                if app.id in results:
                    prev_avail = results[app.id].get("available_version", "")
                    if not is_newer_version(up_info["available"], prev_avail):
                        continue

                target_wid = up_info.get("pkg_id") or wid
                display_name = app.name
                if app.id == "python" and "." in up_info["version"]:
                    parts = up_info["version"].split(".")
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        display_name = f"Python {parts[0]}.{parts[1]}"

                results[app.id] = {
                    "app_id": app.id,
                    "name": display_name,
                    "current_version": up_info["version"],
                    "available_version": up_info["available"],
                    "target_winget_id": target_wid,
                    "source": "winget",
                }
                # Синхронизируем версию в installed, чтобы в UI не было рассинхрона
                if installed is not None:
                    installed[app.id] = {
                        "installed": True,
                        "name": display_name,
                        "version": up_info["version"],
                        "uninstall_cmd": installed.get(app.id, {}).get("uninstall_cmd", ""),
                        "quiet_uninstall": installed.get(app.id, {}).get("quiet_uninstall", ""),
                    }
    except Exception as e:
        logger.error(f"Winget upgrade check error: {e}")

    # 2. GitHub checks for installed apps
    # Для программ с winget_id источником правды является winget, чтобы не возникало рассинхрона
    # (например, когда разработчик Obsidian выложил тег 1.13.8 на GitHub, но в манифестах winget доступна только 1.13.7).
    # GitHub проверяется только для утилит без winget_id (например, Zapret, TG WS Proxy, Opera Proxy)
    # либо если проверка winget завершилась ошибкой.
    github_apps = [
        app for app in catalog
        if app.github_repo and app.id in installed and (not app.winget_id or not winget_upgrades)
    ]
    if github_apps:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_app = {
                executor.submit(_get_github_latest_version, app.github_repo): app
                for app in github_apps
            }
            for future in as_completed(future_to_app):
                app = future_to_app[future]
                latest_ver = future.result()
                if latest_ver:
                    curr_ver = installed[app.id].get("version", "")
                    if curr_ver and is_newer_version(latest_ver, curr_ver):
                        results[app.id] = {
                            "app_id": app.id,
                            "name": app.name,
                            "current_version": curr_ver,
                            "available_version": latest_ver,
                            "source": "github",
                        }

    return results
