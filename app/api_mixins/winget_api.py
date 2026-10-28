"""
Winget & Package Manager API Mixin.
Поиск пакетов в глобальном репозитории Winget, тихая установка и журнал изменений (Release Notes).
"""

import json
import logging
import re
import subprocess
import threading
import urllib.request
from typing import Any
from app.i18n import i18n

logger = logging.getLogger("WinSetup")


class WingetApiMixin:
    """Миксин для взаимодействия с Winget и получения Release Notes."""

    def get_app_changelog(self, app_id: str) -> dict[str, Any]:
        """Возвращает журнал изменений (Release Notes) для приложения из каталога."""
        catalog_map = getattr(self, "_catalog_map", {})
        app = catalog_map.get(app_id)
        if not app:
            return {"success": False, "error": "Приложение не найдено в каталоге"}

        # 1. Если есть github_repo — запрашиваем релиз из GitHub
        if getattr(app, "github_repo", None):
            try:
                url = f"https://api.github.com/repos/{app.github_repo}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "ZiablWinSetup"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read().decode("utf-8"))
                tag = data.get("tag_name") or data.get("name") or ""
                body = data.get("body") or "Нет описания релиза."
                html_url = data.get("html_url") or f"https://github.com/{app.github_repo}/releases"
                return {
                    "success": True,
                    "app_name": app.name,
                    "version": tag,
                    "source": "github",
                    "notes": body,
                    "url": html_url,
                }
            except Exception as e:
                logger.debug(f"GitHub release check failed for {app.name}: {e}")

        # 2. Если есть winget_id — получаем описание из winget show
        if getattr(app, "winget_id", None):
            try:
                cmd = ["winget", "show", "--id", app.winget_id, "--accept-source-agreements"]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    timeout=6,
                )
                output = proc.stdout
                ver_match = re.search(r'(?:Версия|Version):\s*([^\r\n]+)', output)
                ver = ver_match.group(1).strip() if ver_match else ""
                url_match = re.search(r'(?:URL-адрес заметок о выпуске|Release Notes URL):\s*([^\r\n]+)', output)
                notes_url = url_match.group(1).strip() if url_match else ""

                desc_match = re.search(r'(?:Описание|Description):\s*\r?\n([\s\S]*?)(?:\r?\n\S|$)', output)
                desc = desc_match.group(1).strip() if desc_match else ""

                notes_text = ""
                if notes_url:
                    notes_text += f"🔗 **Официальные заметки о выпуске:** [{notes_url}]({notes_url})\n\n"
                if desc:
                    notes_text += f"**Описание пакета:**\n{desc}"
                if not notes_text:
                    notes_text = app.get_notes(i18n.lang) or "Подробный список изменений доступен на официальном сайте программы."

                return {
                    "success": True,
                    "app_name": app.name,
                    "version": ver,
                    "source": "winget",
                    "notes": notes_text,
                    "url": notes_url or getattr(app, "web_url", "") or "",
                }
            except Exception as e:
                logger.debug(f"Winget show failed for {app.name}: {e}")

        notes = app.get_notes(i18n.lang) if hasattr(app, "get_notes") else ""
        return {
            "success": True,
            "app_name": app.name,
            "version": "",
            "source": "catalog",
            "notes": notes or (getattr(app, "description", "") or "Подробности о релизе на сайте программы."),
            "url": getattr(app, "web_url", "") or "",
        }

    def search_winget_packages(self, query: str) -> dict[str, Any]:
        """Выполняет глобальный поиск пакетов в Winget репозитории."""
        q = (query or "").strip()
        if not q or len(q) < 2:
            return {"success": False, "error": "Введите минимум 2 символа для поиска"}
        try:
            cmd = ["winget", "search", q, "--accept-source-agreements", "-n", "25"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                timeout=12,
            )
            output = proc.stdout
            lines = output.strip().splitlines()
            if len(lines) < 2:
                return {"success": True, "results": [], "count": 0}

            header = lines[0]
            matches = list(re.finditer(r'\S+', header))
            col_starts = [m.start() for m in matches]

            results = []
            for l in lines[2:]:
                if not l.strip() or l.startswith("<"):
                    continue
                name = l[col_starts[0]:col_starts[1]].strip() if len(col_starts) > 1 else l.strip()
                pkg_id = l[col_starts[1]:col_starts[2]].strip() if len(col_starts) > 2 else l[col_starts[1]:].strip()
                version = l[col_starts[2]:col_starts[3]].strip() if len(col_starts) > 3 else l[col_starts[2]:].strip()
                source = l[col_starts[4]:].strip() if len(col_starts) > 4 else "winget"
                if not source:
                    source = "winget"
                if pkg_id:
                    results.append({
                        "name": name,
                        "id": pkg_id,
                        "version": version,
                        "source": source,
                    })

            return {"success": True, "results": results, "count": len(results)}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Превышено время ожидания поиска Winget (таймаут)"}
        except Exception as e:
            logger.error(f"Winget search error: {e}")
            return {"success": False, "error": str(e)}

    def install_custom_winget_package(self, pkg_id: str, source: str = "winget") -> dict[str, Any]:
        """Запускает установку любого пакета Winget в фоновом режиме."""
        pkg = (pkg_id or "").strip()
        if not pkg:
            return {"success": False, "error": "ID пакета не указан"}

        def worker():
            if hasattr(self, "call_js"):
                self.call_js("onLog", f"🚀 Запуск установки через Winget: {pkg}...")
            cmd = [
                "winget", "install", "--id", pkg, "--exact",
                "--accept-package-agreements", "--accept-source-agreements",
                "--disable-interactivity"
            ]
            if source and source in ("msstore", "winget"):
                cmd.extend(["-s", source])
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                )
                for line in iter(proc.stdout.readline, ""):
                    clean = line.strip()
                    if clean and hasattr(self, "call_js"):
                        self.call_js("onLog", f"[{pkg}] {clean}")
                rc = proc.wait()
                if rc == 0:
                    if hasattr(self, "call_js"):
                        self.call_js("onLog", f"✅ Пакет {pkg} успешно установлен!")
                        self.call_js("showNotification", f"Пакет {pkg} успешно установлен", "success")
                else:
                    if hasattr(self, "call_js"):
                        self.call_js("onLog", f"❌ Ошибка установки {pkg} (код {rc})")
                        self.call_js("showNotification", f"Ошибка установки {pkg}", "error")
            except Exception as ex:
                if hasattr(self, "call_js"):
                    self.call_js("onLog", f"❌ Ошибка: {ex}")

        threading.Thread(target=worker, daemon=True).start()
        return {"success": True, "message": f"Установка {pkg} запущена"}
