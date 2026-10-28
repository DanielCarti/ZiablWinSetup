"""
History & Undo API Mixin.
Хранение и откат действий (Timeline Undo) для твиков, автозапуска и Metro приложений.
"""

import logging
from typing import Any
from app.history import action_history

logger = logging.getLogger("WinSetup")


class HistoryApiMixin:
    """Миксин для управления историей действий и откатом (Undo)."""

    def get_action_history(self) -> list[dict[str, Any]]:
        """Возвращает список недавних действий для UI."""
        return action_history.get_history(40)

    def undo_action(self, action_id: str) -> dict[str, Any]:
        """Откатывает действие из истории."""
        for item in action_history.get_history(100):
            if item.get("id") == action_id:
                if item.get("undone"):
                    return {"success": False, "error": "Действие уже было отменено"}
                revert_data = item.get("revert_data", {})
                act_type = item.get("action_type")

                if act_type == "tweak_apply":
                    res = self.revert_tweak(revert_data.get("tweak_id"), record_history=False)
                elif act_type == "tweak_revert":
                    res = self.apply_tweak(revert_data.get("tweak_id"), record_history=False)
                elif act_type == "metro_remove":
                    res = self.restore_metro_app(revert_data.get("metro_id"), record_history=False)
                elif act_type == "metro_restore":
                    res = self.remove_metro_app(revert_data.get("metro_id"), record_history=False)
                elif act_type == "startup_toggle":
                    res = self.toggle_startup_item(revert_data.get("item_id"), revert_data.get("enable"), record_history=False)
                else:
                    return {"success": False, "error": "Неизвестный тип отката"}

                if res.get("success"):
                    action_history.mark_undone(action_id)
                    if hasattr(self, "call_js"):
                        self.call_js("onLog", f"↩️ Успешно отменено действие: {item.get('title')}")
                return res
        return {"success": False, "error": "Действие не найдено в истории"}

    def undo_last_action(self) -> dict[str, Any]:
        """Откатывает последнее выполненное действие."""
        for item in action_history.get_history(100):
            if item.get("can_undo") and not item.get("undone"):
                return self.undo_action(item.get("id"))
        return {"success": False, "error": "Нет доступных действий для отмены"}

    def clear_action_history(self) -> dict[str, Any]:
        """Очищает историю действий."""
        success = action_history.clear()
        return {"success": success}
