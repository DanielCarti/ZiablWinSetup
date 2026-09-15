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
                    c_name_l = c_app.name.lower()
                    if c_name_l in up_name_l or up_name_l in c_name_l:
                        app = c_app
                        break
            if app:
                results[app.id] = {
                    "app_id": app.id,
                    "name": app.name,
                    "current_version": up_info["version"],
                    "available_version": up_info["available"],
                    "source": "winget",
                }
                # Если winget нашел обновление — приложение 100% установлено в системе!
                if app.id not in installed:
                    installed[app.id] = {
                        "installed": True,
                        "name": app.name,
                        "version": up_info["version"],
                        "uninstall_cmd": "",
                        "quiet_uninstall": "",
                    }
    except Exception as e:
        logger.error(f"Winget upgrade check error: {e}")

    # 2. GitHub checks for installed apps
    github_apps = [app for app in catalog if app.github_repo and app.id in installed]
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
                    curr_clean = curr_ver.lstrip("v").strip()
                    if curr_clean and curr_clean != latest_ver:
                        results[app.id] = {
                            "app_id": app.id,
                            "name": app.name,
                            "current_version": curr_ver,
                            "available_version": latest_ver,
                            "source": "github",
                        }

    return results
