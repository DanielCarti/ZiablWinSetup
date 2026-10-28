"""
ZiablWinSetup — Модуль истории действий и отката (Undo / Timeline).
Сохраняет выполненные операции (твики, автозагрузка, Metro) и обеспечивает
их безопасный откат в один клик.
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("WinSetup")


def get_history_file_path() -> Path:
    """Возвращает путь к файлу истории действий в AppData."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "ZiablWinSetup"
    else:
        base = Path.home() / ".ziablwinsetup"
    base.mkdir(parents=True, exist_ok=True)
    return base / "action_history.json"


class ActionHistoryManager:
    """Управляет историей действий и механизмами отката."""

    MAX_HISTORY_ITEMS = 60

    def __init__(self):
        self.file_path = get_history_file_path()
        self._history: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f"Failed to load action history: {e}")
        return []

    def _save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._history[:self.MAX_HISTORY_ITEMS], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save action history: {e}")

    def record_action(
        self,
        action_type: str,
        title: str,
        title_en: str = "",
        details: str = "",
        revert_data: dict[str, Any] | None = None,
        can_undo: bool = True,
    ) -> str:
        """
        Записывает действие в историю.
        
        Args:
            action_type: 'tweak_toggle', 'startup_toggle', 'metro_remove', 'metro_restore', etc.
            title: Название действия на русском
            title_en: Название действия на английском
            details: Дополнительные детали
            revert_data: Данные, необходимые для выполнения обратного действия
            can_undo: Можно ли откатить это действие
        """
        action_id = f"act_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        entry = {
            "id": action_id,
            "timestamp": int(time.time()),
            "action_type": action_type,
            "title": title,
            "title_en": title_en or title,
            "details": details,
            "revert_data": revert_data or {},
            "can_undo": can_undo,
            "undone": False,
        }
        self._history.insert(0, entry)
        self._save()
        logger.info(f"Recorded action {action_id}: {title}")
        return action_id

    def get_history(self, limit: int = 40) -> list[dict[str, Any]]:
        """Возвращает список недавних действий."""
        return self._history[:limit]

    def mark_undone(self, action_id: str) -> bool:
        """Помечает действие как отмененное."""
        for item in self._history:
            if item.get("id") == action_id:
                item["undone"] = True
                item["can_undo"] = False
                self._save()
                return True
        return False

    def clear(self) -> bool:
        """Очищает историю действий."""
        self._history = []
        self._save()
        return True


# Глобальный синглтон менеджера истории
action_history = ActionHistoryManager()
