"""
ZiablWinSetup — GUI на CustomTkinter.
Современный интерфейс в стиле Windows 11 Fluent Dark (Slate),
адаптивное масштабирование, перетаскиваемый сплиттер, плавная прокрутка и полная двуязычность.
"""

import logging
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from app.catalog import AppEntry, get_apps_by_category, get_catalog, get_recommended
from app.downloader import DownloadResult, Downloader
from app.i18n import I18n, i18n
from app.installer import InstallResult, Installer, get_desktop_path
from app.utils import check_winget, ensure_download_dir, get_winget_version

logger = logging.getLogger("ZiablWinSetup")

# ===================================================
# Цветовая палитра: Windows 11 Fluent Slate Dark
# Мягкая, спокойная для глаз, без едких синих и фиолетовых тонов
# ===================================================
COLORS = {
    # Фоны
    "bg_window": "#1e1e1e",        # Глубокий матовый тёмно-серый
    "bg_header": "#252525",        # Шапка окна
    "bg_sidebar": "#222222",       # Панель навигации (сайдбар)
    "bg_card": "#2b2b2b",          # Поверхность карточки
    "bg_card_hover": "#333333",    # При наведении
    "border": "#3c3c3c",           # Мягкая граница карточек
    "border_light": "#4a4a4a",     # Границы полей и скроллбара
    "splitter": "#303030",         # Разделитель панелей
    "splitter_hover": "#0078d4",   # Акцент при наведении/перетаскивании

    # Текст
    "text_primary": "#f3f3f3",     # Основной читаемый белый
    "text_secondary": "#a5a5a5",   # Мягкий серый для описаний
    "text_dim": "#757575",         # Приглушённые подсказки и лейблы

    # Акценты и кнопки (Windows 11 Blue & Green)
    "accent": "#0078d4",           # Фирменный синий Windows Fluent
    "accent_hover": "#1084d9",
    "btn_primary": "#0078d4",
    "btn_primary_hover": "#1084d9",
    "btn_success": "#107c41",      # Спокойный хвойный зелёный
    "btn_success_hover": "#16914c",
    "btn_extract": "#c16800",      # Тёплый янтарь для распаковки ZIP
    "btn_extract_hover": "#d67400",
    "btn_secondary": "#363636",
    "btn_secondary_hover": "#424242",
    "btn_danger": "#c42b1c",       # Мягкий красный
    "btn_danger_hover": "#d13438",
    "warning": "#d89614",          # Спокойный жёлто-янтарный
    "error": "#d13438",            # Спокойный красный
    "success": "#107c41",          # Зелёный
    "progress_bg": "#333333",
    "progress_fg": "#0078d4",
}

# Статусы приложений
STATUS_IDLE = "idle"
STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_DOWNLOADED = "downloaded"
STATUS_INSTALLING = "installing"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
STATUS_EXTRACTED = "extracted"


def _status_display(status: str) -> tuple[str, str, str]:
    """Возвращает (emoji, текст_ключ_i18n, цвет) для статуса."""
    mapping = {
        STATUS_IDLE: ("⏸️", "status_idle", COLORS["text_dim"]),
        STATUS_QUEUED: ("⏳", "status_queued", COLORS["warning"]),
        STATUS_DOWNLOADING: ("📥", "status_downloading", COLORS["accent"]),
        STATUS_DOWNLOADED: ("📦", "status_downloaded", COLORS["btn_primary"]),
        STATUS_INSTALLING: ("⚙️", "status_installing", COLORS["warning"]),
        STATUS_DONE: ("✅", "status_done", COLORS["btn_success"]),
        STATUS_ERROR: ("❌", "status_error", COLORS["error"]),
        STATUS_SKIPPED: ("⏭️", "status_skipped", COLORS["text_dim"]),
        STATUS_EXTRACTED: ("📂", "status_extracted", COLORS["btn_extract"]),
    }
    return mapping.get(status, ("❓", status, COLORS["text_dim"]))


class AppCard(ctk.CTkFrame):
    """Карточка приложения с чекбоксом, описанием, режимом установки и кнопкой действия."""

    def __init__(
        self,
        master,
        app: AppEntry,
        on_download_click=None,
        on_install_click=None,
        on_extract_click=None,
        on_select_change=None,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=6,
            fg_color=COLORS["bg_card"],
            border_width=0,
            height=68,
            **kwargs,
        )
        self.app = app
        self.status = STATUS_IDLE
        self.download_result: DownloadResult | None = None
        self._on_download_click = on_download_click
        self._on_install_click = on_install_click
        self._on_extract_click = on_extract_click
        self._on_select_change = on_select_change

        self.grid_columnconfigure(1, weight=1)

        # Колонка 0: Чекбокс
        self.selected_var = ctk.BooleanVar(value=app.recommended)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.selected_var,
            width=24,
            checkbox_width=22,
            checkbox_height=22,
            corner_radius=5,
            border_width=2,
            border_color=COLORS["border_light"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=10, sticky="w")

        # Колонка 1: Название и описание
        self.name_label = ctk.CTkLabel(
            self,
            text=app.name,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.name_label.grid(row=0, column=1, padx=6, pady=(10, 2), sticky="w")

        desc = app.get_description(i18n.lang)
        notes = app.get_notes(i18n.lang)
        if notes:
            desc += f"  ⓘ {notes}"

        self.desc_label = ctk.CTkLabel(
            self,
            text=desc,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.desc_label.grid(row=1, column=1, padx=6, pady=(0, 10), sticky="w")

        # Колонка 2: Режим установки
        self.mode_var = ctk.StringVar(value=i18n.t("mode_interactive"))
        self.mode_menu = ctk.CTkOptionMenu(
            self,
            variable=self.mode_var,
            values=[i18n.t("mode_interactive"), i18n.t("mode_silent")],
            width=145,
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["btn_secondary"],
            button_color=COLORS["btn_secondary"],
            button_hover_color=COLORS["btn_secondary_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["btn_secondary"],
            dropdown_text_color=COLORS["text_primary"],
            text_color=COLORS["text_primary"],
        )
        self.mode_menu.grid(row=0, column=2, padx=(8, 8), pady=(10, 2), sticky="e")

        # Колонка 3: Кнопка действия (Скачать / Установить / Распаковать)
        self.action_button = ctk.CTkButton(
            self,
            text=i18n.t("btn_download"),
            width=140,
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
            text_color="white",
            command=self._on_action_click,
            state="normal",
        )
        self.action_button.grid(row=0, column=3, rowspan=2, padx=(8, 14), pady=10, sticky="e")

        # Прогресс-бар (скрыт по умолчанию)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=145,
            height=6,
            corner_radius=3,
            fg_color=COLORS["progress_bg"],
            progress_color=COLORS["accent"],
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=2, padx=8, pady=(0, 10), sticky="e")
        self.progress_bar.grid_remove()

        # Статус-лейбл
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"],
            anchor="e",
        )
        self.status_label.grid(row=1, column=2, padx=8, pady=(0, 10), sticky="e")

    @property
    def is_selected(self) -> bool:
        return self.selected_var.get()

    @property
    def is_silent(self) -> bool:
        return self.mode_var.get() in (i18n.t("mode_silent"), "Тихая", "Silent")

    def _on_checkbox_toggle(self):
        """Чекбокс выбора для массовой установки."""
        if self._on_select_change:
            self._on_select_change()

    def _on_action_click(self):
        """Обработчик нажатия кнопки действия на карточке."""
        if self.status == STATUS_IDLE:
            if self._on_download_click:
                self._on_download_click(self)
        elif self.status == STATUS_ERROR:
            has_installer = bool(self.download_result and self.download_result.installer_path and self.download_result.installer_path.exists())
            if has_installer:
                if self._on_install_click:
                    self._on_install_click(self, as_admin=True)
            else:
                if self._on_download_click:
                    self._on_download_click(self)
        elif self.status == STATUS_DOWNLOADED:
            if self.app.installer_type == "zip":
                if self._on_extract_click:
                    self._on_extract_click(self)
            else:
                if self._on_install_click:
                    self._on_install_click(self, as_admin=False)

    def set_status(self, status: str, detail: str = ""):
        """Обновляет статус и кнопку действия."""
        self.status = status
        emoji, i18n_key, color = _status_display(status)
        label_text = i18n.t(i18n_key) if not detail else detail
        self.status_label.configure(text=f"{emoji} {label_text}", text_color=color)

        if status == STATUS_DOWNLOADING:
            self.progress_bar.grid()
            self.status_label.grid_remove()
            self.action_button.configure(state="disabled", text="📥 ...", fg_color=COLORS["btn_primary"])
        elif status == STATUS_DOWNLOADED:
            self.progress_bar.grid_remove()
            self.status_label.grid()
            if self.app.installer_type == "zip":
                self.action_button.configure(
                    state="normal",
                    text=i18n.t("btn_extract"),
                    fg_color=COLORS["btn_extract"],
                    hover_color=COLORS["btn_extract_hover"],
                )
            else:
                self.action_button.configure(
                    state="normal",
                    text=i18n.t("btn_install"),
                    fg_color=COLORS["btn_success"],
                    hover_color=COLORS["btn_success_hover"],
                )
        elif status == STATUS_INSTALLING:
            self.action_button.configure(state="disabled", text="⚙️ ...", fg_color=COLORS["warning"])
            self.status_label.grid()
            self.progress_bar.grid_remove()
        elif status in (STATUS_DONE, STATUS_EXTRACTED):
            self.progress_bar.grid_remove()
            self.status_label.grid()
            self.action_button.configure(
                state="disabled",
                text="✅",
                fg_color=COLORS["btn_success"],
            )
        elif status == STATUS_ERROR:
            self.progress_bar.grid_remove()
            self.status_label.grid()
            has_installer = bool(self.download_result and self.download_result.installer_path and self.download_result.installer_path.exists())
            if has_installer:
                self.action_button.configure(
                    state="normal",
                    text=i18n.t("btn_install_admin"),
                    fg_color=COLORS["warning"],
                    hover_color="#d97706",
                )
            else:
                self.action_button.configure(
                    state="normal",
                    text=i18n.t("btn_download"),
                    fg_color=COLORS["btn_primary"],
                    hover_color=COLORS["btn_primary_hover"],
                )
        else:
            self.progress_bar.grid_remove()
            self.status_label.grid()
            self.action_button.configure(
                state="normal",
                text=i18n.t("btn_download"),
                fg_color=COLORS["btn_primary"],
                hover_color=COLORS["btn_primary_hover"],
            )

    def set_progress(self, percent: float):
        """Обновляет прогресс-бар."""
        if percent < 0:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.stop()
            self.progress_bar.set(percent / 100.0)

    def reset_to_idle(self):
        """Сбрасывает карточку в начальное состояние."""
        self.status = STATUS_IDLE
        self.download_result = None
        self.progress_bar.grid_remove()
        self.status_label.configure(text="", text_color=COLORS["text_dim"])
        self.status_label.grid()
        self.action_button.configure(
            state="normal",
            text=i18n.t("btn_download"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
        )

    def update_language(self, lang: str):
        """Обновляет все надписи карточки при смене языка."""
        desc = self.app.get_description(lang)
        notes = self.app.get_notes(lang)
        if notes:
            desc += f"  ⓘ {notes}"
        self.desc_label.configure(text=desc)

        # Режим установки
        was_silent = self.is_silent
        modes = [i18n.t("mode_interactive"), i18n.t("mode_silent")]
        self.mode_menu.configure(values=modes)
        self.mode_var.set(modes[1] if was_silent else modes[0])

        # Кнопка действия
        if self.status == STATUS_IDLE:
            self.action_button.configure(text=i18n.t("btn_download"))
        elif self.status == STATUS_DOWNLOADED:
            if self.app.installer_type == "zip":
                self.action_button.configure(text=i18n.t("btn_extract"))
            else:
                self.action_button.configure(text=i18n.t("btn_install"))
        elif self.status == STATUS_ERROR:
            has_installer = bool(self.download_result and self.download_result.installer_path and self.download_result.installer_path.exists())
            self.action_button.configure(
                text=i18n.t("btn_install_admin") if has_installer else i18n.t("btn_download")
            )

        # Статус
        if self.status != STATUS_IDLE:
            emoji, i18n_key, color = _status_display(self.status)
            self.status_label.configure(text=f"{emoji} {i18n.t(i18n_key)}", text_color=color)


class ZiablWinSetupApp(ctk.CTk):
    """Главное окно ZiablWinSetup."""

    def __init__(self):
        super().__init__()

        self.title(i18n.t("app_title"))
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=COLORS["bg_window"])

        # Установка иконки
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # Состояние
        self.app_cards: dict[str, AppCard] = {}
        self.current_category = "all"
        self.is_downloading = False
        self.message_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.downloader = Downloader()
        self.extract_path = get_desktop_path()
        self.installer = Installer(extract_path=self.extract_path)

        # Разделитель: состояние перетаскивания
        self._splitter_dragging = False
        self._splitter_start_x = 0
        self._splitter_start_width = 240

        # Winget
        self.winget_available = check_winget()
        self.winget_version = get_winget_version() if self.winget_available else None

        # Строим интерфейс
        self._build_ui()
        self._process_queue()

        # Адаптивный расчёт геометрии окна с учётом DPI-масштабирования
        self.update_idletasks()
        try:
            scaling = self._get_window_scaling()
        except Exception:
            scaling = 1.0

        screen_w = max(self.winfo_screenwidth(), 800)
        screen_h = max(self.winfo_screenheight(), 600)

        logical_screen_w = screen_w / scaling
        logical_screen_h = screen_h / scaling

        w = int(min(1150, max(750, logical_screen_w * 0.88)))
        h = int(min(750, max(520, logical_screen_h * 0.82)))

        physical_w = int(w * scaling)
        physical_h = int(h * scaling)

        x = max(10, (screen_w - physical_w) // 2)
        y = max(10, (screen_h - physical_h) // 2)

        self.minsize(min(w, 720), min(h, 480))
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Выводим окно поверх остальных при запуске
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_content()
        self._build_footer()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_header"], corner_radius=0, height=72)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        # Логотип и заголовок
        left_frame = ctk.CTkFrame(header, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        title = ctk.CTkLabel(
            left_frame,
            text="🚀 ZiablWinSetup",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        title.pack(anchor="w")

        subtitle_text = i18n.t("app_subtitle")
        if self.winget_available:
            subtitle_text += f"  •  {i18n.t('winget_found')} {self.winget_version}"
        else:
            subtitle_text += f"  •  {i18n.t('winget_not_found')}"

        self.subtitle_label = ctk.CTkLabel(
            left_frame,
            text=subtitle_text,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"],
        )
        self.subtitle_label.pack(anchor="w")

        # Правая часть шапки: язык + поиск
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.grid(row=0, column=1, padx=20, pady=10, sticky="e")

        self.lang_button = ctk.CTkButton(
            right_frame,
            text="🌐 RU / EN",
            width=100,
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["btn_secondary"],
            hover_color=COLORS["btn_secondary_hover"],
            text_color=COLORS["text_primary"],
            command=self._toggle_language,
        )
        self.lang_button.pack(side="right", padx=(10, 0))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search)

        self.search_entry = ctk.CTkEntry(
            right_frame,
            placeholder_text=i18n.t("search_placeholder"),
            textvariable=self.search_var,
            width=260,
            height=36,
            corner_radius=6,
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
        )
        self.search_entry.pack(side="right")

    def _build_content(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)

        # 0: Сайдбар, 1: Сплиттер (разделитель), 2: Список приложений
        content.grid_columnconfigure(0, weight=0)
        content.grid_columnconfigure(1, weight=0)
        content.grid_columnconfigure(2, weight=1)

        self._build_sidebar(content)
        self._build_splitter(content)
        self._build_app_list(content)

    def _build_sidebar(self, parent):
        self.sidebar = ctk.CTkScrollableFrame(
            parent,
            fg_color=COLORS["bg_sidebar"],
            width=240,
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_light"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Заголовок категорий
        self.categories_header_label = ctk.CTkLabel(
            self.sidebar,
            text=i18n.t("categories"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_dim"],
        )
        self.categories_header_label.pack(padx=16, pady=(16, 8), anchor="w")

        from app.catalog import CATEGORIES
        self.category_buttons: dict[str, ctk.CTkButton] = {}

        for cat_id in CATEGORIES:
            count = len(get_apps_by_category(cat_id))
            cat_label = i18n.cat_name(cat_id)

            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{cat_label}  ({count})",
                anchor="w",
                height=38,
                corner_radius=6,
                font=ctk.CTkFont(size=12),
                fg_color=COLORS["btn_primary"] if cat_id == "all" else "transparent",
                hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_primary"],
                command=lambda c=cat_id: self._select_category(c),
            )
            btn.pack(padx=8, pady=2, fill="x")
            self.category_buttons[cat_id] = btn

        # Разделитель
        sep1 = ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"])
        sep1.pack(fill="x", padx=12, pady=12)

        # Быстрые действия
        self.quick_actions_header_label = ctk.CTkLabel(
            self.sidebar,
            text=i18n.t("quick_actions"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_dim"],
        )
        self.quick_actions_header_label.pack(padx=16, pady=(4, 8), anchor="w")

        self.quick_action_buttons: dict[str, ctk.CTkButton] = {}
        actions = [
            ("select_recommended", COLORS["warning"], self._select_recommended),
            ("select_all", COLORS["text_primary"], self._select_all),
            ("deselect_all", COLORS["text_secondary"], self._deselect_all),
            ("all_silent", COLORS["text_secondary"], lambda: self._set_all_mode("silent")),
            ("all_interactive", COLORS["text_secondary"], lambda: self._set_all_mode("interactive")),
        ]

        for key, color, cmd in actions:
            btn = ctk.CTkButton(
                self.sidebar,
                text=i18n.t(key),
                anchor="w",
                height=34,
                corner_radius=6,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color=COLORS["bg_card_hover"],
                text_color=color,
                command=cmd,
            )
            btn.pack(padx=8, pady=2, fill="x")
            self.quick_action_buttons[key] = btn

        # Разделитель
        sep2 = ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"])
        sep2.pack(fill="x", padx=12, pady=12)

        # Настройки
        self.settings_header_label = ctk.CTkLabel(
            self.sidebar,
            text=i18n.t("settings"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_dim"],
        )
        self.settings_header_label.pack(padx=16, pady=(4, 8), anchor="w")

        self.extract_path_header_label = ctk.CTkLabel(
            self.sidebar,
            text=i18n.t("extract_path_label"),
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"],
        )
        self.extract_path_header_label.pack(padx=16, pady=(0, 3), anchor="w")

        self.extract_path_label = ctk.CTkLabel(
            self.sidebar,
            text=str(self.extract_path),
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_primary"],
            wraplength=200,
            anchor="w",
            justify="left",
        )
        self.extract_path_label.pack(padx=16, pady=(0, 6), anchor="w")

        self.browse_button = ctk.CTkButton(
            self.sidebar,
            text=i18n.t("browse"),
            width=110,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["btn_secondary"],
            hover_color=COLORS["btn_secondary_hover"],
            text_color=COLORS["text_primary"],
            command=self._browse_extract_path,
        )
        self.browse_button.pack(padx=16, pady=(0, 16), anchor="w")

    def _build_splitter(self, parent):
        """Интерактивный перетаскиваемый разделитель между сайдбаром и списком приложений."""
        self.splitter = ctk.CTkFrame(
            parent,
            width=5,
            fg_color=COLORS["splitter"],
            corner_radius=0,
            cursor="size_we",
        )
        self.splitter.grid(row=0, column=1, sticky="ns")
        self.splitter.grid_propagate(False)

        # События мыши для перетаскивания
        self.splitter.bind("<Enter>", lambda e: self.splitter.configure(fg_color=COLORS["splitter_hover"]))
        self.splitter.bind("<Leave>", lambda e: self._on_splitter_leave())
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)

    def _on_splitter_press(self, event):
        self._splitter_dragging = True
        self._splitter_start_x = event.x_root
        self._splitter_start_width = self.sidebar.winfo_width()
        self.splitter.configure(fg_color=COLORS["splitter_hover"])

    def _on_splitter_drag(self, event):
        if not getattr(self, "_splitter_dragging", False):
            return
        dx = event.x_root - self._splitter_start_x
        new_width = max(180, min(420, self._splitter_start_width + dx))
        self.sidebar.configure(width=new_width)

    def _on_splitter_release(self, event):
        self._splitter_dragging = False
        self.splitter.configure(fg_color=COLORS["splitter"])

    def _on_splitter_leave(self):
        if not getattr(self, "_splitter_dragging", False):
            self.splitter.configure(fg_color=COLORS["splitter"])

    def _build_app_list(self, parent):
        self.app_list_frame = ctk.CTkScrollableFrame(
            parent,
            fg_color=COLORS["bg_window"],
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.app_list_frame.grid(row=0, column=2, sticky="nsew")
        self.app_list_frame.grid_columnconfigure(0, weight=1)

        # Оптимизация изменения размера (debounce), предотвращающая пикселизацию и лаги при растягивании окна
        resize_timer = [None]
        orig_fit = self.app_list_frame._fit_frame_dimensions_to_canvas

        def _debounced_fit(event):
            if resize_timer[0]:
                self.after_cancel(resize_timer[0])
            def _apply():
                orig_fit(event)
                resize_timer[0] = None
            resize_timer[0] = self.after(25, _apply)

        self.app_list_frame._parent_canvas.bind("<Configure>", _debounced_fit)

        # Мгновенный и отзывчивый скроллинг колесиком (~80px за деление, 1 карточка за шаг)
        def _fast_scroll(frame, event):
            if frame._check_if_valid_scroll(event.widget):
                if sys.platform.startswith("win"):
                    frame._parent_canvas.yview("scroll", -int(event.delta / 1.5), "units")

        self.app_list_frame._mouse_wheel_all = lambda event: _fast_scroll(self.app_list_frame, event)
        self.sidebar._mouse_wheel_all = lambda event: _fast_scroll(self.sidebar, event)

        # Создаём карточки приложений
        for idx, app in enumerate(get_catalog()):
            card = AppCard(
                self.app_list_frame,
                app,
                on_download_click=self._on_card_download,
                on_install_click=self._on_card_install,
                on_extract_click=self._on_card_extract,
                on_select_change=self._update_selected_count,
            )
            card.grid(row=idx, column=0, padx=12, pady=4, sticky="ew")
            self.app_cards[app.id] = card

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=COLORS["bg_header"], corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        # Панель кнопок и статуса
        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
        btn_row.grid_columnconfigure(1, weight=1)

        # Счётчик выбранных
        self.selected_count_label = ctk.CTkLabel(
            btn_row,
            text=i18n.t("selected_count", count=0),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"],
        )
        self.selected_count_label.grid(row=0, column=0, sticky="w")

        # Общий статус
        self.overall_status_label = ctk.CTkLabel(
            btn_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
        )
        self.overall_status_label.grid(row=0, column=1, padx=20, sticky="e")

        # Кнопка "Установить все скачанные"
        self.install_all_button = ctk.CTkButton(
            btn_row,
            text=i18n.t("btn_install_all"),
            width=220,
            height=40,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["btn_success"],
            hover_color=COLORS["btn_success_hover"],
            text_color="white",
            command=self._on_install_all,
            state="disabled",
        )
        self.install_all_button.grid(row=0, column=2, padx=(6, 6), sticky="e")

        # Кнопка "Скачать выбранное"
        self.download_button = ctk.CTkButton(
            btn_row,
            text=i18n.t("btn_download_selected"),
            width=220,
            height=40,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
            text_color="white",
            command=self._on_download,
        )
        self.download_button.grid(row=0, column=3, padx=(6, 0), sticky="e")

        # Прогресс-бар общий
        self.overall_progress = ctk.CTkProgressBar(
            footer,
            height=6,
            corner_radius=3,
            fg_color=COLORS["progress_bg"],
            progress_color=COLORS["accent"],
        )
        self.overall_progress.set(0)
        self.overall_progress.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        # Лог событий
        self.log_text = ctk.CTkTextbox(
            footer,
            height=85,
            corner_radius=6,
            fg_color="#181818",
            text_color=COLORS["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
        )
        self.log_text.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        # Подписка на обновление счётчика
        self._update_selected_count()
        for card in self.app_cards.values():
            card.selected_var.trace_add("write", lambda *_: self._update_selected_count())

    # ==========================================
    # Действия пользователя
    # ==========================================

    def _select_category(self, category: str):
        self.current_category = category
        for cat_id, btn in self.category_buttons.items():
            if cat_id == category:
                btn.configure(
                    fg_color=COLORS["btn_primary"],
                    hover_color=COLORS["btn_primary_hover"],
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=COLORS["bg_card_hover"],
                )
        self._filter_cards()

    def _filter_cards(self):
        """Фильтрует карточки по категории и поисковому запросу с переупорядочиванием сетки."""
        search = self.search_var.get().lower().strip()
        cat = self.current_category
        visible_idx = 0

        for card in self.app_cards.values():
            show = True
            if cat != "all" and card.app.category != cat:
                show = False
            if search:
                name_m = card.app.name.lower()
                desc_ru = card.app.description.lower()
                desc_en = card.app.description_en.lower()
                id_m = card.app.id.lower()
                if search not in f"{name_m} {desc_ru} {desc_en} {id_m}":
                    show = False

            if show:
                card.grid(row=visible_idx, column=0, padx=12, pady=4, sticky="ew")
                visible_idx += 1
            else:
                card.grid_remove()

        # Всегда сбрасываем позицию прокрутки в самое начало
        try:
            self.app_list_frame._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _on_search(self, *_):
        self._filter_cards()

    def _select_recommended(self):
        rec_ids = {a.id for a in get_recommended()}
        for aid, card in self.app_cards.items():
            card.selected_var.set(aid in rec_ids)
            card._on_checkbox_toggle()

    def _select_all(self):
        for card in self.app_cards.values():
            if card.winfo_ismapped():
                card.selected_var.set(True)
                card._on_checkbox_toggle()

    def _deselect_all(self):
        for card in self.app_cards.values():
            card.selected_var.set(False)
            card._on_checkbox_toggle()

    def _set_all_mode(self, mode: str):
        val = i18n.t("mode_silent") if mode == "silent" else i18n.t("mode_interactive")
        for card in self.app_cards.values():
            card.mode_var.set(val)

    def _update_selected_count(self):
        count = sum(1 for c in self.app_cards.values() if c.is_selected)
        self.selected_count_label.configure(text=i18n.t("selected_count", count=count))

    def _browse_extract_path(self):
        path = filedialog.askdirectory(
            initialdir=str(self.extract_path),
            title="Выберите папку для распаковки ZIP / Select ZIP extraction folder",
        )
        if path:
            self.extract_path = Path(path)
            self.installer.extract_path = self.extract_path
            self.extract_path_label.configure(text=str(self.extract_path))

    def _toggle_language(self):
        """Полная динамическая смена языка интерфейса без перезапуска приложения."""
        new_lang = i18n.toggle()
        self.title(i18n.t("app_title"))

        # Подзаголовок в шапке
        subtitle_text = i18n.t("app_subtitle")
        if self.winget_available:
            subtitle_text += f"  •  {i18n.t('winget_found')} {self.winget_version}"
        else:
            subtitle_text += f"  •  {i18n.t('winget_not_found')}"
        self.subtitle_label.configure(text=subtitle_text)

        # Кнопка языка и поиск
        self.lang_button.configure(text="🌐 RU / EN")
        self.search_entry.configure(placeholder_text=i18n.t("search_placeholder"))

        # Заголовки сайдбара
        self.categories_header_label.configure(text=i18n.t("categories"))
        self.quick_actions_header_label.configure(text=i18n.t("quick_actions"))
        self.settings_header_label.configure(text=i18n.t("settings"))
        self.extract_path_header_label.configure(text=i18n.t("extract_path_label"))
        self.browse_button.configure(text=i18n.t("browse"))

        # Кнопки категорий
        for cat_id, btn in self.category_buttons.items():
            count = len(get_apps_by_category(cat_id))
            cat_label = i18n.cat_name(cat_id)
            btn.configure(text=f"{cat_label}  ({count})")

        # Кнопки быстрых действий
        for key, btn in self.quick_action_buttons.items():
            btn.configure(text=i18n.t(key))

        # Нижняя панель
        self.download_button.configure(
            text=i18n.t("btn_cancel") if self.is_downloading else i18n.t("btn_download_selected")
        )
        self.install_all_button.configure(text=i18n.t("btn_install_all"))
        self._update_selected_count()

        # Обновление всех карточек приложений
        for card in self.app_cards.values():
            card.update_language(new_lang)

    # ==========================================
    # Скачивание
    # ==========================================

    def _on_download(self):
        """Скачивает все выбранные приложения."""
        if self.is_downloading:
            self._cancel_download()
            return

        selected = [c for c in self.app_cards.values() if c.is_selected and c.status not in (STATUS_DOWNLOADED, STATUS_DONE, STATUS_EXTRACTED)]
        if not selected:
            self._log(i18n.t("log_no_selection"))
            return

        self.is_downloading = True
        self.downloader.reset()

        self.download_button.configure(
            text=i18n.t("btn_cancel"),
            fg_color=COLORS["btn_danger"],
            hover_color=COLORS["btn_danger_hover"],
        )

        for card in selected:
            card.set_status(STATUS_QUEUED)

        self._log(i18n.t("log_start_download", count=len(selected)))

        thread = threading.Thread(target=self._download_worker, args=(selected,), daemon=True)
        thread.start()

    def _cancel_download(self):
        self._log(i18n.t("log_cancelled"))
        self.downloader.cancel()
        self.is_downloading = False
        self.download_button.configure(
            text=i18n.t("btn_download_selected"),
            fg_color=COLORS["btn_primary"],
            hover_color=COLORS["btn_primary_hover"],
        )

    def _download_worker(self, cards: list[AppCard]):
        """Рабочий поток: параллельное скачивание."""
        total = len(cards)
        completed = 0

        def progress_cb(app_id: str, percent: float, status_text: str):
            self._queue_msg("app_progress", (app_id, percent, status_text))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for card in cards:
                self._queue_msg("app_status", (card.app.id, STATUS_DOWNLOADING))
                future = executor.submit(self.downloader.download, card.app, progress_cb)
                futures[future] = card

            for future in futures:
                card = futures[future]
                try:
                    result = future.result()
                    completed += 1

                    if result.success:
                        self._queue_msg("download_done", (card.app.id, result))
                        self._queue_msg("log", i18n.t("log_downloaded", name=card.app.name))
                    else:
                        self._queue_msg("app_status", (card.app.id, STATUS_ERROR, result.error))
                        self._queue_msg("log", i18n.t("log_download_error", name=card.app.name, error=result.error))

                    self._queue_msg("overall_progress", completed / total)
                    self._queue_msg("overall_status", i18n.t("downloading_progress", done=completed, total=total))

                except Exception as e:
                    completed += 1
                    self._queue_msg("app_status", (card.app.id, STATUS_ERROR, str(e)))
                    self._queue_msg("log", i18n.t("log_download_error", name=card.app.name, error=str(e)))

        self._queue_msg("log", i18n.t("log_download_done"))
        self._queue_msg("download_phase_done", None)

    # ==========================================
    # Одиночное скачивание по кнопке на карточке
    # ==========================================

    def _on_card_download(self, card: AppCard):
        """Скачивание одного приложения по кнопке на карточке."""
        if card.status == STATUS_DOWNLOADING:
            return

        card.set_status(STATUS_DOWNLOADING)
        self._log(f"📥 {card.app.name}: {i18n.t('status_downloading')}...")

        thread = threading.Thread(
            target=self._download_single_worker,
            args=(card,),
            daemon=True,
        )
        thread.start()

    def _download_single_worker(self, card: AppCard):
        """Рабочий поток одиночного скачивания."""
        def progress_cb(app_id: str, percent: float, status_text: str):
            self._queue_msg("app_progress", (app_id, percent, status_text))

        try:
            result = self.downloader.download(card.app, progress_cb)
            if result.success:
                self._queue_msg("download_done", (card.app.id, result))
                self._queue_msg("log", i18n.t("log_downloaded", name=card.app.name))
                self._queue_msg("enable_install_all", None)
            else:
                self._queue_msg("app_status", (card.app.id, STATUS_ERROR, result.error))
                self._queue_msg("log", i18n.t("log_download_error", name=card.app.name, error=result.error))
        except Exception as e:
            self._queue_msg("app_status", (card.app.id, STATUS_ERROR, str(e)))
            self._queue_msg("log", i18n.t("log_download_error", name=card.app.name, error=str(e)))

    # ==========================================
    # Установка
    # ==========================================

    def _on_card_install(self, card: AppCard, as_admin: bool = False):
        """Установка одного приложения по кнопке на карточке."""
        if not card.download_result or not card.download_result.installer_path:
            return

        card.set_status(STATUS_INSTALLING)
        admin_tag = " 🛡️ (Администратор)" if as_admin else ""
        self._log(f"{i18n.t('log_start_install', name=card.app.name)}{admin_tag}")

        thread = threading.Thread(
            target=self._install_single_worker,
            args=(card, as_admin),
            daemon=True,
        )
        thread.start()

    def _on_card_extract(self, card: AppCard):
        """Распаковка ZIP по кнопке на карточке."""
        if not card.download_result or not card.download_result.installer_path:
            return

        card.set_status(STATUS_INSTALLING)
        thread = threading.Thread(
            target=self._install_single_worker,
            args=(card, False),
            daemon=True,
        )
        thread.start()

    def _install_single_worker(self, card: AppCard, as_admin: bool = False):
        """Установка или распаковка одного приложения в отдельном потоке."""
        result = self.installer.run(
            card.app,
            card.download_result.installer_path,
            silent=card.is_silent,
            as_admin=as_admin,
        )

        if result.success:
            if card.app.installer_type == "zip":
                self._queue_msg("app_status", (card.app.id, STATUS_EXTRACTED, result.error))
                self._queue_msg("log", i18n.t("log_extracted", name=card.app.name, path=result.error))
            else:
                self._queue_msg("app_status", (card.app.id, STATUS_DONE, ""))
                self._queue_msg("log", i18n.t("log_installed", name=card.app.name))
        else:
            self._queue_msg("app_status", (card.app.id, STATUS_ERROR, result.error))
            self._queue_msg("log", i18n.t("log_install_error", name=card.app.name, error=result.error))

    def _on_install_all(self):
        """Устанавливает все скачанные приложения по очереди."""
        downloaded = [c for c in self.app_cards.values() if c.status == STATUS_DOWNLOADED]
        if not downloaded:
            return

        self.install_all_button.configure(state="disabled")

        thread = threading.Thread(
            target=self._install_all_worker,
            args=(downloaded,),
            daemon=True,
        )
        thread.start()

    def _install_all_worker(self, cards: list[AppCard]):
        """Последовательная установка всех скачанных приложений."""
        total = len(cards)
        self._queue_msg("log", f"\n⚙️ {i18n.t('installing_progress', done=0, total=total)}")

        for idx, card in enumerate(cards):
            if not card.download_result or not card.download_result.installer_path:
                continue

            self._queue_msg("app_status", (card.app.id, STATUS_INSTALLING))
            self._queue_msg("log", i18n.t("log_start_install", name=card.app.name))
            self._queue_msg("overall_status", i18n.t("installing_progress", done=idx, total=total))

            result = self.installer.run(
                card.app,
                card.download_result.installer_path,
                silent=card.is_silent,
            )

            if result.success:
                if card.app.installer_type == "zip":
                    self._queue_msg("app_status", (card.app.id, STATUS_EXTRACTED, result.error))
                    self._queue_msg("log", i18n.t("log_extracted", name=card.app.name, path=result.error))
                else:
                    self._queue_msg("app_status", (card.app.id, STATUS_DONE, ""))
                    self._queue_msg("log", i18n.t("log_installed", name=card.app.name))
            else:
                self._queue_msg("app_status", (card.app.id, STATUS_ERROR, result.error))
                self._queue_msg("log", i18n.t("log_install_error", name=card.app.name, error=result.error))

            self._queue_msg("overall_progress", (idx + 1) / total)

        self._queue_msg("log", i18n.t("log_all_done"))
        self._queue_msg("install_all_done", None)

    # ==========================================
    # Очередь сообщений GUI ↔ потоки
    # ==========================================

    def _queue_msg(self, msg_type: str, data: Any):
        self.message_queue.put((msg_type, data))

    def _process_queue(self):
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == "log":
                    self._log(data)

                elif msg_type == "app_status":
                    app_id, status = data[0], data[1]
                    detail = data[2] if len(data) > 2 else ""
                    if app_id in self.app_cards:
                        self.app_cards[app_id].set_status(status, detail)

                elif msg_type == "app_progress":
                    app_id, percent, text = data
                    if app_id in self.app_cards:
                        self.app_cards[app_id].set_progress(percent)
                        self.app_cards[app_id].set_status(STATUS_DOWNLOADING, text)

                elif msg_type == "download_done":
                    app_id, result = data
                    if app_id in self.app_cards:
                        card = self.app_cards[app_id]
                        card.download_result = result
                        card.set_status(STATUS_DOWNLOADED)

                elif msg_type == "enable_install_all":
                    self.install_all_button.configure(state="normal")

                elif msg_type == "overall_progress":
                    self.overall_progress.set(data)

                elif msg_type == "overall_status":
                    self.overall_status_label.configure(text=data)

                elif msg_type == "download_phase_done":
                    self.is_downloading = False
                    self.download_button.configure(
                        text=i18n.t("btn_download_selected"),
                        fg_color=COLORS["btn_primary"],
                        hover_color=COLORS["btn_primary_hover"],
                    )
                    downloaded_count = sum(1 for c in self.app_cards.values() if c.status == STATUS_DOWNLOADED)
                    if downloaded_count > 0:
                        self.install_all_button.configure(state="normal")
                    self.overall_status_label.configure(
                        text=i18n.t("downloaded_count", count=downloaded_count)
                    )

                elif msg_type == "install_all_done":
                    self.install_all_button.configure(state="disabled")
                    self.overall_status_label.configure(text=i18n.t("completed"))
                    self.overall_progress.set(1.0)

        except queue.Empty:
            pass

        self.after(100, self._process_queue)

    def _log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
