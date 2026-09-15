"""
ZiablWinSetup — Детектор установленного в Windows ПО.
Быстро сканирует реестр Windows (HKLM 64/32-bit и HKCU) и стандартные пути установки,
определяя наличие установленных программ из каталога, их версии и команды удаления.
"""

import ctypes
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import winreg
from pathlib import Path
from typing import Any

from app.catalog import get_catalog

logger = logging.getLogger("WinSetup")

# Правила детекции для каждого приложения каталога
DETECTION_RULES: dict[str, dict[str, list[str]]] = {
    "obsidian": {
        "patterns": [r"Obsidian"],
        "paths": [r"Obsidian\Obsidian.exe", r"Programs\Obsidian\Obsidian.exe"],
    },
    "libreoffice": {
        "patterns": [r"LibreOffice"],
        "paths": [r"LibreOffice\program\soffice.exe"],
    },
    "openoffice": {
        "patterns": [r"OpenOffice"],
        "paths": [r"OpenOffice 4\program\soffice.exe"],
    },
    "brave": {
        "patterns": [r"^Brave$"],
        "paths": [r"BraveSoftware\Brave-Browser\Application\brave.exe"],
    },
    "dolphinanty": {
        "patterns": [r"Dolphin Anty"],
        "paths": [r"Dolphin Anty\Dolphin Anty.exe", r"Programs\Dolphin Anty\Dolphin Anty.exe"],
    },
    "claude": {
        "patterns": [r"^Claude$"],
        "paths": [r"Claude\Claude.exe", r"Programs\Claude\Claude.exe"],
    },
    "chatgpt": {
        "patterns": [r"^ChatGPT$"],
        "paths": [r"ChatGPT\ChatGPT.exe", r"Programs\ChatGPT\ChatGPT.exe"],
    },
    "pycharm": {
        "patterns": [r"PyCharm"],
        "paths": [r"JetBrains\PyCharm*\bin\pycharm64.exe"],
    },
    "codex": {
        "patterns": [r"\bCodex\b", r"OpenAI\s+Codex"],
        "paths": [
            r"Programs\Codex\Codex.exe",
            r"Codex\Codex.exe",
        ],
        "binaries": ["codex", "codex.exe"],
    },
    "opencode": {
        "patterns": [
            r"^Open\s*Code",
            r"^opencode\b",
            r"OpenCode AI",
            r"SST\.OpenCodeDesktop",
            r"SST\.opencode",
        ],
        "paths": [
            r"Programs\opencode\opencode.exe",
            r"Programs\OpenCode\OpenCode.exe",
            r"Programs\Open Code\Open Code.exe",
            r"Programs\opencode\OpenCode.exe",
            r"opencode\opencode.exe",
            r"OpenCode\OpenCode.exe",
            r"Open Code\Open Code.exe",
            r"Local\Programs\opencode\opencode.exe",
            r"Local\Programs\OpenCode\OpenCode.exe",
        ],
        "binaries": ["opencode", "opencode.exe", "opencode-desktop"],
    },
    "crystaldiskinfo": {
        "patterns": [r"CrystalDiskInfo"],
        "paths": [r"CrystalDiskInfo\DiskInfo64.exe", r"CrystalDiskInfo\DiskInfo32.exe"],
    },
    "crystaldiskmark": {
        "patterns": [r"CrystalDiskMark"],
        "paths": [r"CrystalDiskMark\DiskMark64.exe", r"CrystalDiskMark\DiskMark32.exe"],
    },
    "gpuz": {
        "patterns": [r"GPU-Z"],
        "paths": [r"GPU-Z\GPU-Z.exe"],
    },
    "furmark": {
        "patterns": [r"FurMark"],
        "paths": [r"Geeks3D\FurMark2\FurMark.exe", r"Geeks3D\FurMark*\FurMark.exe"],
    },
    "occt": {
        "patterns": [r"OCCT"],
        "paths": [r"OCBASE\OCCT\OCCT.exe"],
    },
    "uninstalltool": {
        "patterns": [r"Uninstall Tool"],
        "paths": [r"Uninstall Tool\UninstallTool.exe"],
    },
    "driverbooster": {
        "patterns": [r"Driver Booster"],
        "paths": [r"IObit\Driver Booster\*\DriverBooster.exe"],
    },
    "unlocker": {
        "patterns": [r"Unlocker"],
        "paths": [r"IObit\IObit Unlocker\Unlocker.exe"],
    },
    "unchecker": {
        "patterns": [r"Unchecker"],
        "paths": [r"Unchecker\unchecker.exe"],
    },
    "yogadns": {
        "patterns": [r"YogaDNS"],
        "paths": [r"YogaDNS\YogaDNS.exe"],
    },
    "tgwsproxy": {
        "patterns": [r"tg-ws-proxy"],
        "paths": [],
    },
    "operaproxy": {
        "patterns": [r"opera-proxy"],
        "paths": [],
    },
    "photoshop": {
        "patterns": [r"Adobe Photoshop"],
        "paths": [r"Adobe\Adobe Photoshop *\Photoshop.exe"],
    },
    "premiere": {
        "patterns": [r"Adobe Premiere"],
        "paths": [r"Adobe\Adobe Premiere Pro *\Adobe Premiere Pro.exe"],
    },
    "chrome": {
        "patterns": [r"^Google Chrome$"],
        "paths": [r"Google\Chrome\Application\chrome.exe"],
    },
    "opera-gx": {
        "patterns": [r"Opera GX"],
        "paths": [r"Programs\Opera GX\opera.exe"],
    },
    "firefox": {
        "patterns": [r"Mozilla Firefox", r"^Firefox$"],
        "paths": [
            r"Mozilla Firefox\firefox.exe",
            r"WindowsApps\Mozilla.Firefox_*\VFS\ProgramFiles\Firefox Package Root\firefox.exe",
        ],
    },
    "vlc": {
        "patterns": [r"VLC media player"],
        "paths": [r"VideoLAN\VLC\vlc.exe"],
    },
    "klite": {
        "patterns": [r"K-Lite (Codec Pack|Mega)"],
        "paths": [],
    },
    "picasa3": {
        "patterns": [r"Picasa 3"],
        "paths": [r"Google\Picasa3\Picasa3.exe"],
    },
    "obs": {
        "patterns": [r"OBS Studio"],
        "paths": [r"obs-studio\bin\64bit\obs64.exe"],
    },
    "winrar": {
        "patterns": [r"WinRAR"],
        "paths": [r"WinRAR\WinRAR.exe"],
    },
    "7zip": {
        "patterns": [r"^7-Zip"],
        "paths": [r"7-Zip\7z.exe", r"7-Zip\7zFM.exe"],
    },
    "everything": {
        "patterns": [r"^Everything"],
        "paths": [r"Everything\Everything.exe"],
    },
    "total-commander": {
        "patterns": [r"Total Commander"],
        "paths": [r"totalcmd\TOTALCMD64.EXE", r"totalcmd\TOTALCMD.EXE"],
    },
    "eartrumpet": {
        "patterns": [r"EarTrumpet"],
        "paths": [],
    },
    "cpuz": {
        "patterns": [r"CPU-Z"],
        "paths": [r"CPUID\CPU-Z\cpuz.exe"],
    },
    "hwinfo": {
        "patterns": [r"HWiNFO"],
        "paths": [r"HWiNFO64\HWiNFO64.exe"],
    },
    "sharex": {
        "patterns": [r"^ShareX"],
        "paths": [r"ShareX\ShareX.exe"],
    },
    "powertoys": {
        "patterns": [r"PowerToys"],
        "paths": [r"PowerToys\PowerToys.exe"],
    },
    "discord": {
        "patterns": [r"^Discord$"],
        "paths": [r"Discord\Update.exe"],
    },
    "telegram": {
        "patterns": [r"Telegram Desktop"],
        "paths": [r"Telegram Desktop\Telegram.exe"],
    },
    "todoist": {
        "patterns": [r"^Todoist"],
        "paths": [r"Programs\todoist\Todoist.exe"],
    },
    "git": {
        "patterns": [r"^Git version", r"^Git$"],
        "paths": [r"Git\cmd\git.exe", r"Git\bin\git.exe"],
    },
    "java": {
        "patterns": [r"Temurin", r"Java\(TM\)", r"Java \d+", r"JDK"],
        "paths": [],
    },
    "python": {
        "patterns": [r"^Python 3\."],
        "paths": [],
    },
    "vscode": {
        "patterns": [r"Microsoft Visual Studio Code"],
        "paths": [r"Microsoft VS Code\Code.exe"],
    },
    "notepadpp": {
        "patterns": [r"Notepad\+\+"],
        "paths": [r"Notepad\+\+\notepad\+\+\.exe"],
    },
    "sublimetext": {
        "patterns": [r"Sublime Text"],
        "paths": [r"Sublime Text\sublime_text.exe"],
    },
    "nvidia-app": {
        "patterns": [r"NVIDIA (App|GeForce Experience)"],
        "paths": [],
    },
    "amd-software": {
        "patterns": [r"AMD Software"],
        "paths": [],
    },
    "amnezia-vpn": {
        "patterns": [r"AmneziaVPN"],
        "paths": [r"AmneziaVPN\AmneziaVPN.exe"],
    },
    "zapret": {
        "patterns": [r"zapret"],
        "paths": [],
    },
    "anydesk": {
        "patterns": [r"AnyDesk"],
        "paths": [r"AnyDesk\AnyDesk.exe"],
    },
    "steam": {
        "patterns": [r"^Steam$"],
        "paths": [r"Steam\steam.exe"],
    },
    "qbittorrent": {
        "patterns": [r"qBittorrent"],
        "paths": [r"qBittorrent\qbittorrent.exe"],
    },
    "bittorrent": {
        "patterns": [r"^BitTorrent$"],
        "paths": [r"BitTorrent\BitTorrent.exe"],
    },
    "dropbox": {
        "patterns": [r"^Dropbox$"],
        "paths": [r"Dropbox\Client\Dropbox.exe"],
    },
}


def _get_registry_entries() -> list[dict[str, str]]:
    """Быстро считывает все записи об установленных программах из реестра Windows."""
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    entries = []
    seen = set()

    for hkey, subkey_path in roots:
        try:
            with winreg.OpenKey(hkey, subkey_path) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as app_key:
                            try:
                                dn, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                if not dn or not str(dn).strip():
                                    continue
                                dn = str(dn).strip()
                            except Exception:
                                continue

                            # Исключаем дубликаты
                            dedup_key = (dn.lower(), subkey_name.lower())
                            if dedup_key in seen:
                                continue
                            seen.add(dedup_key)

                            try:
                                ver, _ = winreg.QueryValueEx(app_key, "DisplayVersion")
                                ver = str(ver).strip()
                            except Exception:
                                ver = ""

                            try:
                                uninst, _ = winreg.QueryValueEx(app_key, "UninstallString")
                                uninst = str(uninst).strip()
                            except Exception:
                                uninst = ""

                            try:
                                quiet_uninst, _ = winreg.QueryValueEx(app_key, "QuietUninstallString")
                                quiet_uninst = str(quiet_uninst).strip()
                            except Exception:
                                quiet_uninst = ""

                            entries.append({
                                "display_name": dn,
                                "version": ver,
                                "uninstall": uninst,
                                "quiet_uninstall": quiet_uninst,
                            })
                    except Exception:
                        pass
        except Exception:
            pass

    # Сканирование установленных пакетов Windows Store / AppX / MSIX
    appx_path = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, appx_path) as key:
            num_subkeys = winreg.QueryInfoKey(key)[0]
            for i in range(num_subkeys):
                try:
                    pkg_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, pkg_name) as app_key:
                        dn = ""
                        try:
                            val, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            if val and not str(val).startswith("@{"):
                                dn = str(val).strip()
                        except Exception:
                            pass

                        parts = pkg_name.split("_")
                        base_name = parts[0]
                        ver = parts[1] if len(parts) > 1 else ""

                        if not dn:
                            dn = base_name

                        dedup_key = (dn.lower(), pkg_name.lower())
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                        uninst = f'powershell.exe -NoProfile -NonInteractive -Command "Remove-AppxPackage -Package {pkg_name}"'
                        entries.append({
                            "display_name": dn,
                            "version": ver,
                            "uninstall": uninst,
                            "quiet_uninstall": uninst,
                        })
                except Exception:
                    pass
    except Exception:
        pass

    return entries


def detect_installed_apps() -> dict[str, dict[str, Any]]:
    """
    Проверяет, какие программы из каталога установлены в системе.
    Возвращает словарь: { app_id: { 'installed': True, 'version': '...', 'uninstall_cmd': '...' } }
    """
    entries = _get_registry_entries()

    # Стандартные системные директории для проверки наличия исполняемых файлов
    prog_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LocalAppData", ""),
        os.environ.get("AppData", ""),
    ]

    results: dict[str, dict[str, Any]] = {}
    catalog = get_catalog()

    for app in catalog:
        rule = DETECTION_RULES.get(app.id, {"patterns": [re.escape(app.name)], "paths": []})
        match_info = None

        # 1. Поиск в реестре Windows
        for e in entries:
            dn = e["display_name"]
            for pat in rule["patterns"]:
                if re.search(pat, dn, re.IGNORECASE):
                    match_info = {
                        "installed": True,
                        "name": dn,
                        "version": e["version"],
                        "uninstall_cmd": e["uninstall"],
                        "quiet_uninstall": e["quiet_uninstall"],
                    }
                    break
            if match_info:
                break

        # 2. Fallback: поиск исполняемых файлов в стандартных папках установки
        if not match_info:
            for rel_path in rule.get("paths", []):
                for base in prog_dirs:
                    if not base:
                        continue
                    full_path = Path(base) / rel_path
                    if full_path.exists():
                        match_info = {
                            "installed": True,
                            "name": app.name,
                            "version": "",
                            "uninstall_cmd": "",
                            "quiet_uninstall": "",
                        }
                        break
                if match_info:
                    break

        # 3. Fallback: проверка исполняемых файлов в PATH (shutil.which)
        if not match_info:
            for bin_name in rule.get("binaries", []):
                found_bin = shutil.which(bin_name)
                if found_bin:
                    match_info = {
                        "installed": True,
                        "name": app.name,
                        "version": "",
                        "uninstall_cmd": "",
                        "quiet_uninstall": "",
                    }
                    break

        if match_info:
            results[app.id] = match_info

    logger.info(f"Обнаружено {len(results)} установленных приложений из каталога")
    return results


def uninstall_app(app_id: str) -> dict[str, Any]:
    """
    Запускает деинсталлятор для указанного приложения.
    Поддерживает как классические EXE деинсталляторы, так и MSI/MsiExec.
    """
    detected = detect_installed_apps()
    app_info = detected.get(app_id)

    if not app_info:
        return {"success": False, "error": f"Приложение '{app_id}' не обнаружено в установленных."}

    cmd = app_info.get("uninstall_cmd") or app_info.get("quiet_uninstall")
    if not cmd:
        return {
            "success": False,
            "error": f"Не найдена строка деинсталляции для '{app_id}'. Удалите приложение через Параметры Windows.",
        }

    logger.info(f"Запуск деинсталляции {app_id}: {cmd}")

    try:
        # Проверяем, является ли команда вызовом msiexec или powershell
        cmd_lower = cmd.lower()
        if "msiexec" in cmd_lower or "powershell" in cmd_lower:
            subprocess.Popen(cmd, shell=True)
            return {"success": True, "message": "Запущен процесс деинсталляции."}

        # Парсим исполняемый файл и аргументы
        # Часто строка в реестре имеет вид: "C:\Path\uninstall.exe" /arg1 /arg2
        exe_path = ""
        args = ""

        if cmd.startswith('"'):
            end_quote = cmd.find('"', 1)
            if end_quote != -1:
                exe_path = cmd[1:end_quote]
                args = cmd[end_quote + 1:].strip()
        else:
            parts = cmd.split(maxsplit=1)
            exe_path = parts[0]
            args = parts[1] if len(parts) > 1 else ""

        # Запускаем через ShellExecuteW с запросом прав при необходимости
        res = ctypes.windll.shell32.ShellExecuteW(
            None,
            "open",
            exe_path,
            args,
            str(Path(exe_path).parent) if Path(exe_path).is_file() else None,
            1,  # SW_SHOWNORMAL
        )

        if res <= 32:  # Код ошибки ShellExecute
            # Пробуем с повышением прав runas
            res_admin = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                exe_path,
                args,
                None,
                1,
            )
            if res_admin <= 32:
                # В крайнем случае shell=True
                subprocess.Popen(cmd, shell=True)

        return {"success": True, "message": "Процесс деинсталляции запущен."}
    except Exception as e:
        logger.error(f"Ошибка при запуске деинсталлятора: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
