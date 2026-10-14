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
        "patterns": [r"^Python 3\.\d+(?:\.\d+)?\s*\((?:64|32)-bit\)$", r"^Python 3\."],
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
    "rufus": {
        "patterns": [r"Rufus"],
        "paths": [r"Rufus\rufus*.exe", r"rufus*.exe", r"Programs\Rufus\rufus*.exe"],
    },
    "hydralauncher": {
        "patterns": [r"Hydra"],
        "paths": [r"Hydra\Hydra.exe", r"Programs\Hydra\Hydra.exe"],
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
        matching_entries = []
        for e in entries:
            dn = e["display_name"]
            for pat in rule["patterns"]:
                if re.search(pat, dn, re.IGNORECASE):
                    ver = e["version"]
                    if app.id == "python":
                        # Очищаем внутренний формат MSI (3.12.10150.0 -> 3.12.10)
                        vm = re.search(r"Python\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)", dn, re.IGNORECASE)
                        if vm:
                            ver = vm.group(1)
                    matching_entries.append({
                        "installed": True,
                        "name": dn,
                        "version": ver,
                        "uninstall_cmd": e["uninstall"],
                        "quiet_uninstall": e["quiet_uninstall"],
                    })
                    break
        if matching_entries:
            from app.updater import parse_version_tuple
            if app.id == "python":
                roots = [m for m in matching_entries if not any(w in m["name"].lower() for w in ("libraries", "suite", "pip", "documentation", "tcl", "path", "utility", "tools", "standard library", "executables"))]
                if roots:
                    matching_entries = roots
            matching_entries.sort(key=lambda x: parse_version_tuple(x.get("version", "")), reverse=True)
            match_info = matching_entries[0]
            if app.id == "python" and match_info.get("version"):
                match_info["name"] = f"Python {match_info['version']}"

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

        # 4. Fallback: проверка portable-приложений и ярлыков на Рабочем столе
        if not match_info and (app.installer_type == "portable" or app.id in ("gpuz", "tgwsproxy", "operaproxy", "zapret")):
            try:
                from app.installer import get_desktop_path, get_exe_dir, _resolve_extract_path
                from app.settings import load_settings
                desktop = get_desktop_path()
                exe_dir = get_exe_dir()
                extract_path = _resolve_extract_path(load_settings())

                desktop_shortcuts = [
                    desktop / f"{app.name}.lnk",
                    desktop / f"{app.id}.lnk",
                    desktop / "GPU-Z.lnk",
                    desktop / "TechPowerUp GPU-Z.lnk",
                ]
                portable_paths = [
                    extract_path / app.name / f"{app.name}.exe",
                    extract_path / f"{app.name}.exe",
                    exe_dir / app.name / f"{app.name}.exe",
                    exe_dir / f"{app.name}.exe",
                    exe_dir / "Portable" / app.name / f"{app.name}.exe",
                    desktop / f"{app.name}.exe",
                ]

                # Проверка сохранённого файла версии
                ver_candidates = [
                    extract_path / app.name / ".version",
                    exe_dir / app.name / ".version",
                    desktop / app.name / ".version",
                    desktop / f"{app.name}.version",
                ]
                saved_ver = ""
                for vf in ver_candidates:
                    if vf.exists():
                        try:
                            saved_ver = vf.read_text(encoding="utf-8").strip()
                            if saved_ver:
                                break
                        except Exception:
                            pass

                # Для Zapret и подобных утилит ищем версию в папках архивов
                if not saved_ver and app.id in ("zapret", "operaproxy", "tgwsproxy"):
                    for base_dir in (extract_path, desktop, exe_dir):
                        if base_dir and base_dir.exists():
                            for sub in base_dir.glob(f"{app.id}*"):
                                if sub.is_dir():
                                    zv_file = sub / ".version"
                                    if zv_file.exists():
                                        try:
                                            saved_ver = zv_file.read_text(encoding="utf-8").strip()
                                        except Exception:
                                            pass
                                    if not saved_ver:
                                        m_v = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", sub.name)
                                        if m_v:
                                            saved_ver = m_v.group(1)
                                    if saved_ver:
                                        break
                        if saved_ver:
                            break

                found_path = None
                for sc in desktop_shortcuts:
                    if sc.exists():
                        found_path = str(sc)
                        break

                if not found_path:
                    for pp in portable_paths:
                        if pp.exists():
                            found_path = str(pp)
                            break

                if found_path:
                    from app.utils import get_file_version
                    det_ver = saved_ver
                    if not det_ver:
                        for pp in portable_paths:
                            if pp.exists():
                                pe_v = get_file_version(pp)
                                if pe_v and pe_v != "0.0":
                                    det_ver = pe_v
                                    break
                    if not det_ver:
                        det_ver = "Portable"

                    match_info = {
                        "installed": True,
                        "name": app.name,
                        "version": det_ver,
                        "uninstall_cmd": "",
                        "quiet_uninstall": "",
                        "path": found_path,
                    }
            except Exception:
                pass

        if match_info:
            results[app.id] = match_info

    logger.info(f"Обнаружено {len(results)} установленных приложений из каталога")
    return results


def find_leftovers(app_id: str, app_info: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """
    Сканирует систему на наличие остаточных папок, ярлыков и ключей реестра
    без их фактического удаления (для показа пользователю в диалоге Uninstall Tool).
    """
    found: dict[str, list[str]] = {"dirs": [], "shortcuts": [], "registry": []}
    app_name = (app_info.get("name") if app_info else "") or app_id

    keywords = set()
    for raw in [app_id, app_name]:
        clean = re.sub(r"[^\w\s-]", "", raw).strip().lower()
        if len(clean) >= 3 and clean not in ("windows", "program", "system", "setup", "update", "temp", "install"):
            keywords.add(clean)
            for part in clean.split():
                if len(part) >= 4 and part not in ("tool", "client", "edition", "pro", "free", "beta", "lite"):
                    keywords.add(part)

    if not keywords:
        return found

    def is_safe_match(name: str) -> bool:
        lower = name.lower()
        return any(kw in lower for kw in keywords)

    protected_roots = {
        Path("C:\\"),
        Path(os.environ.get("SystemDrive", "C:") + "\\"),
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("APPDATA", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path(os.environ.get("ProgramData", "C:\\ProgramData")),
        Path.home(),
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
    }

    candidate_dirs: list[Path] = []
    if app_info and app_info.get("path"):
        p = Path(app_info["path"])
        if p.is_file():
            candidate_dirs.append(p.parent)
        elif p.is_dir():
            candidate_dirs.append(p)

    appdata = Path(os.environ.get("APPDATA", ""))
    localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
    progdata = Path(os.environ.get("ProgramData", "C:\\ProgramData"))
    pf = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
    pfx86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))

    # 1. Поиск остаточных папок
    for base in [appdata, localappdata, progdata, pf, pfx86]:
        if not base.exists():
            continue
        try:
            for item in base.iterdir():
                if item.is_dir() and item not in protected_roots and is_safe_match(item.name):
                    candidate_dirs.append(item)
        except Exception:
            pass

    # Специальные пути для CLI/npm инструментов (например, opencode)
    if app_id == "opencode":
        npm_dir = appdata / "npm"
        if npm_dir.exists():
            try:
                for script in ["opencode", "opencode.cmd", "opencode.ps1"]:
                    sp = npm_dir / script
                    if sp.exists():
                        found["shortcuts"].append(str(sp))
                nm = npm_dir / "node_modules" / "opencode-ai"
                if nm.exists():
                    candidate_dirs.append(nm)
            except Exception:
                pass

    for c_dir in set(candidate_dirs):
        if c_dir in protected_roots or not c_dir.exists() or len(c_dir.parts) < 3:
            continue
        found["dirs"].append(str(c_dir))

    # 2. Поиск остаточных ярлыков
    shortcut_locations = [
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Desktop",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        progdata / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]

    for s_loc in shortcut_locations:
        if not s_loc.exists():
            continue
        try:
            for lnk in s_loc.rglob("*.lnk"):
                if is_safe_match(lnk.stem):
                    found["shortcuts"].append(str(lnk))
        except Exception:
            pass

    # 3. Поиск остаточных ключей реестра
    reg_roots = [
        (winreg.HKEY_CURRENT_USER, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node"),
    ]
    for hkey, sub in reg_roots:
        try:
            with winreg.OpenKey(hkey, sub, 0, winreg.KEY_READ) as parent_key:
                idx = 0
                while True:
                    try:
                        kn = winreg.EnumKey(parent_key, idx)
                        if is_safe_match(kn):
                            found["registry"].append(f"{sub}\\{kn}")
                        idx += 1
                    except OSError:
                        break
        except Exception:
            pass

    return found


def delete_leftovers(leftovers: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Безопасно удаляет указанные остаточные файлы, папки, ярлыки и ключи реестра.
    """
    cleaned: dict[str, list[str]] = {"dirs": [], "shortcuts": [], "registry": []}

    protected_roots = {
        Path("C:\\"),
        Path(os.environ.get("SystemDrive", "C:") + "\\"),
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("APPDATA", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path(os.environ.get("ProgramData", "C:\\ProgramData")),
        Path.home(),
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
    }

    # Удаление папок
    for d_str in leftovers.get("dirs", []):
        p = Path(d_str)
        if p.exists() and p not in protected_roots and len(p.parts) >= 3:
            try:
                shutil.rmtree(p, ignore_errors=True)
                if not p.exists():
                    cleaned["dirs"].append(d_str)
                    logger.info(f"Удалены остатки папки: {d_str}")
            except Exception as e:
                logger.debug(f"Не удалось удалить папку {d_str}: {e}")

    # Удаление ярлыков и скриптов
    for s_str in leftovers.get("shortcuts", []):
        p = Path(s_str)
        if p.exists():
            try:
                p.unlink(missing_ok=True)
                cleaned["shortcuts"].append(s_str)
                logger.info(f"Удален остаточный файл/ярлык: {s_str}")
            except Exception:
                pass

    # Удаление ключей реестра
    for r_str in leftovers.get("registry", []):
        parts = r_str.split("\\", 1)
        if len(parts) == 2:
            sub, kn = parts
            for hkey in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    with winreg.OpenKey(hkey, sub, 0, winreg.KEY_SET_VALUE) as parent_key:
                        winreg.DeleteKey(parent_key, kn)
                        cleaned["registry"].append(r_str)
                        logger.info(f"Удален остаточный ключ реестра: {r_str}")
                        break
                except Exception:
                    pass

    return cleaned


def clean_leftovers(app_id: str, app_info: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """
    Находит и сразу удаляет остатки программы.
    """
    found = find_leftovers(app_id, app_info)
    return delete_leftovers(found)


def uninstall_app(app_id: str) -> dict[str, Any]:
    """
    Запускает деинсталлятор для указанного приложения и ожидает его завершения.
    Если официальный деинсталлятор отсутствует (например, portable/npm/winget):
    пытается выполнить деинсталляцию через winget или npm, либо подготавливает очистку файлов.
    """
    detected = detect_installed_apps()
    app_info = detected.get(app_id)

    if not app_info:
        return {"success": False, "error": f"Приложение '{app_id}' не обнаружено в установленных."}

    cmd = app_info.get("uninstall_cmd") or app_info.get("quiet_uninstall")
    
    # 1. Попытка деинсталляции через официальный UninstallString
    if cmd:
        logger.info(f"Запуск официального деинсталлятора {app_id}: {cmd}")
        try:
            subprocess.run(f'cmd.exe /c "{cmd}"', shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Ошибка вызова uninstaller {cmd}: {e}")
    else:
        # 2. Если UninstallString нет в реестре:
        winget_id = None
        from app.catalog import ALL_APPS
        for a in ALL_APPS:
            if a.id == app_id and a.winget_id:
                winget_id = a.winget_id
                break
        
        winget_uninstalled = False
        if winget_id:
            logger.info(f"Попытка удаления через winget: {winget_id}")
            try:
                w_res = subprocess.run(
                    ["winget", "uninstall", "--id", winget_id, "--silent", "--accept-source-agreements"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    timeout=45
                )
                if w_res.returncode == 0:
                    winget_uninstalled = True
                    logger.info(f"Успешно удалено через winget: {winget_id}")
            except Exception as ex:
                logger.debug(f"Winget uninstall не удался: {ex}")

        # Проверяем наличие специфического npm пакета (например, opencode)
        if not winget_uninstalled and app_id == "opencode":
            try:
                subprocess.run(
                    ["cmd.exe", "/c", "npm uninstall -g opencode-ai & npm uninstall -g opencode"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    timeout=30
                )
            except Exception:
                pass

    # 3. Находим остаточные файлы, папки, ярлыки и ключи реестра
    leftovers = find_leftovers(app_id, app_info)
    return {
        "success": True,
        "app_id": app_id,
        "app_name": app_info.get("name", app_id),
        "leftovers": leftovers
    }
