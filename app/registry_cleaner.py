"""
ZiablWinSetup — Модуль очистки и оптимизации реестра Windows.
Безопасный поиск устаревших и недействительных записей с ОБЯЗАТЕЛЬНЫМ
созданием отката в формате .reg перед любым изменением.
"""

import os
import re
import sys
import datetime
import logging
import winreg
from pathlib import Path
from typing import Any

logger = logging.getLogger("WinSetup")

def get_backups_dir() -> Path:
    """Возвращает путь к папке бэкапов реестра в Документах пользователя."""
    user_docs = Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Documents" / "ZiablWinSetup_Backups"
    user_docs.mkdir(parents=True, exist_ok=True)
    return user_docs


def _get_hkey_name(hkey) -> str:
    if hkey == winreg.HKEY_CURRENT_USER:
        return "HKEY_CURRENT_USER"
    if hkey == winreg.HKEY_LOCAL_MACHINE:
        return "HKEY_LOCAL_MACHINE"
    if hkey == winreg.HKEY_CLASSES_ROOT:
        return "HKEY_CLASSES_ROOT"
    return "HKEY_UNKNOWN"


def _clean_path(raw: str) -> str:
    """Очищает строку пути от кавычек, пробелов и аргументов."""
    if not raw:
        return ""
    expanded = os.path.expandvars(raw.strip())
    # Если в кавычках: "C:\path\to\file.exe"
    m_quoted = re.match(r'^"([^"]+)"', expanded)
    if m_quoted:
        return m_quoted.group(1).strip()
    # Если без кавычек, берем до первого пробела с .exe или всю строку
    m_exe = re.match(r'^([a-zA-Z]:\\[^\s]+\.exe)', expanded, re.IGNORECASE)
    if m_exe:
        return m_exe.group(1).strip()
    return expanded.strip('" \t')


def _export_key_to_reg_lines(hkey_constant, subkey_path: str) -> list[str]:
    """Рекурсивно экспортирует ключ реестра и все его подключи в синтаксис .reg файла."""
    lines = []
    hkey_name = _get_hkey_name(hkey_constant)
    full_key_header = f"[{hkey_name}\\{subkey_path}]"

    try:
        with winreg.OpenKey(hkey_constant, subkey_path, 0, winreg.KEY_READ) as key:
            lines.append(full_key_header)
            num_subkeys, num_values, _ = winreg.QueryInfoKey(key)

            for i in range(num_values):
                try:
                    vn, val, val_type = winreg.EnumValue(key, i)
                    v_name_escaped = f'"{vn.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"' if vn else "@"

                    if val_type == winreg.REG_SZ:
                        s_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{v_name_escaped}="{s_val}"')
                    elif val_type == winreg.REG_EXPAND_SZ:
                        s_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
                        # REG_EXPAND_SZ можно экспортировать как hex(2) или строку
                        lines.append(f'{v_name_escaped}="{s_val}"')
                    elif val_type == winreg.REG_DWORD:
                        lines.append(f"{v_name_escaped}=dword:{val:08x}")
                    elif val_type == winreg.REG_MULTI_SZ:
                        # Сериализация списка строк
                        hex_bytes = b"".join(s.encode("utf-16le") + b"\x00\x00" for s in val) + b"\x00\x00"
                        hex_str = ",".join(f"{b:02x}" for b in hex_bytes)
                        lines.append(f"{v_name_escaped}=hex(7):{hex_str}")
                    elif val_type == winreg.REG_BINARY:
                        hex_str = ",".join(f"{b:02x}" for b in val) if isinstance(val, (bytes, bytearray)) else ""
                        lines.append(f"{v_name_escaped}=hex:{hex_str}")
                except Exception:
                    pass
            lines.append("")

            # Рекурсивно для всех подпапок ключа
            for j in range(num_subkeys):
                try:
                    sk_name = winreg.EnumKey(key, j)
                    lines.extend(_export_key_to_reg_lines(hkey_constant, f"{subkey_path}\\{sk_name}"))
                except Exception:
                    pass
    except Exception:
        pass
    return lines


def _export_single_value_to_reg_lines(hkey_constant, subkey_path: str, value_name: str) -> list[str]:
    """Экспортирует отдельное значение ключа реестра для отката."""
    lines = []
    hkey_name = _get_hkey_name(hkey_constant)
    full_key_header = f"[{hkey_name}\\{subkey_path}]"

    try:
        with winreg.OpenKey(hkey_constant, subkey_path, 0, winreg.KEY_READ) as key:
            val, val_type = winreg.QueryValueEx(key, value_name)
            lines.append(full_key_header)
            v_name_escaped = f'"{value_name.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"' if value_name else "@"

            if val_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                s_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{v_name_escaped}="{s_val}"')
            elif val_type == winreg.REG_DWORD:
                lines.append(f"{v_name_escaped}=dword:{val:08x}")
            else:
                s_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{v_name_escaped}="{s_val}"')
            lines.append("")
    except Exception:
        pass
    return lines


def _delete_key_recursively(hkey_constant, subkey_path: str):
    """Рекурсивное удаление ключа реестра со всеми подпапками."""
    try:
        with winreg.OpenKey(hkey_constant, subkey_path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub_name = winreg.EnumKey(key, 0)
                    _delete_key_recursively(hkey_constant, f"{subkey_path}\\{sub_name}")
                except OSError:
                    break
    except Exception:
        pass

    try:
        parent_path, sep, key_name = subkey_path.rpartition("\\")
        if parent_path:
            with winreg.OpenKey(hkey_constant, parent_path, 0, winreg.KEY_ALL_ACCESS) as parent:
                winreg.DeleteKey(parent, key_name)
        else:
            winreg.DeleteKey(hkey_constant, key_name)
    except Exception as e:
        logger.warning(f"Error deleting key {subkey_path}: {e}")


def scan_registry_issues() -> list[dict[str, Any]]:
    """
    Сканирует реестр на наличие недействительных/мусорных записей:
    1. Недействительные Uninstall записи (где папка/деинсталлятор удалены, кроме msiexec)
    2. Битые записи Автозагрузки Run/RunOnce
    3. Недействительные App Paths
    4. Устаревший кэш MuiCache для удалённых exe
    """
    issues = []
    issue_idx = 1

    # -------------------------------------------------------------
    # 1. Недействительные записи деинсталляции
    # -------------------------------------------------------------
    uninst_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 64-bit"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM 32-bit"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
    ]

    for hkey, subkey_path, rname in uninst_roots:
        try:
            with winreg.OpenKey(hkey, subkey_path, 0, winreg.KEY_READ) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        sk = winreg.EnumKey(key, i)
                        full_sub = f"{subkey_path}\\{sk}"
                        with winreg.OpenKey(hkey, full_sub, 0, winreg.KEY_READ) as app_key:
                            try:
                                dn, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                dn = str(dn).strip()
                            except Exception:
                                dn = ""

                            if not dn:
                                continue

                            # Не трогаем системные обновления Windows
                            if dn.startswith("KB") or "Security Update" in dn or "Hotfix" in dn:
                                continue

                            loc = ""
                            try:
                                loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                loc = _clean_path(str(loc))
                            except Exception:
                                pass

                            uninst = ""
                            try:
                                uninst, _ = winreg.QueryValueEx(app_key, "UninstallString")
                                uninst = str(uninst).strip()
                            except Exception:
                                pass

                            # Если это MSI-деинсталлятор (MsiExec.exe /X...), Windows хранит кэш в Installer
                            if "msiexec" in uninst.lower():
                                continue

                            # Защита от удаления записей драйверов и системных бандлов WiX/Burn в Package Cache
                            if "package cache" in uninst.lower() or "package cache" in loc.lower():
                                continue
                            if "windows\\installer" in uninst.lower():
                                continue
                            if sk.startswith("{") and sk.endswith("}"):
                                continue

                            uninst_exe = _clean_path(uninst)

                            # Проверяем: если есть путь установки на локальном диске, и папка не существует
                            is_broken = False
                            reason = ""

                            if loc and len(loc) > 3 and loc[1:3] == ":\\":
                                if not os.path.exists(loc):
                                    # Проверяем исполняемый деинсталлятор
                                    if uninst_exe and uninst_exe[1:3] == ":\\":
                                        if not os.path.exists(uninst_exe):
                                            is_broken = True
                                            reason = f"Папка «{loc}» и деинсталлятор «{uninst_exe}» не существуют"
                                    elif not uninst:
                                        is_broken = True
                                        reason = f"Папка установки «{loc}» удалена с диска"

                            elif uninst_exe and len(uninst_exe) > 3 and uninst_exe[1:3] == ":\\":
                                if not os.path.exists(uninst_exe):
                                    is_broken = True
                                    reason = f"Файл деинсталлятора отсутствует: «{uninst_exe}»"

                            if is_broken:
                                issues.append({
                                    "id": f"reg_{issue_idx}",
                                    "category": "uninstall",
                                    "category_title": "Недействительная запись деинсталляции",
                                    "title": dn,
                                    "detail": reason,
                                    "root_key": "HKEY_LOCAL_MACHINE" if hkey == winreg.HKEY_LOCAL_MACHINE else "HKEY_CURRENT_USER",
                                    "hkey_val": hkey,
                                    "subkey_path": full_sub,
                                    "value_name": None,
                                    "action_type": "delete_key",
                                    "checked": True,
                                })
                                issue_idx += 1
                    except Exception:
                        pass
        except Exception:
            pass

    # -------------------------------------------------------------
    # 2. Несуществующие файлы в Автозагрузке (Run / RunOnce)
    # -------------------------------------------------------------
    run_roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
    ]

    for hkey, subkey_path in run_roots:
        try:
            with winreg.OpenKey(hkey, subkey_path, 0, winreg.KEY_READ) as key:
                num_values = winreg.QueryInfoKey(key)[1]
                for i in range(num_values):
                    try:
                        vn, val, _ = winreg.EnumValue(key, i)
                        clean_exe = _clean_path(str(val))
                        if clean_exe and len(clean_exe) > 3 and clean_exe[1:3] == ":\\":
                            if not os.path.exists(clean_exe):
                                issues.append({
                                    "id": f"reg_{issue_idx}",
                                    "category": "autostart",
                                    "category_title": "Ошибочная запись автозагрузки",
                                    "title": vn or "Автозапуск",
                                    "detail": f"Отсутствует файл: «{clean_exe}»",
                                    "root_key": _get_hkey_name(hkey),
                                    "hkey_val": hkey,
                                    "subkey_path": subkey_path,
                                    "value_name": vn,
                                    "action_type": "delete_value",
                                    "checked": True,
                                })
                                issue_idx += 1
                    except Exception:
                        pass
        except Exception:
            pass

    # -------------------------------------------------------------
    # 3. Недействительные пути приложений (App Paths)
    # -------------------------------------------------------------
    app_paths_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for hkey, subkey_path in app_paths_roots:
        try:
            with winreg.OpenKey(hkey, subkey_path, 0, winreg.KEY_READ) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        sk = winreg.EnumKey(key, i)
                        full_sub = f"{subkey_path}\\{sk}"
                        with winreg.OpenKey(hkey, full_sub, 0, winreg.KEY_READ) as subk:
                            try:
                                val, _ = winreg.QueryValueEx(subk, "")
                                clean_exe = _clean_path(str(val))
                                if clean_exe and len(clean_exe) > 3 and clean_exe[1:3] == ":\\":
                                    if not os.path.exists(clean_exe):
                                        issues.append({
                                            "id": f"reg_{issue_idx}",
                                            "category": "app_paths",
                                            "category_title": "Недействительный App Path",
                                            "title": sk,
                                            "detail": f"Исполняемый файл не найден: «{clean_exe}»",
                                            "root_key": _get_hkey_name(hkey),
                                            "hkey_val": hkey,
                                            "subkey_path": full_sub,
                                            "value_name": None,
                                            "action_type": "delete_key",
                                            "checked": True,
                                        })
                                        issue_idx += 1
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

    # -------------------------------------------------------------
    # 4. Устаревший кэш MuiCache (мусор от временных инсталляторов и удаленных файлов)
    # -------------------------------------------------------------
    muicache_sub = r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, muicache_sub, 0, winreg.KEY_READ) as key:
            num_values = winreg.QueryInfoKey(key)[1]
            for i in range(num_values):
                try:
                    vn, val, _ = winreg.EnumValue(key, i)
                    m = re.match(r"^([a-zA-Z]:\\[^.]+\.exe)", vn, re.IGNORECASE)
                    if m:
                        exe_path = os.path.expandvars(m.group(1))
                        # Если это путь в Temp или файл уже не существует на диске
                        if not os.path.exists(exe_path):
                            display_title = Path(exe_path).name
                            issues.append({
                                "id": f"reg_{issue_idx}",
                                "category": "muicache",
                                "category_title": "Устаревший кэш MuiCache",
                                "title": display_title,
                                "detail": f"Удалённый файл: «{exe_path}»",
                                "root_key": "HKEY_CURRENT_USER",
                                "hkey_val": winreg.HKEY_CURRENT_USER,
                                "subkey_path": muicache_sub,
                                "value_name": vn,
                                "action_type": "delete_value",
                                "checked": True,
                            })
                            issue_idx += 1
                except Exception:
                    pass
    except Exception:
        pass

    return issues


def clean_registry_issues(selected_issues: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Создает откат (.reg файл) и удаляет выбранные ошибочные записи реестра.
    """
    if not selected_issues:
        return {"success": False, "message": "Не выбрано ни одной записи для очистки"}

    # 1. Формирование .reg файла для отката
    backup_lines = [
        "Windows Registry Editor Version 5.00",
        f"; ZiablWinSetup Registry Backup — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "; Данный файл восстанавливает удалённые при очистке реестра ключи и значения.",
        ""
    ]

    for item in selected_issues:
        hkey = winreg.HKEY_LOCAL_MACHINE if item.get("root_key") == "HKEY_LOCAL_MACHINE" else winreg.HKEY_CURRENT_USER
        subkey = item.get("subkey_path", "")
        act = item.get("action_type")
        vname = item.get("value_name")

        if act == "delete_key":
            backup_lines.extend(_export_key_to_reg_lines(hkey, subkey))
        elif act == "delete_value" and vname is not None:
            backup_lines.extend(_export_single_value_to_reg_lines(hkey, subkey, vname))

    # Сохраняем файл отката
    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = get_backups_dir()
    backup_file = backup_dir / f"Registry_Clean_{now_str}.reg"

    try:
        # Редактор реестра Windows предпочитает utf-16-le с BOM или utf-8
        backup_content = "\r\n".join(backup_lines) + "\r\n"
        backup_file.write_text(backup_content, encoding="utf-16")
    except Exception as e:
        logger.error(f"Error saving registry backup: {e}")
        return {"success": False, "message": f"Не удалось создать резервную копию: {e}"}

    # 2. Выполнение безопасного удаления
    cleaned_count = 0
    errors_count = 0

    for item in selected_issues:
        hkey = winreg.HKEY_LOCAL_MACHINE if item.get("root_key") == "HKEY_LOCAL_MACHINE" else winreg.HKEY_CURRENT_USER
        subkey = item.get("subkey_path", "")
        act = item.get("action_type")
        vname = item.get("value_name")

        try:
            if act == "delete_key":
                _delete_key_recursively(hkey, subkey)
                cleaned_count += 1
            elif act == "delete_value" and vname is not None:
                with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, vname)
                cleaned_count += 1
        except Exception as e:
            errors_count += 1
            logger.warning(f"Failed to delete registry item {subkey} ({vname}): {e}")

    return {
        "success": True,
        "cleaned_count": cleaned_count,
        "errors_count": errors_count,
        "backup_path": str(backup_file),
        "backup_filename": backup_file.name,
        "message": f"Успешно очищено записей: {cleaned_count}. Бэкап сохранён в «{backup_file.name}»."
    }
