"""
ZiablWinSetup — Модуль резервного копирования и восстановления приложений.
Позволяет экспортировать список установленных программ (из каталога ZiablWinSetup
и всей операционной системы Windows) в файл резервной копии (.ziablbackup / .json),
а затем легко импортировать его после переустановки Windows.
"""

import os
import sys
import json
import logging
import datetime
import subprocess
import threading
from pathlib import Path
from typing import Any

from app.catalog import get_catalog
from app.detector import detect_installed_apps, _get_registry_entries

logger = logging.getLogger("WinSetup")


def get_default_backup_dir() -> Path:
    """Возвращает путь к папке бэкапов в Документах пользователя."""
    b_dir = Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Documents" / "ZiablWinSetup_Backups"
    b_dir.mkdir(parents=True, exist_ok=True)
    return b_dir


def export_apps_backup(target_path: str | None = None) -> dict[str, Any]:
    """
    Сканирует все установленные программы и экспортирует их в файл бэкапа.
    """
    try:
        catalog = get_catalog()
        catalog_map = {a.id: a for a in catalog}
        installed_map = detect_installed_apps()

        # 1. Программы из каталога ZiablWinSetup
        catalog_apps_data = []
        catalog_installed_names = set()

        for app_id, info in installed_map.items():
            app = catalog_map.get(app_id)
            if app:
                ver = info.get("version", "")
                catalog_apps_data.append({
                    "id": app.id,
                    "name": app.name,
                    "version": ver,
                    "category": app.category,
                    "winget_id": app.winget_id,
                    "installer_type": app.installer_type,
                    "recommended": getattr(app, "recommended", False),
                })
                catalog_installed_names.add(app.name.lower())
                catalog_installed_names.add(app.id.lower())

        # 2. Сторонние программы системы (из реестра Windows)
        raw_reg = _get_registry_entries()
        system_apps_data = []
        seen_names = set()

        for entry in raw_reg:
            dn = entry.get("display_name", "").strip()
            ver = entry.get("version", "").strip()
            uninst = entry.get("uninstall", "").strip()

            if not dn:
                continue

            dn_lower = dn.lower()
            # Пропускаем системные апдейты
            if dn.startswith("KB") or "Security Update" in dn or "Hotfix" in dn:
                continue
            # Пропускаем, если уже есть в каталоге ZiablWinSetup
            if any(cat_n in dn_lower for cat_n in catalog_installed_names):
                continue
            if dn_lower in seen_names:
                continue
            seen_names.add(dn_lower)

            # Пробуем определить Winget ID из каталога или общих паттернов
            winget_id = ""
            for app in catalog:
                if app.winget_id and (app.name.lower() in dn_lower or dn_lower in app.name.lower()):
                    winget_id = app.winget_id
                    break

            system_apps_data.append({
                "name": dn,
                "version": ver,
                "winget_id": winget_id,
                "uninstall_cmd": uninst,
            })

        # Сортировка по имени
        catalog_apps_data.sort(key=lambda x: x["name"].lower())
        system_apps_data.sort(key=lambda x: x["name"].lower())

        backup_payload = {
            "app": "ZiablWinSetup",
            "format_version": 1,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "machine_name": os.environ.get("COMPUTERNAME", "Windows PC"),
            "os_version": f"Windows {sys.getwindowsversion().major}.{sys.getwindowsversion().build}",
            "catalog_apps_count": len(catalog_apps_data),
            "system_apps_count": len(system_apps_data),
            "catalog_apps": catalog_apps_data,
            "system_apps": system_apps_data,
        }

        if not target_path:
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            target_path = str(get_default_backup_dir() / f"ZiablWinSetup_Backup_{today_str}.ziablbackup")

        out_path = Path(target_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(backup_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        # Также создаем читаемый текстовый список рядом
        txt_path = out_path.with_suffix(".txt")
        lines = [
            f"=== Резервная копия программ ZiablWinSetup ===",
            f"Дата: {backup_payload['created_at']}",
            f"Компьютер: {backup_payload['machine_name']} ({backup_payload['os_version']})",
            f"\n[ ПРОГРАММЫ ИЗ КАТАЛОГА ZIABLWINSETUP ({len(catalog_apps_data)} шт.) ]",
        ]
        for a in catalog_apps_data:
            ver_suffix = f" ({a['version']})" if a.get("version") else ""
            lines.append(f"• {a['name']}{ver_suffix} [{a['category']}]")

        lines.append(f"\n[ ДРУГИЕ ПРОГРАММЫ СИСТЕМЫ ({len(system_apps_data)} шт.) ]")
        for s in system_apps_data:
            ver_suffix = f" ({s['version']})" if s.get("version") else ""
            lines.append(f"• {s['name']}{ver_suffix}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "success": True,
            "file_path": str(out_path),
            "filename": out_path.name,
            "catalog_count": len(catalog_apps_data),
            "system_count": len(system_apps_data),
            "message": f"Бэкап сохранен: {len(catalog_apps_data)} программ каталога, {len(system_apps_data)} системных программ.",
        }
    except Exception as e:
        logger.error(f"Error creating apps backup: {e}")
        return {"success": False, "message": f"Ошибка создания резервной копии: {e}"}


def _parse_txt_backup(content: str) -> dict[str, Any]:
    """Парсит человекочитаемый .txt файл резервной копии программ."""
    catalog_apps = []
    system_apps = []
    current_section = None
    created_at = ""
    machine_name = ""

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Дата:") or line.startswith("Date:"):
            created_at = line.split(":", 1)[1].strip()
        elif line.startswith("Компьютер:") or line.startswith("PC:"):
            machine_name = line.split(":", 1)[1].strip()
        elif "ПРОГРАММЫ ИЗ КАТАЛОГА" in line.upper() or "CATALOG APPS" in line.upper():
            current_section = "catalog"
        elif "ДРУГИЕ ПРОГРАММЫ" in line.upper() or "SYSTEM APPS" in line.upper():
            current_section = "system"
        elif line.startswith("•") or line.startswith("-") or line.startswith("*"):
            item_text = line.lstrip("•-* ").strip()
            # Формат: Name (version) [category]
            m = re.match(r"^(.+?)(?:\s*\(([^)]+)\))?(?:\s*\[([^\]]+)\])?$", item_text)
            if m:
                name = m.group(1).strip()
                version = (m.group(2) or "").strip()
                category = (m.group(3) or "").strip()
                if current_section == "catalog":
                    catalog_apps.append({
                        "name": name,
                        "version": version,
                        "category": category,
                    })
                elif current_section == "system":
                    system_apps.append({
                        "name": name,
                        "version": version,
                    })

    return {
        "app": "ZiablWinSetup",
        "format_version": 1,
        "created_at": created_at,
        "machine_name": machine_name,
        "catalog_apps": catalog_apps,
        "system_apps": system_apps,
    }


def import_apps_backup(file_path: str) -> dict[str, Any]:
    """
    Считывает файл резервной копии (.ziablbackup, .json или .txt) и сопоставляет его с текущим каталогом и системой.
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return {"success": False, "message": "Файл резервной копии не найден"}

        data = None
        # Если выбран .txt, сначала проверяем companion .ziablbackup, либо парсим текст
        if p.suffix.lower() == ".txt":
            companion = p.with_suffix(".ziablbackup")
            if companion.exists():
                try:
                    data = json.loads(companion.read_text(encoding="utf-8"))
                except Exception:
                    data = None
            if not data:
                data = _parse_txt_backup(p.read_text(encoding="utf-8"))
        else:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                # Если парсинг JSON не удался, пробуем текстовый парсер
                data = _parse_txt_backup(p.read_text(encoding="utf-8"))

        if not data or (data.get("app") != "ZiablWinSetup" and "catalog_apps" not in data):
            return {"success": False, "message": "Неверный формат файла бэкапа"}

        catalog = get_catalog()
        catalog_map = {a.id: a for a in catalog}
        # Карта поиска по имени
        catalog_name_map = {a.name.lower(): a for a in catalog}

        current_installed = detect_installed_apps()

        # Разбор программ каталога
        raw_catalog_list = data.get("catalog_apps", [])
        matched_catalog = []
        already_installed_count = 0
        to_install_count = 0

        for item in raw_catalog_list:
            app_id = item.get("id")
            app = catalog_map.get(app_id) if app_id else None
            if not app:
                # Попробуем по имени
                name_key = item.get("name", "").lower()
                app = catalog_name_map.get(name_key)

            if app:
                is_inst = app.id in current_installed
                cur_ver = current_installed[app.id].get("version", "") if is_inst else ""
                if is_inst:
                    already_installed_count += 1
                else:
                    to_install_count += 1

                matched_catalog.append({
                    "id": app.id,
                    "name": app.name,
                    "category": app.category,
                    "backup_version": item.get("version", ""),
                    "current_version": cur_ver,
                    "already_installed": is_inst,
                    "winget_id": app.winget_id,
                    "installer_type": app.installer_type,
                    "recommended": getattr(app, "recommended", False),
                    "checked": True,  # По умолчанию выделяем все программы из бэкапа
                })

        # Разбор системных программ
        raw_system_list = data.get("system_apps", [])
        current_raw_reg = _get_registry_entries()
        curr_sys_names = {r.get("display_name", "").lower() for r in current_raw_reg if r.get("display_name")}

        matched_system = []
        for s in raw_system_list:
            s_name = s.get("name", "").strip()
            if not s_name:
                continue
            is_inst = s_name.lower() in curr_sys_names
            w_id = s.get("winget_id", "")
            matched_system.append({
                "name": s_name,
                "backup_version": s.get("version", ""),
                "already_installed": is_inst,
                "winget_id": w_id,
                "search_query": s_name,
            })

        return {
            "success": True,
            "filename": p.name,
            "created_at": data.get("created_at", ""),
            "machine_name": data.get("machine_name", ""),
            "os_version": data.get("os_version", ""),
            "catalog_apps": matched_catalog,
            "system_apps": matched_system,
            "stats": {
                "catalog_total": len(matched_catalog),
                "catalog_to_install": to_install_count,
                "catalog_already_installed": already_installed_count,
                "system_total": len(matched_system),
            }
        }
    except Exception as e:
        logger.error(f"Error importing apps backup: {e}")
        return {"success": False, "message": f"Ошибка чтения файла резервной копии: {e}"}


def install_winget_package_sync(winget_id: str) -> dict[str, Any]:
    """Выполняет установку пакета через winget."""
    if not winget_id:
        return {"success": False, "message": "ID пакета winget не указан"}
    try:
        cmd = [
            "winget", "install",
            "--id", winget_id,
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity"
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            timeout=300
        )
        if proc.returncode == 0:
            return {"success": True, "message": f"Пакет {winget_id} успешно установлен через Winget."}
        else:
            return {"success": False, "message": f"Ошибка Winget (код {proc.returncode}): {proc.stderr or proc.stdout}"}
    except Exception as e:
        return {"success": False, "message": f"Не удалось выполнить winget install: {e}"}
