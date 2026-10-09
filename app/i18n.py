"""
ZiablWinSetup — Модуль локализации (i18n).
Поддержка русского и английского языков.
Категории и действия оформлены чистым текстом для сочетания со стильными SVG-иконками.
"""

from typing import Literal

Language = Literal["ru", "en"]

STRINGS: dict[Language, dict[str, str]] = {
    "ru": {
        # Заголовок
        "app_title": "ZiablWinSetup — Массовая установка софта",
        "app_subtitle": "Быстрая установка софта после переустановки Windows",
        "winget_found": "winget",
        "winget_not_found": "winget не найден",

        # Категории
        "categories": "Категории",
        "cat_all": "Все",
        "cat_browsers": "Браузеры",
        "cat_media": "Медиа",
        "cat_utilities": "Утилиты",
        "cat_communication": "Мессенджеры и ИИ",
        "cat_development": "Разработка",
        "cat_gaming": "Игры и загрузки",
        "cat_vpn_network": "VPN и сеть",
        "cat_gpu_drivers": "GPU и драйверы",
        "cat_office": "Офис и документы",
        "cat_runtimes": "Библиотеки и Runtimes",

        # Вкладки и твики
        "tab_apps": "Приложения",
        "tab_tweaks": "Твики и фичи",
        "tab_metro": "Metro приложения",
        "tab_startup": "Автозагрузка",
        "metro_title": "Встроенные Metro / UWP приложения Windows",
        "metro_subtitle": "Предустановленный системный софт. Удаляйте ненужные встроенные программы и восстанавливайте их в один клик.",
        "metro_status_installed": "Установлено",
        "metro_status_removed": "Удалено",
        "metro_btn_remove": "Удалить",
        "metro_btn_restore": "Восстановить",
        "metro_btn_remove_selected": "Удалить выбранные",
        "metro_btn_restore_selected": "Восстановить выбранные",
        "metro_count_installed": "Установлено: {installed} из {total}",
        "metro_select_all": "Выбрать все",
        "metro_deselect_all": "Снять все",
        "metro_confirm_remove": "Вы действительно хотите удалить выбранные Metro-приложения ({count} шт.)?",
        "btn_check_updates": "Проверить обновления",
        "checking_updates": "Проверка обновлений...",
        "btn_rescan_installed": "Проверить установленное",
        "rescanning_installed": "Проверка установленных программ...",
        "rescan_completed": "Проверка завершена: найдено {count} установленных программ",
        "select_at_least_one": "Выберите хотя бы одно приложение галочкой!",
        "select_at_least_one_update": "Выберите хотя бы одно приложение галочкой для обновления!",
        "no_updates_in_selection": "Среди выбранных приложений нет доступных обновлений.",
        "cat_updates_available": "Требуют обновления",
        "open_web_1progs": "Скачать с 1progs.ru",
        "open_web": "Перейти на сайт",
        "btn_apply_tweak": "Включить",
        "btn_revert_tweak": "Отключить",
        "btn_clean_action": "Очистить",
        "btn_cleaning": "Очистка...",
        "btn_clean_installers": "Очистить кэш (.exe)",
        "tweak_applied": "Включено",
        "tweak_not_applied": "Отключено",
        "update_available": "Доступно v{version}",
        "btn_upgrade": "Обновить",
        "btn_upgrade_all": "Обновить все",
        "btn_upgrade_selected": "Обновить выбранные",
        "updates_available_banner": "Доступны обновления для {count} приложений",
        "ignored_update_badge": "Не обновлять авто",
        "ignored_update_tooltip": "Исключено из массового обновления («Обновить все»)",

        # Быстрые действия
        "quick_actions": "Быстрые действия",
        "select_recommended": "Рекомендуемые",
        "select_all": "Выбрать все",
        "deselect_all": "Снять все",
        "all_silent": "Все → Тихая",
        "all_interactive": "Все → Интерактивная",

        # Режимы установки
        "mode_interactive": "Интерактивная",
        "mode_silent": "Тихая",

        # Кнопки действий на карточках
        "btn_download": "Скачать",
        "btn_install": "Установить",
        "btn_install_admin": "Установить (Админ)",
        "btn_reinstall": "Переустановить",
        "btn_uninstall": "Удалить",
        "confirm_uninstall": "Вы действительно хотите запустить деинсталляцию {name}?",
        "btn_extract": "Распаковать",
        "btn_launch": "Запустить",
        "btn_open_folder": "Открыть",

        # Основные кнопки панели действий
        "btn_download_selected": "Скачать выбранное",
        "btn_install_all": "Установить все скачанные",
        "btn_cancel": "Отменить",

        # Статусы
        "status_idle": "Ожидание",
        "status_queued": "В очереди",
        "status_downloading": "Скачивается...",
        "status_downloaded": "Скачано",
        "status_installing": "Установка...",
        "status_installed": "Установлено",
        "status_uninstalling": "Удаление...",
        "status_done": "Готово!",
        "status_error": "Ошибка",
        "status_skipped": "Пропущено",
        "status_extracted": "Распаковано",

        # Счетчики и прогресс
        "selected_count": "Выбрано: {count}",
        "downloaded_count": "Скачано: {count}",
        "downloading_progress": "Скачивание: {done}/{total}",
        "installing_progress": "Установка: {done}/{total}",
        "completed": "Завершено",

        # Поиск
        "search_placeholder": "Поиск приложения...",

        # Лог
        "log_no_selection": "Не выбрано ни одного приложения!",
        "log_start_download": "Запуск скачивания {count} приложений...",
        "log_downloaded": "{name} — успешно скачано",
        "log_download_error": "{name} — ошибка скачивания: {error}",
        "log_start_install": "Установка: {name}...",
        "log_installed": "{name} — успешно установлено!",
        "log_install_error": "{name} — ошибка установки: {error}",
        "log_start_uninstall": "Деинсталляция: {name}...",
        "log_uninstalled": "{name} — успешно деинсталлировано!",
        "log_uninstall_error": "{name} — ошибка деинсталляции: {error}",
        "log_extracted": "{name} — распаковано в {path}",
        "log_cancelled": "Операция отменена пользователем",
        "log_cancelled_install": "Установка {name} отменена пользователем.",
        "log_cancelled_upgrade": "Обновление {name} отменено пользователем.",
        "log_all_done": "Все операции успешно завершены!",
        "log_download_done": "Загрузка завершена! Нажмите «Установить» на карточках или «Установить все».",

        # Настройки
        "settings": "Настройки",
        "extract_path_label": "Путь для распаковки ZIP-архивов:",
        "extract_path_desktop": "Рабочий стол",
        "browse": "Обзор...",
        "language": "Язык / Language",
        "no_admin_warning": "Запущено без прав администратора. Некоторые инсталляторы могут запросить подтверждение UAC.",
        "settings_exclusions": "Исключения автообновления",
        "settings_exclusions_desc": "Выбранные приложения не будут обновляться при нажатии «Обновить все». Вы по-прежнему сможете обновить их вручную.",

        # Winget баннер
        "winget_banner_title": "Windows Package Manager (Winget) не установлен в системе",
        "winget_banner_desc": "Он необходим для быстрой фоновой загрузки и автоматического обновления большинства программ.",
        "btn_install_winget_auto": "⚡ Установить Winget автоматически",
        "btn_open_store": "🛍️ Microsoft Store",
        "winget_installing": "Установка Winget...",
        "winget_install_success": "Winget успешно установлен!",

        # Настройки трея и автозапуска
        "settings_autostart_label": "Запускать ZiablWinSetup вместе с Windows",
        "settings_autostart_desc": "Автоматический запуск программы при старте системы (сворачивается в системный трей)",
        "settings_tray_close_label": "Сворачивать в трей при закрытии (крестик)",
        "settings_tray_close_desc": "Окно скрывается в системный трей вместо полного закрытия приложения",

        # Менеджер автозагрузки Windows
        "startup_title": "Менеджер автозагрузки Windows",
        "startup_subtitle": "Программы, системные службы и задачи планировщика, запускающиеся при старте Windows. Отключайте лишнее для ускорения системы.",
        "startup_filter_all": "Все",
        "startup_filter_registry": "Реестр",
        "startup_filter_folders": "Папка автозапуска",
        "startup_filter_tasks": "Планировщик задач",
        "startup_count_summary": "Всего: {total} • Включено: {enabled} • Отключено: {disabled}",
        "startup_status_enabled": "Включено",
        "startup_status_disabled": "Отключено",
        "startup_btn_open_folder": "Открыть папку с файлом",
        "startup_btn_delete": "Удалить",
        "startup_confirm_delete": "Вы действительно хотите удалить запись «{name}» из автозагрузки?",
        "startup_search_placeholder": "Поиск по автозагрузке (название, команда, издатель)...",
        "startup_empty_list": "Записей автозагрузки не найдено.",
        "startup_refresh": "Обновить список",

        # Автопоиск и установка обновлений ZiablWinSetup (Self-Updater)
        "self_update_modal_title": "🎉 Доступно обновление ZiablWinSetup!",
        "self_update_modal_desc": "Вышла новая версия приложения. Рекомендуется обновиться для получения новых функций, каталога и улучшений стабильности.",
        "self_update_current_ver": "Текущая версия",
        "self_update_new_ver": "Новая версия",
        "self_update_btn_install": "⚡ Обновить и перезапустить",
        "self_update_btn_later": "Напомнить позже",
        "self_update_btn_skip": "Пропустить эту версию",
        "self_update_btn_github": "Открыть на GitHub",
        "self_update_downloading": "Скачивание обновления...",
        "self_update_restarting": "Обновление готово! Перезапуск приложения...",
        "self_update_no_updates": "У вас установлена самая последняя версия ZiablWinSetup ({version})",
        "self_update_checking": "Проверка обновлений ZiablWinSetup...",
        "settings_auto_check_app_updates": "Автопоиск обновлений программы при запуске",
        "btn_check_app_update": "Проверить обновление ZiablWinSetup",
    },

    "en": {
        # Header
        "app_title": "ZiablWinSetup — Bulk Software Installer",
        "app_subtitle": "Fast batch application setup after fresh Windows install",
        "winget_found": "winget",
        "winget_not_found": "winget not found",

        # Categories
        "categories": "Categories",
        "cat_all": "All",
        "cat_browsers": "Browsers",
        "cat_media": "Media",
        "cat_utilities": "Utilities",
        "cat_communication": "Messengers & AI",
        "cat_development": "Development",
        "cat_gaming": "Gaming & Downloads",
        "cat_vpn_network": "VPN & Network",
        "cat_gpu_drivers": "GPU & Drivers",
        "cat_office": "Office & Docs",
        "cat_runtimes": "Libraries & Runtimes",

        # Tabs & Tweaks
        "tab_apps": "Apps",
        "tab_tweaks": "Tweaks & Features",
        "tab_metro": "Metro Apps",
        "tab_startup": "Startup",
        "metro_title": "Built-in Windows Metro / UWP Apps",
        "metro_subtitle": "Pre-installed system applications. Uninstall unwanted software and restore apps in a single click.",
        "metro_status_installed": "Installed",
        "metro_status_removed": "Uninstalled",
        "metro_btn_remove": "Uninstall",
        "metro_btn_restore": "Restore",
        "metro_btn_remove_selected": "Uninstall Selected",
        "metro_btn_restore_selected": "Restore Selected",
        "metro_count_installed": "Installed: {installed} of {total}",
        "metro_select_all": "Select All",
        "metro_deselect_all": "Deselect All",
        "metro_confirm_remove": "Are you sure you want to remove the selected Metro apps ({count})?",
        "btn_check_updates": "Check for Updates",
        "checking_updates": "Checking updates...",
        "btn_rescan_installed": "Re-scan Installed",
        "rescanning_installed": "Checking installed apps...",
        "rescan_completed": "Scan complete: found {count} installed apps",
        "select_at_least_one": "Please select at least one application with a checkbox!",
        "select_at_least_one_update": "Please select at least one application to update!",
        "no_updates_in_selection": "No updates available among selected applications.",
        "cat_updates_available": "Updates Available",
        "open_web_1progs": "Download from 1progs.ru",
        "open_web": "Go to website",
        "btn_apply_tweak": "Enable",
        "btn_revert_tweak": "Disable",
        "btn_clean_action": "Clean",
        "btn_cleaning": "Cleaning...",
        "btn_clean_installers": "Clean Installer Cache (.exe)",
        "tweak_applied": "Enabled",
        "tweak_not_applied": "Disabled",
        "update_available": "Update available: v{version}",
        "btn_upgrade": "Upgrade",
        "btn_upgrade_all": "Update All",
        "btn_upgrade_selected": "Update Selected",
        "updates_available_banner": "Updates available for {count} applications",
        "ignored_update_badge": "Skip Auto-Update",
        "ignored_update_tooltip": "Excluded from bulk 'Update All'",

        # Quick actions
        "quick_actions": "Quick Actions",
        "select_recommended": "Recommended",
        "select_all": "Select All",
        "deselect_all": "Deselect All",
        "all_silent": "All → Silent",
        "all_interactive": "All → Interactive",

        # Install modes
        "mode_interactive": "Interactive",
        "mode_silent": "Silent",

        # Card action buttons
        "btn_download": "Download",
        "btn_install": "Install",
        "btn_install_admin": "Install (Admin)",
        "btn_reinstall": "Reinstall",
        "btn_uninstall": "Uninstall",
        "confirm_uninstall": "Are you sure you want to uninstall {name}?",
        "btn_extract": "Extract",
        "btn_launch": "Launch",
        "btn_open_folder": "Open",

        # Main buttons
        "btn_download_selected": "Download Selected",
        "btn_install_all": "Install All Downloaded",
        "btn_cancel": "Cancel",

        # Statuses
        "status_idle": "Idle",
        "status_queued": "Queued",
        "status_downloading": "Downloading...",
        "status_downloaded": "Downloaded",
        "status_installing": "Installing...",
        "status_installed": "Installed",
        "status_uninstalling": "Uninstalling...",
        "status_done": "Done!",
        "status_error": "Error",
        "status_skipped": "Skipped",
        "status_extracted": "Extracted",

        # Counters & Progress
        "selected_count": "Selected: {count}",
        "downloaded_count": "Downloaded: {count}",
        "downloading_progress": "Downloading: {done}/{total}",
        "installing_progress": "Installing: {done}/{total}",
        "completed": "Completed",

        # Search
        "search_placeholder": "Search app...",

        # Log
        "log_no_selection": "No applications selected!",
        "log_start_download": "Downloading {count} apps...",
        "log_downloaded": "{name} — downloaded",
        "log_download_error": "{name} — error: {error}",
        "log_start_install": "Installing: {name}...",
        "log_installed": "{name} — installed!",
        "log_install_error": "{name} — error: {error}",
        "log_start_uninstall": "Uninstalling: {name}...",
        "log_uninstalled": "{name} — uninstalled!",
        "log_uninstall_error": "{name} — error: {error}",
        "log_extracted": "{name} — extracted to {path}",
        "log_cancelled": "Cancelled by user",
        "log_cancelled_install": "Installation of {name} was cancelled by user.",
        "log_cancelled_upgrade": "Upgrade of {name} was cancelled by user.",
        "log_all_done": "All tasks completed!",
        "log_download_done": "Downloads complete! Click 'Install' on cards or 'Install All'.",

        # Settings
        "settings": "Settings",
        "extract_path_label": "ZIP extraction path:",
        "extract_path_desktop": "Desktop",
        "browse": "Browse...",
        "language": "Language",
        "no_admin_warning": "Running without admin rights. Some installers may request UAC.",
        "settings_exclusions": "Auto-Update Exclusions",
        "settings_exclusions_desc": "Selected apps will not be updated when clicking 'Update All'. You can still update them manually.",

        # Winget banner
        "winget_banner_title": "Windows Package Manager (Winget) is not installed",
        "winget_banner_desc": "It is required for fast background downloading and automatic updates for most software.",
        "btn_install_winget_auto": "⚡ Install Winget Automatically",
        "btn_open_store": "🛍️ Microsoft Store",
        "winget_installing": "Installing Winget...",
        "winget_install_success": "Winget installed successfully!",

        # Tray and Autostart settings
        "settings_autostart_label": "Start ZiablWinSetup on Windows startup",
        "settings_autostart_desc": "Application starts automatically with Windows and minimizes to system tray",
        "settings_tray_close_label": "Minimize to tray on close",
        "settings_tray_close_desc": "Clicking the window close button minimizes to system tray instead of exiting",

        # Startup Manager
        "startup_title": "Windows Startup Manager",
        "startup_subtitle": "Applications, background services, and scheduled tasks that launch on Windows boot. Disable unnecessary items to accelerate system startup.",
        "startup_filter_all": "All",
        "startup_filter_registry": "Registry",
        "startup_filter_folders": "Startup Folder",
        "startup_filter_tasks": "Task Scheduler",
        "startup_count_summary": "Total: {total} • Enabled: {enabled} • Disabled: {disabled}",
        "startup_status_enabled": "Enabled",
        "startup_status_disabled": "Disabled",
        "startup_btn_open_folder": "Open file folder",
        "startup_btn_delete": "Delete",
        "startup_confirm_delete": "Are you sure you want to remove '{name}' from Windows startup?",
        "startup_search_placeholder": "Search startup items (app, command, publisher)...",
        "startup_empty_list": "No startup items found.",
        "startup_refresh": "Refresh List",

        # ZiablWinSetup Self-Updater
        "self_update_modal_title": "🎉 ZiablWinSetup Update Available!",
        "self_update_modal_desc": "A new version of ZiablWinSetup is ready. Updating is recommended for new features, catalog additions, and bug fixes.",
        "self_update_current_ver": "Current version",
        "self_update_new_ver": "New version",
        "self_update_btn_install": "⚡ Update & Restart",
        "self_update_btn_later": "Remind Later",
        "self_update_btn_skip": "Skip this version",
        "self_update_btn_github": "View on GitHub",
        "self_update_downloading": "Downloading update...",
        "self_update_restarting": "Update ready! Restarting application...",
        "self_update_no_updates": "You are using the latest version of ZiablWinSetup ({version})",
        "self_update_checking": "Checking for ZiablWinSetup updates...",
        "settings_auto_check_app_updates": "Auto-check for app updates on startup",
        "btn_check_app_update": "Check for ZiablWinSetup Update",
    },
}

# Названия категорий по языкам (без эмодзи)
CATEGORY_NAMES: dict[Language, dict[str, str]] = {
    "ru": {
        "all": "Все",
        "browsers": "Браузеры",
        "media": "Медиа",
        "utilities": "Утилиты",
        "communication": "Связь",
        "development": "Разработка",
        "gpu_drivers": "GPU и драйверы",
        "vpn_network": "VPN и сеть",
        "gaming": "Игры и загрузки",
        "office": "Офис и документы",
        "runtimes": "Библиотеки и Runtimes",
    },
    "en": {
        "all": "All",
        "browsers": "Browsers",
        "media": "Media",
        "utilities": "Utilities",
        "communication": "Communication",
        "development": "Development",
        "gpu_drivers": "GPU & Drivers",
        "vpn_network": "VPN & Network",
        "gaming": "Gaming & Downloads",
        "office": "Office & Docs",
        "runtimes": "Libraries & Runtimes",
    },
}


class I18n:
    """Простой менеджер локализации."""

    def __init__(self, language: Language = "ru"):
        self._lang = language

    @property
    def lang(self) -> Language:
        return self._lang

    @lang.setter
    def lang(self, value: Language):
        self._lang = value

    def set_language(self, language: Language):
        self._lang = language

    def t(self, key: str, **kwargs) -> str:
        """Возвращает локализованную строку по ключу."""
        text = STRINGS.get(self._lang, STRINGS["ru"]).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    def cat_name(self, category_id: str) -> str:
        """Возвращает локализованное название категории."""
        return CATEGORY_NAMES.get(self._lang, CATEGORY_NAMES["ru"]).get(category_id, category_id)

    def toggle(self) -> Language:
        """Переключает язык и возвращает новый."""
        self._lang = "en" if self._lang == "ru" else "ru"
        return self._lang


# Глобальный синглтон
i18n = I18n("ru")
