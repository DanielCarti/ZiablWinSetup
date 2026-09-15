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
        "cat_communication": "Связь",
        "cat_development": "Разработка",
        "cat_gaming": "Игры и загрузки",
        "cat_vpn_network": "VPN и сеть",
        "cat_gpu_drivers": "GPU и драйверы",
        "cat_office": "Офис и документы",

        # Вкладки и твики
        "tab_apps": "Приложения",
        "tab_tweaks": "Твики и фичи",
        "tab_metro": "Metro приложения",
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
        "btn_apply_tweak": "Включить",
        "btn_revert_tweak": "Отключить",
        "btn_clean_action": "Очистить",
        "btn_cleaning": "Очистка...",
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
        "cat_communication": "Communication",
        "cat_development": "Development",
        "cat_gaming": "Gaming & Downloads",
        "cat_vpn_network": "VPN & Network",
        "cat_gpu_drivers": "GPU & Drivers",
        "cat_office": "Office & Docs",

        # Tabs & Tweaks
        "tab_apps": "Apps",
        "tab_tweaks": "Tweaks & Features",
        "tab_metro": "Metro Apps",
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
        "btn_apply_tweak": "Enable",
        "btn_revert_tweak": "Disable",
        "btn_clean_action": "Clean",
        "btn_cleaning": "Cleaning...",
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
