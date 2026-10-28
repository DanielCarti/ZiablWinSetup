"""
Metro / UWP Apps API Mixin.
Управление системными Metro/UWP приложениями (удаление, пакетная деинсталляция, восстановление).
"""

import logging
from typing import Any
from app.i18n import i18n
from app.history import action_history
from app.metro import (
    get_all_metro_apps,
    remove_metro_app_by_id,
    restore_metro_app_by_id,
    remove_batch_metro,
    restore_batch_metro,
)

logger = logging.getLogger("WinSetup")


class MetroApiMixin:
    """Миксин для работы со встроенными Metro-приложениями Windows."""

    def get_metro_apps(self) -> list[dict[str, Any]]:
        """Возвращает список всех Metro приложений со статусом установки."""
        return get_all_metro_apps(i18n.lang)

    def remove_metro_app(self, app_id: str, record_history: bool = True) -> dict[str, Any]:
        """Удаляет одно Metro приложение."""
        res = remove_metro_app_by_id(app_id)
        if record_history and res.get("success"):
            action_history.record_action(
                action_type="metro_remove",
                title=f"Удалено Metro: {app_id}",
                title_en=f"Removed Metro: {app_id}",
                revert_data={"metro_id": app_id, "action": "restore"},
                can_undo=True,
            )
        return res

    def restore_metro_app(self, app_id: str, record_history: bool = True) -> dict[str, Any]:
        """Восстанавливает одно Metro приложение."""
        res = restore_metro_app_by_id(app_id)
        if record_history and res.get("success"):
            action_history.record_action(
                action_type="metro_restore",
                title=f"Восстановлено Metro: {app_id}",
                title_en=f"Restored Metro: {app_id}",
                revert_data={"metro_id": app_id, "action": "remove"},
                can_undo=True,
            )
        return res

    def remove_selected_metro(self, app_ids: list[str]) -> list[dict[str, Any]]:
        """Пакетное удаление выбранных Metro приложений."""
        return remove_batch_metro(app_ids)

    def restore_selected_metro(self, app_ids: list[str]) -> list[dict[str, Any]]:
        """Пакетное восстановление выбранных Metro приложений."""
        return restore_batch_metro(app_ids)
