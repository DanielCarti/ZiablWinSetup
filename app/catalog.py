"""
WinSetup — Каталог поддерживаемых приложений.
Содержит метаданные, категории, winget-идентификаторы, fallback-URL и параметры установки.
Все 58 приложений аккуратно сгруппированы по 9 категориям.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppEntry:
    """Запись приложения в каталоге."""
    id: str                           # Уникальный идентификатор (латиница, дефисы)
    name: str                         # Отображаемое имя
    description: str                  # Краткое описание на русском
    category: str                     # ID категории
    description_en: str = ""          # Краткое описание на английском
    winget_id: str | None = None      # Winget package ID
    direct_url: str | None = None     # Прямой URL для скачивания (fallback)
    github_repo: str | None = None    # GitHub repo "user/repo" для скачивания release
    github_asset_pattern: str | None = None  # Glob-паттерн для выбора нужного asset
    installer_type: str = "exe"       # Тип установщика: exe, msi, zip
    silent_args: list[str] = field(default_factory=list)  # Аргументы для тихой установки
    recommended: bool = False         # Входит ли в пресет "рекомендуемые"
    notes: str = ""                   # Примечания на русском
    notes_en: str = ""                # Примечания на английском
    web_url: str | None = None        # Внешняя ссылка (например, 1progs.ru)

    def get_description(self, lang: str = "ru") -> str:
        if lang == "en" and self.description_en:
            return self.description_en
        return self.description

    def get_notes(self, lang: str = "ru") -> str:
        if lang == "en" and self.notes_en:
            return self.notes_en
        return self.notes


# Категории с emoji-иконками
CATEGORIES: dict[str, str] = {
    "all":           "📂  Все",
    "browsers":      "🌐  Браузеры",
    "media":         "🎬  Медиа",
    "utilities":     "🔧  Утилиты",
    "communication": "💬  Связь",
    "development":   "💻  Разработка",
    "gpu_drivers":   "🖥️  GPU и драйверы",
    "vpn_network":   "🔒  VPN и сеть",
    "gaming":        "🎮  Игры и загрузки",
    "office":        "📑  Офис и документы",
    "runtimes":      "📦  Библиотеки и Runtimes",
}


def _build_catalog() -> list[AppEntry]:
    """Формирует полный каталог приложений, сгруппированный по категориям."""
    return [
        # ========================
        # 1. БРАУЗЕРЫ (5)
        # ========================
        AppEntry(
            id="chrome",
            name="Google Chrome",
            description="Самый популярный веб-браузер в мире от компании Google",
            description_en="World's most popular fast, simple, and secure web browser",
            category="browsers",
            winget_id="Google.Chrome",
            silent_args=["/silent", "/install"],
            recommended=True,
        ),
        AppEntry(
            id="opera-gx",
            name="Opera GX",
            description="Геймерский браузер с контролем процессора, ОЗУ и сетевого трафика",
            description_en="Gaming browser with CPU, RAM, and network limiters",
            category="browsers",
            winget_id="Opera.OperaGX",
            silent_args=["/silent", "/norestart"],
        ),
        AppEntry(
            id="firefox",
            name="Mozilla Firefox",
            description="Быстрый браузер с открытым кодом и упором на защиту приватности",
            description_en="Fast, private, and independent open-source web browser",
            category="browsers",
            winget_id="Mozilla.Firefox",
            direct_url="https://download.mozilla.org/?product=firefox-latest&os=win64&lang=ru",
            silent_args=["-ms"],
            recommended=True,
        ),
        AppEntry(
            id="brave",
            name="Brave Browser",
            description="Быстрый приватный браузер со встроенной блокировкой рекламы и трекеров",
            description_en="Secure and fast Chromium-based browser with built-in ad blocker",
            category="browsers",
            winget_id="Brave.Brave",
            silent_args=["/silent", "/install"],
            recommended=True,
        ),
        AppEntry(
            id="dolphinanty",
            name="Dolphin Anty",
            description="Антидетект-браузер для мультиаккаунтинга с управлением цифровыми отпечатками",
            description_en="Modern anti-detect browser for managing digital browser fingerprints",
            category="browsers",
            winget_id="Dolphin.Anty",
            direct_url="https://dolphin-anty-cdn.com/anty-app/dolphin-anty-win-x64-latest.exe",
            silent_args=["/S"],
        ),

        # ========================
        # 2. МЕДИА И ДИЗАЙН (6)
        # ========================
        AppEntry(
            id="vlc",
            name="VLC Media Player",
            description="Универсальный медиаплеер с поддержкой почти всех форматов аудио и видео",
            description_en="Free, portable, open-source multi-platform media player and streamer",
            category="media",
            winget_id="VideoLAN.VLC",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="klite",
            name="K-Lite Codec Pack Full",
            description="Набор аудио/видео кодеков с удобным и быстрым плеером MPC-HC",
            description_en="Collection of audio/video codecs with lightweight MPC-HC player",
            category="media",
            winget_id="CodecGuide.K-LiteCodecPack.Full",
            silent_args=["/verysilent"],
        ),
        AppEntry(
            id="picasa3",
            name="Picasa 3",
            description="Быстрый классический просмотрщик изображений и фото от Google",
            description_en="Classic, ultra-fast photo organizer and viewer by Google",
            category="media",
            direct_url="https://archive.org/download/picasa-3.9.141.259/picasa39-setup.exe",
            silent_args=["/S"],
        ),
        AppEntry(
            id="obs",
            name="OBS Studio",
            description="Профессиональная программа для видеозаписи экрана и стриминга",
            description_en="Free and open source software for video recording and live streaming",
            category="media",
            winget_id="OBSProject.OBSStudio",
            github_repo="obsproject/obs-studio",
            github_asset_pattern="*x64-Installer.exe",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="photoshop",
            name="Adobe Photoshop",
            description="Профессиональный редактор растровой графики и дизайна (активированная версия на 1progs.ru)",
            description_en="Industry-standard graphics and photo editing software (via 1progs.ru)",
            category="media",
            web_url="https://1progs.ru/adobe-photoshop/",
        ),
        AppEntry(
            id="premiere",
            name="Adobe Premiere Pro",
            description="Профессиональный пакет нелинейного видеомонтажа (активированная версия на 1progs.ru)",
            description_en="Professional video editing and post-production suite (via 1progs.ru)",
            category="media",
            web_url="https://1progs.ru/adobe-premiere/",
        ),

        # ========================
        # 3. УТИЛИТЫ И ДИАГНОСТИКА (15)
        # ========================
        AppEntry(
            id="7zip",
            name="7-Zip",
            description="Бесплатный архиватор с высочайшей степенью сжатия форматов 7z, ZIP, RAR",
            description_en="Free open-source file archiver with high compression ratio",
            category="utilities",
            winget_id="7zip.7zip",
            direct_url="https://www.7-zip.org/a/7z2408-x64.exe",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="winrar",
            name="WinRAR",
            description="Популярный архиватор для открытия и создания архивов RAR и ZIP",
            description_en="Powerful archive manager supporting RAR, ZIP, and other formats",
            category="utilities",
            winget_id="RARLab.WinRAR",
            silent_args=["/s"],
        ),
        AppEntry(
            id="everything",
            name="Everything",
            description="Молниеносный локальный поиск файлов и папок по именам на NTFS-дисках",
            description_en="Ultra-fast filename search engine for Windows NTFS volumes",
            category="utilities",
            winget_id="voidtools.Everything",
            direct_url="https://www.voidtools.com/Everything-1.4.1.1026.x64-Setup.exe",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="total-commander",
            name="Total Commander",
            description="Двухпанельный файловый менеджер со встроенным FTP-клиентом и архиватором",
            description_en="Feature-rich dual-pane orthodox file manager with FTP client",
            category="utilities",
            winget_id="Ghisler.TotalCommander",
            silent_args=["/auto=1"],
        ),
        AppEntry(
            id="eartrumpet",
            name="EarTrumpet",
            description="Продвинутый регулятор громкости для Windows с раздельной настройкой для каждого приложения",
            description_en="Powerful volume control companion with per-app volume sliders",
            category="utilities",
            winget_id="File-New-Project.EarTrumpet",
            recommended=True,
        ),
        AppEntry(
            id="cpuz",
            name="CPU-Z",
            description="Информация о процессоре, материнской плате, оперативной памяти и таймингах",
            description_en="Comprehensive system profiler for CPU, motherboard, and RAM",
            category="utilities",
            winget_id="CPUID.CPU-Z",
            silent_args=["/VERYSILENT"],
            recommended=True,
        ),
        AppEntry(
            id="hwinfo",
            name="HWiNFO",
            description="Глубокая диагностика оборудования, аппаратный мониторинг температур и напряжений",
            description_en="Professional hardware analysis, diagnostic, and real-time monitoring",
            category="utilities",
            winget_id="REALiX.HWiNFO",
            direct_url="https://www.sac.sk/download/utildiag/hwi_852x.exe",
            silent_args=["/VERYSILENT"],
        ),
        AppEntry(
            id="sharex",
            name="ShareX",
            description="Захват экрана, создание скриншотов, запись GIF и мгновенная загрузка в сеть",
            description_en="Screen capture, file sharing, and productivity tool with OCR",
            category="utilities",
            winget_id="ShareX.ShareX",
            github_repo="ShareX/ShareX",
            github_asset_pattern="*setup.exe",
            silent_args=["/VERYSILENT"],
            recommended=True,
        ),
        AppEntry(
            id="powertoys",
            name="Microsoft PowerToys",
            description="Набор инструментов Windows для продуктивности: FancyZones, Text Extractor, ColorPicker",
            description_en="Set of utilities for power users to tune and streamline Windows",
            category="utilities",
            winget_id="Microsoft.PowerToys",
            github_repo="microsoft/PowerToys",
            github_asset_pattern="PowerToysSetup*x64.exe",
            silent_args=["--silent"],
            recommended=True,
        ),
        AppEntry(
            id="crystaldiskinfo",
            name="CrystalDiskInfo",
            description="Мониторинг состояния и температуры жестких дисков и SSD (S.M.A.R.T.)",
            description_en="HDD and SSD health and S.M.A.R.T. monitoring utility",
            category="utilities",
            winget_id="CrystalDewWorld.CrystalDiskInfo",
            silent_args=["/VERYSILENT", "/NORESTART"],
            recommended=True,
        ),
        AppEntry(
            id="crystaldiskmark",
            name="CrystalDiskMark",
            description="Бенчмарк для измерения скорости чтения и записи накопителей",
            description_en="Storage benchmark utility for measuring read/write speeds",
            category="utilities",
            winget_id="CrystalDewWorld.CrystalDiskMark",
            silent_args=["/VERYSILENT", "/NORESTART"],
            recommended=True,
        ),
        AppEntry(
            id="occt",
            name="OCCT Personal",
            description="Комплексный стресс-тест стабильности процессора, памяти и блока питания",
            description_en="All-in-one CPU, memory, and power supply stability stress test",
            category="utilities",
            winget_id="OCBase.OCCT.Personal",
            silent_args=["/S"],
        ),
        AppEntry(
            id="uninstalltool",
            name="Uninstall Tool",
            description="Чистая деинсталляция программ с глубоким удалением остатков и следов в реестре",
            description_en="Powerful uninstaller removing residual files and registry keys",
            category="utilities",
            winget_id="CrystalIDEASoftware.UninstallTool",
            silent_args=["/VERYSILENT"],
            recommended=True,
        ),
        AppEntry(
            id="unlocker",
            name="IObit Unlocker",
            description="Быстрая разблокировка и удаление файлов, занятых другими системными процессами",
            description_en="Easily unlocks and deletes files locked by system processes",
            category="utilities",
            winget_id="IObit.Unlocker",
            direct_url="https://download.iobit.com/unlocker-setup.exe",
            silent_args=["/VERYSILENT", "/SUPPRESSMSGBOXES"],
        ),
        AppEntry(
            id="unchecker",
            name="Unchecky",
            description="Автоматическое снятие галочек с рекламных предложений и тулбаров при установке софта",
            description_en="Automatically unchecks unwanted software bundles during installations",
            category="utilities",
            winget_id="ReasonCompanySoftware.Unchecker",
            direct_url="https://unchecker.com/dl/unchecker_setup.exe",
            silent_args=["/VERYSILENT"],
            recommended=True,
        ),
        AppEntry(
            id="hitmanpro",
            name="HitmanPro",
            description="Быстрый облачный антивирусный сканер второго мнения (активированная версия на 1progs.ru)",
            description_en="Fast second-opinion cloud-based malware and rootkit scanner (1progs.ru)",
            category="utilities",
            web_url="https://1progs.ru/hitmanpro/",
            direct_url="https://dl.surfright.nl/HitmanPro_x64.exe",
            silent_args=["/quiet"],
            recommended=True,
        ),

        # ========================
        # 4. СВЯЗЬ И МЕССЕНДЖЕРЫ (5)
        # ========================
        AppEntry(
            id="telegram",
            name="Telegram Desktop",
            description="Быстрый и безопасный мессенджер с поддержкой каналов и групп",
            description_en="Fast and secure desktop messaging app with cloud sync",
            category="communication",
            winget_id="Telegram.TelegramDesktop",
            direct_url="https://telegram.org/dl/desktop/win64",
            silent_args=["/VERYSILENT"],
            recommended=True,
        ),
        AppEntry(
            id="discord",
            name="Discord",
            description="Голосовой, видео- и текстовый чат для геймеров и сообществ",
            description_en="All-in-one voice, video, and text communication platform",
            category="communication",
            winget_id="Discord.Discord",
            recommended=True,
        ),
        AppEntry(
            id="claude",
            name="Claude Desktop",
            description="Официальное десктопное приложение ИИ-ассистента Claude от Anthropic",
            description_en="Official desktop client for Anthropic's Claude AI assistant",
            category="communication",
            winget_id="Anthropic.Claude",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="chatgpt",
            name="ChatGPT Desktop",
            description="Официальный клиент ChatGPT для Windows с горячими клавишами и голосовым вводом",
            description_en="Official OpenAI ChatGPT Windows client with global hotkey support",
            category="communication",
            winget_id="9PLM9XGG6VKS",
            recommended=True,
        ),
        AppEntry(
            id="todoist",
            name="Todoist",
            description="Популярный планировщик задач, списков дел и проектов",
            description_en="Organize your work and personal life with task manager",
            category="communication",
            winget_id="Doist.Todoist",
        ),

        # ========================
        # 5. РАЗРАБОТКА И ИИ (9)
        # ========================
        AppEntry(
            id="vscode",
            name="Visual Studio Code",
            description="Мощный легковесный редактор кода от Microsoft с огромной экосистемой расширений",
            description_en="Streamlined lightweight code editor with vast extensions library",
            category="development",
            winget_id="Microsoft.VisualStudioCode",
            silent_args=["/VERYSILENT", "/NORESTART", "/MERGETASKS=!runcode,addcontextmenufiles,addcontextmenufolders"],
            recommended=True,
        ),
        AppEntry(
            id="pycharm",
            name="PyCharm Community",
            description="Интеллектуальная среда разработки Python от JetBrains с умной подсветкой и отладчиком",
            description_en="Intelligent Python IDE by JetBrains with code analysis",
            category="development",
            winget_id="JetBrains.PyCharm.Community",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="sublimetext",
            name="Sublime Text",
            description="Сверхбыстрый и отзывчивый редактор кода и заметок",
            description_en="Sophisticated text editor for code, markup, and prose",
            category="development",
            winget_id="SublimeHQ.SublimeText.4",
            silent_args=["/VERYSILENT"],
        ),
        AppEntry(
            id="notepadpp",
            name="Notepad++",
            description="Быстрый текстовый редактор с подсветкой синтаксиса и вкладками",
            description_en="Free and fast source code and text editor replacing Notepad",
            category="development",
            winget_id="Notepad++.Notepad++",
            github_repo="notepad-plus-plus/notepad-plus-plus",
            github_asset_pattern="*Installer.x64.exe",
            direct_url="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.8/npp.8.9.8.Installer.x64.exe",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="git",
            name="Git",
            description="Распределённая система контроля версий для отслеживания изменений в коде",
            description_en="Fast, scalable, distributed revision control system",
            category="development",
            winget_id="Git.Git",
            github_repo="git-for-windows/git",
            github_asset_pattern="*64-bit.exe",
            silent_args=["/VERYSILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            recommended=True,
        ),
        AppEntry(
            id="python",
            name="Python 3",
            description="Современный язык программирования общего назначения для скриптов и разработки",
            description_en="High-level scripting and programming language with pip and venv",
            category="development",
            winget_id="Python.Python.3.12",
            silent_args=["/quiet", "PrependPath=1", "Include_pip=1"],
            recommended=True,
        ),
        AppEntry(
            id="java",
            name="Java (Eclipse Temurin JDK 21)",
            description="Среда исполнения и компиляции Java от сообщества Adoptium (LTS-релиз)",
            description_en="High-performance, cross-platform enterprise Java runtime (LTS)",
            category="development",
            winget_id="EclipseAdoptium.Temurin.21.JDK",
            installer_type="msi",
            silent_args=["/quiet", "/norestart"],
        ),
        AppEntry(
            id="codex",
            name="OpenAI Codex CLI",
            description="Консольный инструмент и агент кодинга на базе моделей OpenAI",
            description_en="Command-line AI coding assistant and agent",
            category="development",
            winget_id="jcv8000.Codex",
        ),
        AppEntry(
            id="opencode",
            name="OpenCode AI",
            description="Открытая платформа и среда разработки с поддержкой ИИ",
            description_en="Open-source AI-assisted coding environment",
            category="development",
            winget_id="SST.OpenCodeDesktop",
            github_repo="anomalyco/opencode",
            direct_url="https://github.com/anomalyco/opencode/releases/latest/download/opencode-desktop-win-x64.exe",
            installer_type="exe",
            silent_args=["/S"],
        ),

        # ========================
        # 6. GPU И ДРАЙВЕРЫ (5)
        # ========================
        AppEntry(
            id="nvidia-app",
            name="NVIDIA App (GeForce Experience)",
            description="Центр управления графикой, обновление драйверов и оптимизация игр NVIDIA",
            description_en="Official client for NVIDIA GPU driver updates and game tuning",
            category="gpu_drivers",
            winget_id="XP8CLZL93F5Z4P",
            direct_url="https://uk.download.nvidia.com/nvapp/client/11.0.9.251/NVIDIA_app_v11.0.9.251.exe",
            notes="Для видеокарт NVIDIA GeForce",
            notes_en="For NVIDIA GeForce graphics cards",
        ),
        AppEntry(
            id="amd-software",
            name="AMD Software: Adrenalin Edition",
            description="Панель управления и драйверы для видеокарт AMD Radeon",
            description_en="Drivers and software control panel for AMD Radeon GPUs",
            category="gpu_drivers",
            winget_id="AdvancedMicroDevices.Adrenalin",
            direct_url="https://drivers.amd.com/drivers/installer/26.10/whql/amd-software-adrenalin-edition-26.8.1-minimalsetup-260818_web.exe",
            notes="Для видеокарт AMD Radeon",
            notes_en="For AMD Radeon graphics cards",
        ),
        AppEntry(
            id="gpuz",
            name="TechPowerUp GPU-Z",
            description="Подробные характеристики видеокарты, частот, видеопамяти и датчиков",
            description_en="Lightweight utility providing detailed information on video cards and GPU",
            category="gpu_drivers",
            winget_id="TechPowerUp.GPU-Z",
            direct_url="https://us1-dl.techpowerup.com/files/GPU-Z.2.71.0.exe",
            installer_type="portable",
            silent_args=["-installSilent"],
            recommended=True,
            notes="Портативная утилита, не требует установки",
            notes_en="Portable standalone utility, runs without installation",
        ),
        AppEntry(
            id="furmark",
            name="Geeks3D FurMark 2",
            description="Интенсивный стресс-тест видеокарты и бенчмарк стабильности («бублик»)",
            description_en="Intensive GPU stress test and stability benchmark",
            category="gpu_drivers",
            winget_id="Geeks3D.FurMark.2",
            direct_url="https://geeks3d.com/downloads/2024p/FurMark_2.4.0.0_setup.exe",
            silent_args=["/VERYSILENT", "/NORESTART"],
        ),
        AppEntry(
            id="driverbooster",
            name="IObit Driver Booster",
            description="Автоматическое сканирование и обновление устаревших драйверов Windows (активированная версия на 1progs.ru)",
            description_en="Automatic scanning and updating for outdated device drivers (Pro via 1progs.ru)",
            category="gpu_drivers",
            web_url="https://1progs.ru/iobit-driver-booster-pro/",
            winget_id="IObit.DriverBooster",
            silent_args=["/VERYSILENT"],
        ),
        AppEntry(
            id="nvidiabroadcast",
            name="NVIDIA Broadcast",
            description="Интеллектуальное шумоподавление микрофона и эффекты веб-камеры на базе ИИ для видеокарт RTX",
            description_en="AI-powered microphone noise reduction and webcam effects for RTX GPUs",
            category="gpu_drivers",
            winget_id="Nvidia.Broadcast",
            web_url="https://www.nvidia.com/ru-ru/geforce/broadcasting/broadcast-app/",
            direct_url="https://international.download.nvidia.com/Windows/broadcast/1.4.0.29/NVIDIA_Broadcast_v1.4.0.29.exe",
            silent_args=["-s"],
        ),

        # ========================
        # 7. VPN И СЕТЬ (6)
        # ========================
        AppEntry(
            id="amnezia-vpn",
            name="AmneziaVPN",
            description="Бесплатный VPN-клиент с поддержкой устойчивых протоколов",
            description_en="Free open-source VPN client supporting modern protocols",
            category="vpn_network",
            winget_id="AmneziaVPN.AmneziaVPN",
            github_repo="amnezia-vpn/amnezia-client",
            github_asset_pattern="*windows*x64*.exe",
            installer_type="exe",
        ),
        AppEntry(
            id="zapret",
            name="Zapret (Discord/YouTube разблокировка)",
            description="Обход замедлений и блокировок Discord и YouTube без VPN",
            description_en="Bypass throttling and blocking of Discord & YouTube without VPN",
            category="vpn_network",
            winget_id=None,
            github_repo="Flowseal/zapret-discord-youtube",
            github_asset_pattern="*.zip",
            installer_type="zip",
            notes="Распакуется на Рабочий стол с готовым ярлыком для запуска",
            notes_en="Extracts to Desktop with an auto-created launch shortcut",
            recommended=True,
        ),
        AppEntry(
            id="yogadns",
            name="YogaDNS",
            description="Продвинутый системный DNS-клиент с поддержкой DoH, DoT и правил маршрутизации",
            description_en="Advanced DNS client supporting DNS-over-HTTPS, DoT, and rule routing",
            category="vpn_network",
            winget_id="Initex.YogaDNS",
            silent_args=["/VERYSILENT"],
        ),
        AppEntry(
            id="tgwsproxy",
            name="Tg-WS Proxy (Flowseal)",
            description="Локальный MTProto WebSocket прокси для обхода блокировок и замедления Telegram",
            description_en="Local MTProto WebSocket bridge proxy to accelerate Telegram connections",
            category="vpn_network",
            github_repo="Flowseal/tg-ws-proxy",
            github_asset_pattern="*windows.exe",
            installer_type="portable",
            recommended=True,
            notes="Портативная консольная утилита",
            notes_en="Portable standalone CLI utility",
        ),
        AppEntry(
            id="operaproxy",
            name="Opera Proxy (Alexey71)",
            description="Автономный прокси-клиент для подключения к серверам Opera VPN без браузера",
            description_en="Standalone proxy client for connecting to Opera VPN servers",
            category="vpn_network",
            github_repo="Alexey71/opera-proxy",
            github_asset_pattern="*windows-amd64.exe",
            installer_type="portable",
            notes="Портативная консольная утилита",
            notes_en="Portable standalone CLI utility",
        ),
        AppEntry(
            id="anydesk",
            name="AnyDesk",
            description="Быстрое и защищённое подключение к удалённому рабочему столу",
            description_en="Fast and lightweight remote desktop connection software",
            category="vpn_network",
            winget_id="AnyDesk.AnyDesk",
            direct_url="https://download.anydesk.com/AnyDesk.exe",
            silent_args=["--install", "C:\\Program Files (x86)\\AnyDesk", "--silent"],
        ),

        # ========================
        # 8. ИГРЫ И ЗАГРУЗКИ (4)
        # ========================
        AppEntry(
            id="steam",
            name="Steam",
            description="Крупнейшая платформа цифровой дистрибуции игр от Valve",
            description_en="Ultimate online game store and community platform by Valve",
            category="gaming",
            winget_id="Valve.Steam",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="qbittorrent",
            name="qBittorrent",
            description="Бесплатный торрент-клиент с чистым интерфейсом без рекламы",
            description_en="Free and reliable open-source torrent client without ads",
            category="gaming",
            winget_id="qBittorrent.qBittorrent",
            github_repo="qbittorrent/qBittorrent",
            github_asset_pattern="*x64_setup.exe",
            direct_url="https://sourceforge.net/projects/qbittorrent/files/qbittorrent-win32/qbittorrent-5.0.4/qbittorrent_5.0.4_x64_setup.exe/download",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="bittorrent",
            name="BitTorrent",
            description="Классический торрент-клиент для скачивания больших файлов",
            description_en="Classic peer-to-peer file sharing and torrent client",
            category="gaming",
            winget_id="BitTorrent.BitTorrent",
            direct_url="https://download-new.utorrent.com/endpoint/bittorrent/os/windows/track/stable/",
            silent_args=["/S"],
        ),
        AppEntry(
            id="dropbox",
            name="Dropbox",
            description="Надёжное облачное хранилище и синхронизация документов",
            description_en="Reliable cloud storage, file backup and syncing service",
            category="gaming",
            winget_id="Dropbox.Dropbox",
            silent_args=["/S"],
        ),
        AppEntry(
            id="roblox",
            name="Roblox",
            description="Популярная онлайн-платформа игр и создания виртуальных миров",
            description_en="Popular online gaming platform and universe creation system",
            category="gaming",
            winget_id="Roblox.Roblox",
            web_url="https://www.roblox.com/download/client",
            direct_url="https://setup.rbxcdn.com/RobloxPlayerInstaller.exe",
            silent_args=["/silent"],
            recommended=True,
        ),
        AppEntry(
            id="tlauncher",
            name="TLauncher (Minecraft)",
            description="Один из самых популярных лаунчеров Minecraft с модами, скинами и версиями",
            description_en="Popular Minecraft launcher with modpack, skin, and version support",
            category="gaming",
            winget_id="TLauncher.TLauncher",
            web_url="https://tlauncher.org/",
            direct_url="https://tlauncher.org/installer",
            silent_args=["/VERYSILENT", "/NORESTART"],
            recommended=True,
        ),

        # ========================
        # 9. ОФИС И ДОКУМЕНТЫ (3)
        # ========================
        AppEntry(
            id="obsidian",
            name="Obsidian",
            description="База знаний и заметочник на основе локальных файлов Markdown",
            description_en="Extensible note-taking and personal knowledge base on Markdown",
            category="office",
            winget_id="Obsidian.Obsidian",
            github_repo="obsidianmd/obsidian-releases",
            github_asset_pattern="Obsidian*x64.exe",
            silent_args=["/S"],
            recommended=True,
        ),
        AppEntry(
            id="libreoffice",
            name="LibreOffice",
            description="Полноценный бесплатный офисный пакет для документов и таблиц",
            description_en="Free and powerful open source office suite",
            category="office",
            winget_id="TheDocumentFoundation.LibreOffice",
            silent_args=["/qn"],
        ),
        AppEntry(
            id="openoffice",
            name="Apache OpenOffice",
            description="Классический офисный пакет с открытым исходным кодом",
            description_en="Classic open-source productivity suite",
            category="office",
            winget_id="Apache.OpenOffice",
            silent_args=["/qn"],
        ),

        # ========================
        # 10. БИБЛИОТЕКИ И RUNTIMES (9)
        # ========================
        AppEntry(
            id="directx",
            name="DirectX End-User Runtimes (June 2010)",
            description="Полный набор библиотек DirectX 9.0c / 10 / 11 для совместимости со всеми играми",
            description_en="Legacy DirectX 9.0c / 10 / 11 runtime libraries for PC games compatibility",
            category="runtimes",
            winget_id="Microsoft.DirectX",
            web_url="https://www.microsoft.com/download/details.aspx?id=35",
            direct_url="https://download.microsoft.com/download/1/7/1/1718CCC4-6316-448E-938E-11910E20D5F4/directx_Jun2010_redist.exe",
            silent_args=["/Q"],
            recommended=True,
        ),
        AppEntry(
            id="vcredist_aio",
            name="Visual C++ Runtimes All-in-One",
            description="Универсальный полный пакет всех версий Microsoft Visual C++ (2005-2022 x86/x64)",
            description_en="Complete all-in-one package of Microsoft Visual C++ runtimes (2005-2022 x86/x64)",
            category="runtimes",
            winget_id="abbodi1406.vcredist",
            web_url="https://github.com/abbodi1406/vcredist",
            direct_url="https://github.com/abbodi1406/vcredist/releases/latest/download/Visual-C-Runtimes-All-in-One-Setup.zip",
            silent_args=["/y"],
            recommended=True,
        ),
        AppEntry(
            id="vcredist_2015_2022_x64",
            name="Visual C++ 2015-2022 Redistributable (x64)",
            description="Официальные распространяемые компоненты Microsoft Visual C++ 2015-2022 для 64-бит",
            description_en="Official Microsoft Visual C++ 2015-2022 redistributable for 64-bit Windows",
            category="runtimes",
            winget_id="Microsoft.VCRedist.2015+.x64",
            direct_url="https://aka.ms/vs/17/release/vc_redist.x64.exe",
            silent_args=["/quiet", "/norestart"],
            recommended=True,
        ),
        AppEntry(
            id="vcredist_2015_2022_x86",
            name="Visual C++ 2015-2022 Redistributable (x86)",
            description="Официальные компоненты Microsoft Visual C++ 2015-2022 для 32-бит программ и игр",
            description_en="Official Microsoft Visual C++ 2015-2022 redistributable for 32-bit apps and games",
            category="runtimes",
            winget_id="Microsoft.VCRedist.2015+.x86",
            direct_url="https://aka.ms/vs/17/release/vc_redist.x86.exe",
            silent_args=["/quiet", "/norestart"],
        ),
        AppEntry(
            id="dotnet_desktop_8",
            name=".NET Desktop Runtime 8.0 (LTS x64)",
            description="Среда выполнения Microsoft .NET 8.0 LTS для современных настольных приложений Windows",
            description_en="Microsoft .NET 8.0 LTS Desktop Runtime for modern Windows applications",
            category="runtimes",
            winget_id="Microsoft.DotNet.DesktopRuntime.8",
            direct_url="https://aka.ms/dotnet/8.0/windowsdesktop-runtime-win-x64.exe",
            silent_args=["/install", "/quiet", "/norestart"],
            recommended=True,
        ),
        AppEntry(
            id="dotnet_desktop_9",
            name=".NET Desktop Runtime 9.0 (x64)",
            description="Новейшая среда выполнения Microsoft .NET 9.0 для самых современных программ",
            description_en="Latest Microsoft .NET 9.0 Desktop Runtime for Windows applications",
            category="runtimes",
            winget_id="Microsoft.DotNet.DesktopRuntime.9",
            direct_url="https://aka.ms/dotnet/9.0/windowsdesktop-runtime-win-x64.exe",
            silent_args=["/install", "/quiet", "/norestart"],
        ),
        AppEntry(
            id="dotnet_desktop_6",
            name=".NET Desktop Runtime 6.0 (x64)",
            description="Среда выполнения Microsoft .NET 6.0, требуемая многими популярными утилитами",
            description_en="Microsoft .NET 6.0 Desktop Runtime required by many existing applications",
            category="runtimes",
            winget_id="Microsoft.DotNet.DesktopRuntime.6",
            direct_url="https://aka.ms/dotnet/6.0/windowsdesktop-runtime-win-x64.exe",
            silent_args=["/install", "/quiet", "/norestart"],
        ),
        AppEntry(
            id="dotnet_framework_481",
            name=".NET Framework 4.8.1 Runtime",
            description="Классический рантайм .NET Framework 4.8.1 для широкой совместимости программ",
            description_en="Classic .NET Framework 4.8.1 runtime for Windows software compatibility",
            category="runtimes",
            winget_id="Microsoft.DotNet.Framework.Runtime.4.8.1",
            direct_url="https://go.microsoft.com/fwlink/?linkid=2203305",
            silent_args=["/q", "/norestart"],
        ),
        AppEntry(
            id="dotnet_framework_35",
            name=".NET Framework 3.5 (включает 2.0 / 3.0)",
            description="Пакет поддержки .NET Framework 3.5 / 2.0 для старых игр и классических утилит",
            description_en="Legacy .NET Framework 3.5 / 2.0 package for classic software and older games",
            category="runtimes",
            winget_id="Microsoft.DotNet.Framework.DeveloperPack_3.5",
            silent_args=["/q", "/norestart"],
        ),
    ]


# Глобальный кэш каталога
_catalog_cache: list[AppEntry] | None = None


def get_catalog() -> list[AppEntry]:
    """Возвращает полный каталог приложений."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = _build_catalog()
    return _catalog_cache


def get_apps_by_category(category: str) -> list[AppEntry]:
    """Возвращает приложения из указанной категории."""
    if category == "all":
        return get_catalog()
    return [app for app in get_catalog() if app.category == category]


def get_recommended() -> list[AppEntry]:
    """Возвращает рекомендованные приложения."""
    return [app for app in get_catalog() if app.recommended]


def get_app_by_id(app_id: str) -> AppEntry | None:
    """Находит приложение по ID."""
    for app in get_catalog():
        if app.id == app_id:
            return app
    return None
