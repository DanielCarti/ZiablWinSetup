"""
ZiablWinSetup — Модуль управления встроенными Metro / UWP приложениями Windows.
Предоставляет удаление в один клик и восстановление встроенных приложений Windows 10/11.
"""

import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


@dataclass
class MetroAppDef:
    id: str
    name: str
    name_en: str
    description: str
    description_en: str
    icon: str
    package_patterns: list[str]
    store_id: str
    can_remove: bool = True

    def to_dict(self, installed: bool, lang: str = "ru") -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name if lang != "en" else self.name_en,
            "description": self.description if lang != "en" else self.description_en,
            "icon": self.icon,
            "store_id": self.store_id,
            "can_remove": self.can_remove,
            "installed": installed,
        }


METRO_APPS: list[MetroAppDef] = [
    MetroAppDef(
        id="weather",
        name="MSN Погода",
        name_en="MSN Weather",
        description="Прогноз погоды, карты осадков и виджеты от Microsoft.",
        description_en="Weather forecast, precipitation radar, and live tiles.",
        icon="🌤️",
        package_patterns=["*BingWeather*"],
        store_id="9WZDNCRFJ3Q2",
    ),
    MetroAppDef(
        id="news",
        name="Microsoft Новости",
        name_en="Microsoft News",
        description="Новостная лента MSN и встроенный контент виджетов Windows.",
        description_en="MSN news feed and Windows widget news content.",
        icon="📰",
        package_patterns=["*BingNews*"],
        store_id="9WZDNCRFHVFW",
    ),
    MetroAppDef(
        id="camera",
        name="Камера Windows",
        name_en="Windows Camera",
        description="Стандартное UWP-приложение для веб-камеры и съемки фото/видео.",
        description_en="Built-in webcam photo and video recording application.",
        icon="📷",
        package_patterns=["*WindowsCamera*"],
        store_id="9WZDNCRFJBBG",
    ),
    MetroAppDef(
        id="maps",
        name="Карты Windows",
        name_en="Windows Maps",
        description="Встроенные оффлайн-карты, навигация и геолокация от Microsoft.",
        description_en="Offline maps, navigation, and location services by Microsoft.",
        icon="🗺️",
        package_patterns=["*WindowsMaps*"],
        store_id="9WZDNCRBXB69",
    ),
    MetroAppDef(
        id="sound_recorder",
        name="Запись голоса (Диктофон)",
        name_en="Sound Recorder",
        description="Базовое приложение записи звука и заметок с микрофона.",
        description_en="Basic audio and voice recording tool.",
        icon="🎙️",
        package_patterns=["*WindowsSoundRecorder*"],
        store_id="9WZDNCRFHWKN",
    ),
    MetroAppDef(
        id="phone_link",
        name="Связь с телефоном (Phone Link)",
        name_en="Phone Link",
        description="Синхронизация звонков, SMS и уведомлений со смартфона Android/iOS.",
        description_en="Sync calls, texts, and notifications with Android/iOS phones.",
        icon="📱",
        package_patterns=["*YourPhone*"],
        store_id="9NBLGGH4VST9",
    ),
    MetroAppDef(
        id="feedback_hub",
        name="Центр отзывов (Feedback Hub)",
        name_en="Feedback Hub",
        description="Отправка диагностических отчетов и предложений в Microsoft.",
        description_en="Send diagnostic reports and suggestions to Microsoft.",
        icon="💬",
        package_patterns=["*WindowsFeedbackHub*"],
        store_id="9NBLGGH4R32N",
    ),
    MetroAppDef(
        id="get_help",
        name="Техническая поддержка (Get Help)",
        name_en="Get Help",
        description="Справка и виртуальный агент службы поддержки Microsoft.",
        description_en="Online troubleshooting and Microsoft support virtual agent.",
        icon="❓",
        package_patterns=["*GetHelp*"],
        store_id="9PKDZBMV1H3T",
    ),
    MetroAppDef(
        id="tips",
        name="Советы Windows (Tips)",
        name_en="Windows Tips",
        description="Обучающие подсказки и руководство по функциям Windows.",
        description_en="Introductory tutorials and feature walkthroughs for Windows.",
        icon="💡",
        package_patterns=["*Getstarted*"],
        store_id="9WZDNCRFJBDG",
    ),
    MetroAppDef(
        id="solitaire",
        name="Пасьянсы (Solitaire Collection)",
        name_en="Microsoft Solitaire Collection",
        description="Предустановленная карточная игра (Косынка, Паук, Солитер) со встроенной рекламой.",
        description_en="Pre-installed card games (Klondike, Spider, FreeCell) with ads.",
        icon="🃏",
        package_patterns=["*MicrosoftSolitaireCollection*"],
        store_id="9WZDNCRFHWD2",
    ),
    MetroAppDef(
        id="zune_video",
        name="Кино и ТВ (Movies & TV)",
        name_en="Films & TV",
        description="Встроенный UWP-плеер видеофайлов и магазин фильмов.",
        description_en="Built-in UWP video player and digital media marketplace.",
        icon="🎬",
        package_patterns=["*ZuneVideo*"],
        store_id="9WZDNCRFJ3P2",
    ),
    MetroAppDef(
        id="zune_music",
        name="Windows Медиаплеер (Groove)",
        name_en="Windows Media Player",
        description="Стандартный музыкальный проигрыватель Windows 11.",
        description_en="Default audio and music player in Windows 11.",
        icon="🎵",
        package_patterns=["*ZuneMusic*"],
        store_id="9WZDNCRFJ3PT",
    ),
    MetroAppDef(
        id="xbox_overlay",
        name="Xbox Game Bar",
        name_en="Xbox Game Bar",
        description="Игровой оверлей Windows (Win+G): запись экрана, виджеты и мониторинг FPS.",
        description_en="Gaming overlay (Win+G) with screen recording, widgets, and FPS counter.",
        icon="🎮",
        package_patterns=["*XboxGamingOverlay*"],
        store_id="9NZKPSTSNW4P",
    ),
    MetroAppDef(
        id="xbox_app",
        name="Приложение Xbox",
        name_en="Xbox App",
        description="Клиент сервиса Xbox Game Pass и облачных игр.",
        description_en="Official Xbox client for Game Pass and social gaming.",
        icon="🎯",
        package_patterns=["*XboxApp*", "*GamingApp*"],
        store_id="9MV0B5HZVK9Z",
    ),
    MetroAppDef(
        id="cortana",
        name="Cortana (Кортана)",
        name_en="Cortana",
        description="Устаревший голосовой ассистент от Microsoft.",
        description_en="Legacy voice assistant and productivity helper.",
        icon="⭕",
        package_patterns=["*549981C3F5F10*"],
        store_id="9NBLGGH4NS1M",
    ),
    MetroAppDef(
        id="paint_3d",
        name="Paint 3D",
        name_en="Paint 3D",
        description="Редактор трехмерных моделей и графики.",
        description_en="3D modeling and creative graphics editor.",
        icon="🧊",
        package_patterns=["*MSPaint*", "*Paint3D*"],
        store_id="9NBLGGH5FV99",
    ),
    MetroAppDef(
        id="sticky_notes",
        name="Записки (Sticky Notes)",
        name_en="Microsoft Sticky Notes",
        description="Быстрые цветные стикеры-заметки на Рабочем столе.",
        description_en="Quick desktop digital sticky notes and memos.",
        icon="📝",
        package_patterns=["*MicrosoftStickyNotes*"],
        store_id="9NBLGGH4QGHW",
    ),
    MetroAppDef(
        id="alarms",
        name="Часы и будильники",
        name_en="Windows Clock",
        description="Таймеры, секундомер, будильники и мировое время.",
        description_en="Stopwatch, timer, alarm clock, and world clock.",
        icon="⏰",
        package_patterns=["*WindowsAlarms*"],
        store_id="9WZDNCRFJ3PR",
    ),
    MetroAppDef(
        id="calculator",
        name="Калькулятор Windows",
        name_en="Windows Calculator",
        description="Встроенный калькулятор с инженерным режимом и конвертером валют.",
        description_en="Built-in calculator with scientific mode and currency converter.",
        icon="🔢",
        package_patterns=["*WindowsCalculator*"],
        store_id="9WZDNCRFHVN5",
    ),
    MetroAppDef(
        id="clipchamp",
        name="Clipchamp (Видеоредактор)",
        name_en="Clipchamp Video Editor",
        description="Встроенный в Windows 11 онлайн/UWP редактор видеоклипов.",
        description_en="Built-in video creation and trimming tool in Windows 11.",
        icon="✂️",
        package_patterns=["*Clipchamp*"],
        store_id="9P1J8S7CCWWT",
    ),
    MetroAppDef(
        id="people",
        name="Люди (Контакты)",
        name_en="Microsoft People",
        description="Интеграция адресной книги и контактов Windows.",
        description_en="Contact management and address book integration.",
        icon="👥",
        package_patterns=["*People*"],
        store_id="9NBLGGH10PG8",
    ),
]


def _get_installed_package_names() -> set[str]:
    """Возвращает список всех зарегистрированных для текущего пользователя Appx пакетов."""
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "Get-AppxPackage | Select-Object -ExpandProperty Name"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NO_WINDOW)
        names = {line.strip() for line in res.stdout.splitlines() if line.strip()}
        return names
    except Exception:
        return set()


def get_all_metro_apps(lang: str = "ru") -> list[dict[str, Any]]:
    """Возвращает список всех Metro-приложений с актуальным статусом установки."""
    installed_names = _get_installed_package_names()
    result = []
    for app in METRO_APPS:
        is_inst = False
        for pat in app.package_patterns:
            for pkg in installed_names:
                if fnmatch.fnmatch(pkg.lower(), pat.lower()):
                    is_inst = True
                    break
            if is_inst:
                break
        result.append(app.to_dict(installed=is_inst, lang=lang))
    return result


def remove_metro_app_by_id(app_id: str) -> dict[str, Any]:
    """Удаляет указанное Metro-приложение для текущего пользователя."""
    app = next((a for a in METRO_APPS if a.id == app_id), None)
    if not app:
        return {"success": False, "message": f"Приложение '{app_id}' не найдено в каталоге.", "id": app_id}

    patterns_str = ",".join([f"'{p}'" for p in app.package_patterns])
    ps_cmd = f"Get-AppxPackage -Name {patterns_str} | Remove-AppxPackage -ErrorAction SilentlyContinue"

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
            creationflags=NO_WINDOW
        )
        return {
            "success": True,
            "message": f"Приложение «{app.name}» успешно удалено!",
            "id": app.id,
            "installed": False,
        }
    except Exception as e:
        return {"success": False, "message": f"Ошибка удаления {app.name}: {e}", "id": app.id}


def restore_metro_app_by_id(app_id: str) -> dict[str, Any]:
    """Восстанавливает / переустанавливает указанное Metro-приложение."""
    app = next((a for a in METRO_APPS if a.id == app_id), None)
    if not app:
        return {"success": False, "message": f"Приложение '{app_id}' не найдено в каталоге.", "id": app_id}

    # 1. Сначала пробуем зарегистрировать пакет из манифеста в WindowsApps (мгновенно и оффлайн)
    for pat in app.package_patterns:
        clean_pat = pat.strip("*")
        ps_cmd = (
            f"Get-ChildItem -Path 'C:\\Program Files\\WindowsApps' -Filter '*{clean_pat}*' -ErrorAction SilentlyContinue | "
            f"ForEach-Object {{ Add-AppxPackage -DisableDevelopmentMode -Register (Join-Path $_.FullName 'AppXManifest.xml') -ErrorAction SilentlyContinue }}"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, encoding="utf-8", errors="ignore",
                creationflags=NO_WINDOW
            )
        except Exception:
            pass

    # Проверяем, восстановилось ли
    installed_names = _get_installed_package_names()
    for pat in app.package_patterns:
        for pkg in installed_names:
            if fnmatch.fnmatch(pkg.lower(), pat.lower()):
                return {
                    "success": True,
                    "message": f"Приложение «{app.name}» успешно восстановлено!",
                    "id": app.id,
                    "installed": True,
                }

    # 2. Если оффлайн-манифест не сработал — пробуем winget msstore
    if app.store_id:
        try:
            cmd = ["winget", "install", app.store_id, "--source", "msstore", "--accept-package-agreements", "--accept-source-agreements", "--silent"]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NO_WINDOW)
            if res.returncode == 0:
                return {
                    "success": True,
                    "message": f"Приложение «{app.name}» успешно установлено через Microsoft Store!",
                    "id": app.id,
                    "installed": True,
                }
        except Exception:
            pass

        # 3. Fallback: открываем страницу в Microsoft Store
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", f"ms-windows-store://pdp/?ProductId={app.store_id}"], creationflags=NO_WINDOW)
            return {
                "success": True,
                "message": f"Открыта страница «{app.name}» в Microsoft Store для завершения установки.",
                "id": app.id,
                "installed": False,
            }
        except Exception as e:
            return {"success": False, "message": f"Не удалось запустить установку: {e}", "id": app.id}

    return {"success": False, "message": f"Не удалось найти источник для восстановления {app.name}.", "id": app.id}


def remove_batch_metro(app_ids: list[str]) -> list[dict[str, Any]]:
    """Пакетное удаление выбранных Metro-приложений."""
    results = []
    for aid in app_ids:
        res = remove_metro_app_by_id(aid)
        results.append(res)
    return results


def restore_batch_metro(app_ids: list[str]) -> list[dict[str, Any]]:
    """Пакетное восстановление выбранных Metro-приложений."""
    results = []
    for aid in app_ids:
        res = restore_metro_app_by_id(aid)
        results.append(res)
    return results
