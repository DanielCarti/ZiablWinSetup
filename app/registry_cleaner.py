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
import subprocess
import winreg
from pathlib import Path
from typing import Any

from app.utils import get_user_documents_dir

logger = logging.getLogger("WinSetup")

def get_backups_dir() -> Path:
    """Возвращает путь к папке бэкапов реестра в Документах пользователя."""
    b_dir = get_user_documents_dir() / "ZiablWinSetup_Backups"
    b_dir.mkdir(parents=True, exist_ok=True)
    return b_dir


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

    key = None
    for flag in (winreg.KEY_READ, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0), winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            key = winreg.OpenKey(hkey_constant, subkey_path, 0, flag)
            break
        except Exception:
            pass

    if not key:
        return lines

    try:
        with key:
            lines.append(full_key_header)
            num_subkeys, num_values, _ = winreg.QueryInfoKey(key)

            for i in range(num_values):
                try:
                    vn, val, val_type = winreg.EnumValue(key, i)
                    v_name_escaped = f'"{vn.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"' if vn else "@"

                    if val_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                        s_val = str(val).replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{v_name_escaped}="{s_val}"')
                    elif val_type == winreg.REG_DWORD:
                        lines.append(f"{v_name_escaped}=dword:{val:08x}")
                    elif val_type == winreg.REG_MULTI_SZ:
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

    for flag in (winreg.KEY_READ, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0), winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            with winreg.OpenKey(hkey_constant, subkey_path, 0, flag) as key:
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
                return lines
        except Exception:
            pass
    return lines


def _item_exists(hkey_constant, subkey_path: str, value_name: str | None = None) -> bool:
    """Проверяет реальное существование раздела или параметра реестра во всех доступных разрядностях."""
    flags_to_check = [winreg.KEY_READ]
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        flags_to_check.append(winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    if hasattr(winreg, "KEY_WOW64_32KEY"):
        flags_to_check.append(winreg.KEY_READ | winreg.KEY_WOW64_32KEY)

    for flag in flags_to_check:
        try:
            with winreg.OpenKey(hkey_constant, subkey_path, 0, flag) as k:
                if value_name is not None:
                    try:
                        winreg.QueryValueEx(k, value_name)
                        return True
                    except FileNotFoundError:
                        pass
                else:
                    return True
        except FileNotFoundError:
            pass
        except OSError:
            # Если ключ существует, но доступ на чтение ограничен
            return True
    return False


def _delete_key_recursively(hkey_constant, subkey_path: str) -> bool:
    """Рекурсивное удаление ключа реестра со всеми подпапками (для текущего процесса)."""
    try:
        with winreg.OpenKey(hkey_constant, subkey_path, 0, winreg.KEY_READ) as key:
            subkeys = []
            while True:
                try:
                    subkeys.append(winreg.EnumKey(key, len(subkeys)))
                except OSError:
                    break
        for sub_name in subkeys:
            _delete_key_recursively(hkey_constant, f"{subkey_path}\\{sub_name}")
    except Exception:
        pass

    parent_path, sep, key_name = subkey_path.rpartition("\\")
    for flag in (0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            if parent_path:
                with winreg.OpenKey(hkey_constant, parent_path, 0, (winreg.KEY_SET_VALUE | 0x00010000 | flag)) as parent:
                    winreg.DeleteKey(parent, key_name)
            else:
                winreg.DeleteKey(hkey_constant, key_name)
            return True
        except Exception:
            pass
    return False


def _delete_issues_elevated(issues: list[dict[str, Any]]) -> None:
    """
    Удаляет выбранные записи через единый пакетный скрипт с запросом прав Администратора (UAC).
    Показывает ОДИН UAC-запрос сразу для всех выбранных элементов.
    """
    if not issues:
        return

    import tempfile
    import uuid
    from app.installer import run_with_elevation

    temp_id = uuid.uuid4().hex[:8]
    temp_dir = Path(tempfile.gettempdir())
    reg_del_file = temp_dir / f"ziabl_clean_{temp_id}.reg"
    bat_file = temp_dir / f"ziabl_clean_{temp_id}.bat"

    reg_lines = [
        "Windows Registry Editor Version 5.00",
        ""
    ]
    bat_lines = [
        "@echo off",
        "chcp 65001 >nul",
        f'reg.exe import "{reg_del_file.resolve()}" >nul 2>&1'
    ]

    for item in issues:
        root_name = item.get("root_key", "HKEY_LOCAL_MACHINE")
        short_root = "HKLM" if "LOCAL_MACHINE" in root_name else "HKCU"
        subkey = item.get("subkey_path", "").strip("\\")
        act = item.get("action_type")
        vname = item.get("value_name")

        if act == "delete_key":
            reg_lines.append(f"[-{root_name}\\{subkey}]")
            reg_lines.append("")
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" /f >nul 2>&1')
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" /f /reg:32 >nul 2>&1')
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" /f /reg:64 >nul 2>&1')
            if "wow6432node\\" in subkey.lower():
                alt_sub = re.sub(r'(?i)wow6432node\\', '', subkey)
                bat_lines.append(f'reg.exe delete "{short_root}\\{alt_sub}" /f /reg:32 >nul 2>&1')

        elif act == "delete_value" and vname is not None:
            v_escaped = f'"{vname.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"' if vname else "@"
            reg_lines.append(f"[{root_name}\\{subkey}]")
            reg_lines.append(f"{v_escaped}=-")
            reg_lines.append("")
            v_arg = f'/v "{vname}"' if vname else "/ve"
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" {v_arg} /f >nul 2>&1')
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" {v_arg} /f /reg:32 >nul 2>&1')
            bat_lines.append(f'reg.exe delete "{short_root}\\{subkey}" {v_arg} /f /reg:64 >nul 2>&1')

    try:
        reg_del_file.write_text("\r\n".join(reg_lines) + "\r\n", encoding="utf-16")
        bat_file.write_text("\r\n".join(bat_lines) + "\r\n", encoding="utf-8")
        run_with_elevation("cmd.exe", ["/c", str(bat_file.resolve())], show_window=False)
    finally:
        try:
            if reg_del_file.is_file():
                reg_del_file.unlink(missing_ok=True)
            if bat_file.is_file():
                bat_file.unlink(missing_ok=True)
        except Exception:
            pass


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
    Гарантирует фактическую проверку удаления через _item_exists().
    """
    if not selected_issues:
        return {
            "success": False,
            "cleaned_count": 0,
            "errors_count": 0,
            "cleaned_ids": [],
            "message": "Не выбрано ни одной записи для очистки"
        }

    from app.utils import is_admin

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
        # Редактор реестра Windows предпочитает utf-16-le с BOM
        backup_content = "\r\n".join(backup_lines) + "\r\n"
        backup_file.write_text(backup_content, encoding="utf-16")
    except Exception as e:
        logger.error(f"Error saving registry backup: {e}")
        return {
            "success": False,
            "cleaned_count": 0,
            "errors_count": len(selected_issues),
            "cleaned_ids": [],
            "message": f"Не удалось создать резервную копию: {e}"
        }

    # 2. Попытка прямого удаления (для HKCU или если процесс запущен от Администратора)
    remaining_for_elevated = []
    currently_admin = is_admin()

    for item in selected_issues:
        hkey = winreg.HKEY_LOCAL_MACHINE if item.get("root_key") == "HKEY_LOCAL_MACHINE" else winreg.HKEY_CURRENT_USER
        subkey = item.get("subkey_path", "")
        act = item.get("action_type")
        vname = item.get("value_name")

        if hkey == winreg.HKEY_CURRENT_USER or currently_admin:
            try:
                if act == "delete_key":
                    _delete_key_recursively(hkey, subkey)
                elif act == "delete_value" and vname is not None:
                    with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.DeleteValue(key, vname)
            except Exception as e:
                logger.debug(f"Direct delete failed for {subkey}: {e}")

        # Проверяем, существует ли еще ключ на самом деле
        if _item_exists(hkey, subkey, vname):
            remaining_for_elevated.append(item)

    # 3. Если остались системные записи HKLM или требующие прав админа, запускаем единый UAC-скрипт
    uac_declined = False
    if remaining_for_elevated:
        try:
            _delete_issues_elevated(remaining_for_elevated)
        except PermissionError:
            uac_declined = True
            logger.info("UAC elevation was cancelled by user during registry clean.")
        except Exception as e:
            logger.warning(f"Error during elevated registry clean: {e}")

    # 4. ИТОГОВАЯ ЧЕСТНАЯ ПРОВЕРКА РЕАЛЬНОГО УДАЛЕНИЯ КАЖДОГО ЭЛЕМЕНТА
    cleaned_ids = []
    failed_items = []

    for item in selected_issues:
        hkey = winreg.HKEY_LOCAL_MACHINE if item.get("root_key") == "HKEY_LOCAL_MACHINE" else winreg.HKEY_CURRENT_USER
        subkey = item.get("subkey_path", "")
        vname = item.get("value_name")

        if not _item_exists(hkey, subkey, vname):
            cleaned_ids.append(item["id"])
        else:
            failed_items.append(item)

    cleaned_count = len(cleaned_ids)
    errors_count = len(failed_items)

    if cleaned_count == 0:
        msg = (
            "Запрос прав Администратора (UAC) был отклонён. Системные записи реестра не удалены."
            if uac_declined
            else "Не удалось удалить выбранные записи реестра (отказано в доступе Windows)."
        )
        return {
            "success": False,
            "cleaned_count": 0,
            "errors_count": errors_count,
            "cleaned_ids": [],
            "backup_path": str(backup_file),
            "backup_filename": backup_file.name,
            "message": msg
        }

    if errors_count > 0:
        msg = f"Очищено записей: {cleaned_count}. Не удалось очистить: {errors_count} (требуются права администратора)."
    else:
        msg = f"Успешно очищено записей: {cleaned_count}. Бэкап сохранён в «{backup_file.name}»."

    return {
        "success": True,
        "cleaned_count": cleaned_count,
        "errors_count": errors_count,
        "cleaned_ids": cleaned_ids,
        "backup_path": str(backup_file),
        "backup_filename": backup_file.name,
        "message": msg
    }


def restore_registry_backup(reg_file_path: str) -> tuple[bool, str]:
    """
    Восстанавливает записи реестра из выбранного .reg файла отката.
    Использует системную утилиту reg.exe import с авто-повышением прав при необходимости.
    """
    p = Path(reg_file_path)
    if not p.is_file():
        return False, f"Файл резервной копии не найден: {reg_file_path}"
    if p.suffix.lower() != ".reg":
        return False, "Выбранный файл не является файлом реестра (.reg)."

    try:
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(
            ["reg.exe", "import", str(p.resolve())],
            capture_output=True,
            text=False,
            creationflags=no_win
        )
        if res.returncode == 0:
            return True, f"Записи реестра успешно восстановлены из «{p.name}»."

        # reg.exe является консольной утилитой и выводит ошибки в кодировке OEM (CP866 в RU Windows)
        err_msg = ""
        if res.stderr:
            for enc in ("cp866", "utf-8", "cp1251"):
                try:
                    err_msg = res.stderr.decode(enc).strip()
                    if err_msg:
                        break
                except UnicodeDecodeError:
                    continue
            if not err_msg:
                err_msg = res.stderr.decode("latin1", errors="replace").strip()

        # Если не хватило прав (например, для HKEY_LOCAL_MACHINE), запрашиваем повышение прав
        from app.installer import run_with_elevation
        try:
            code = run_with_elevation("reg.exe", ["import", str(p.resolve())], show_window=False)
            if code == 0:
                return True, f"Записи реестра успешно восстановлены с правами Администратора из «{p.name}»."
        except PermissionError:
            return False, "Запрос прав Администратора (UAC) был отклонён пользователем."
        if not err_msg:
            err_msg = "Ошибка доступа при импорте в реестр."
        return False, f"Не удалось импортировать файл (код {code}): {err_msg}"
    except Exception as e:
        logger.error(f"Error restoring registry backup from {reg_file_path}: {e}")
        return False, f"Ошибка восстановления реестра: {e}"
