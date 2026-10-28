"""
AI Assistant API Mixin.
Интерактивный помощник по оптимизации Windows, твикам и безопасности.
"""

import logging
import sys
from typing import Any
from app.ai_assistant import ai_assistant

logger = logging.getLogger("WinSetup")


class AiApiMixin:
    """Миксин для взаимодействия с ИИ-ассистентом."""

    def get_ai_config(self) -> dict[str, Any]:
        """Возвращает текущие настройки ИИ-ассистента."""
        return ai_assistant.get_config()

    def save_ai_config(self, provider: str, api_key: str, model: str = "") -> dict[str, Any]:
        """Сохраняет настройки провайдера и ключ ИИ-ассистента."""
        success = ai_assistant.save_config(provider, api_key, model)
        return {"success": success}

    def ask_ai_assistant(self, prompt: str) -> dict[str, Any]:
        """Отправляет вопрос ИИ-ассистенту с системным контекстом."""
        try:
            ram = self._get_ram_usage() if hasattr(self, "_get_ram_usage") else {}
            disk = self._get_disk_c_usage() if hasattr(self, "_get_disk_c_usage") else {}
            context = {
                "os": "Windows 11" if sys.getwindowsversion().build >= 22000 else "Windows 10",
                "ram": f"{ram.get('used_gb', 0)}/{ram.get('total_gb', 0)} GB",
                "disk": f"{disk.get('free_gb', 0)} GB свободно",
            }
            return ai_assistant.ask(prompt, system_context=context)
        except Exception as e:
            logger.error(f"Error in ask_ai_assistant: {e}")
            return {"success": False, "error": str(e)}
