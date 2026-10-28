"""
ZiablWinSetup — Модульные API-миксины для AppBridge.
Позволяет разделить God-объект AppBridge на независимые специализированные модули.
"""

from app.api_mixins.health_api import HealthApiMixin
from app.api_mixins.tweaks_api import TweaksApiMixin
from app.api_mixins.metro_api import MetroApiMixin
from app.api_mixins.startup_api import StartupApiMixin
from app.api_mixins.history_api import HistoryApiMixin
from app.api_mixins.winget_api import WingetApiMixin
from app.api_mixins.ai_api import AiApiMixin

__all__ = [
    "HealthApiMixin",
    "TweaksApiMixin",
    "MetroApiMixin",
    "StartupApiMixin",
    "HistoryApiMixin",
    "WingetApiMixin",
    "AiApiMixin",
]
