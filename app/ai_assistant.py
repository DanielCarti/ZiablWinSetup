"""
ZiablWinSetup — Модуль ИИ-Ассистента (AI Assistant).
Интеллектуальный помощник по настройке Windows, анализу служб, твикам и безопасности.
Поддерживает Google Gemini API, OpenRouter, OpenAI, а также встроенную базу знаний.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("WinSetup")


def get_ai_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "ZiablWinSetup"
    else:
        base = Path.home() / ".ziablwinsetup"
    base.mkdir(parents=True, exist_ok=True)
    return base / "ai_config.json"


# Встроенная база знаний на случай отсутствия ключа или оффлайна
OFFLINE_KNOWLEDGE_BASE = [
    {
        "keywords": ["телеметри", "слежк", "шпион", "telemetry", "tracking", "privacy"],
        "answer": (
            "🛡️ **Оптимизация приватности и телеметрии Windows:**\n\n"
            "• **Что такое телеметрия?** Это фоновый сбор диагностических данных, истории ввода и активности, который нагружает диск и процессор службами `DiagTrack` (Connected User Experiences and Telemetry).\n"
            "• **Что рекомендуется отключить в ZiablWinSetup:**\n"
            "  1. *Отключить телеметрию и сбор данных* (вкладка «Твики» → «Конфиденциальность»).\n"
            "  2. *Отключить рекламный идентификатор (Advertising ID)*.\n"
            "  3. *Отключить службы DiagTrack и dmwappushservice*.\n"
            "• **Безопасность:** Отключение полностью безопасно, не ломает Windows Update и существенно снижает фоновую нагрузку на накопитель SSD/HDD."
        ),
    },
    {
        "keywords": ["игра", "игр", "fps", "задержк", "лаг", "фпс", "game", "gaming", "lag"],
        "answer": (
            "🎮 **Твики для максимального FPS и снижения задержек (Latency):**\n\n"
            "1. **Включить игровой режим (Game Mode)**: Приоритезирует ресурсы ЦП и видеокарты для активного игрового окна.\n"
            "2. **Отключить Xbox Game Bar**: Если не используете оверлей Win+G и запись клипов, отключите Game Bar — это освободит до 3-5% ресурсов GPU/CPU и снизит микрофризы.\n"
            "3. **Отключить алгоритм Nagle (TCP NoDelay)**: В твиках сети — снижает пинг в онлайн-играх за счет мгновенной отправки сетевых пакетов.\n"
            "4. **Отключить изоляцию ядра (VBS / Memory Integrity)**: В Windows 11 защита на основе виртуализации может отнимать до 5-15% FPS в процессорозависимых играх (CS2, Valorant, Cyberpunk 2077)."
        ),
    },
    {
        "keywords": ["автозагрузк", "startup", "автозапуск", "грузит", "медленн", "запуск", "boot"],
        "answer": (
            "⚡ **Оптимизация автозагрузки Windows:**\n\n"
            "• Перейдите во вкладку *«Автозапуск»* в верхнем меню ZiablWinSetup.\n"
            "• **Что безопасно отключить:**\n"
            "  - Лаунчеры игр (Steam, Epic Games, Riot, Battle.net) — запускайте их вручную при необходимости.\n"
            "  - Мессенджеры (Discord, Telegram, Skype) — если не нужны первые секунды после старта.\n"
            "  - Службы обновления Adobe, Spotify, Edge (они работают в фоне).\n"
            "• **Что лучше оставить:**\n"
            "  - Панели управления драйверами Realtek Audio, NVIDIA Control Panel / AMD Software.\n"
            "  - Службы антивирусной защиты."
        ),
    },
    {
        "keywords": ["диск", "очистк", "мусор", "кэш", "место", "clean", "disk", "c:"],
        "answer": (
            "🧹 **Как быстро освободить место на системном диске C:**\n\n"
            "1. **Очистка кэша инсталляторов в ZiablWinSetup**: Кнопка в меню настроек удаляет скачанные инсталляторы.\n"
            "2. **Wise Disk Cleaner**: Добавлен в каталог (категория «Утилиты») — безопасно очищает до 10-25 ГБ мусора Windows, системных дампов и кэша браузеров.\n"
            "3. **Удаление скрытого файла гибернации (hiberfil.sys)**: Если не пользуетесь гибернацией (только сном), команда `powercfg -h off` мгновенно освободит размер, равный объему оперативной памяти (16-32 ГБ).\n"
            "4. **Очистка хранилища WinSxS**: Выполните твик восстановления/очистки компонентов DISM в разделе «Твики».\n"
            "5. **Удаление встроенных Metro-приложений**: Вкладка «Metro Apps» позволяет удалить неиспользуемые предустановленные пакеты."
        ),
    },
    {
        "keywords": ["sysmain", "superfetch", "диск 100", "нагрузк"],
        "answer": (
            "⚙️ **Служба SysMain (Superfetch):**\n\n"
            "• **Для чего она нужна:** Предварительно загружает часто используемые программы в оперативную память.\n"
            "• **На SSD**: На современных быстрых NVMe/SATA SSD служба практически бесполезна и лишь производит постоянные фоновые циклы записи, изнашивая диск.\n"
            "• **На HDD**: Часто вызывает проблему «Загрузка диска 100%» после включения ПК.\n"
            "• **Рекомендация:** Отключение службы SysMain в твиках системы безопасно и снимает паразитную нагрузку на диск."
        ),
    },
    {
        "keywords": ["синий экран", "bsod", "краш", "вылет", "падение", "дамп", "dump"],
        "answer": (
            "🛠️ **Диагностика и устранение Синего экрана (BSOD):**\n\n"
            "1. **Проверка целостности системы:** Во вкладке «Твики» примените *«Восстановление системных файлов (SFC)»* или запустите от админа `sfc /scannow`.\n"
            "2. **Восстановление хранилища компонентов:** Примените твик *«Восстановление хранилища DISM»* (`DISM /Online /Cleanup-Image /RestoreHealth`).\n"
            "3. **Проверка оперативной памяти:** Запустите `mdsched.exe` (Средство проверки памяти Windows).\n"
            "4. **Анализ дампа памяти:** Установите утилиту *BlueScreenView* (доступна через поиск Winget) для определения конкретного сбойного драйвера (`.sys`)."
        ),
    },
    {
        "keywords": ["температур", "греется", "перегрев", "кулер", "шум", "троттлинг", "градус"],
        "answer": (
            "🌡️ **Снижение температуры и уровня шума процессора/видеокарты:**\n\n"
            "• **Нормы температур:** До 75-80°C под нагрузкой для CPU и до 70-75°C для GPU (Hotspot до 85-90°C) — это норма.\n"
            "• **Что сделать софтом:**\n"
            "  1. В плане электропитания ограничьте «Максимальное состояние процессора» до 99% — это отключит агрессивный буст и сбросит до 10-15°C на ноутбуках без потери плавности.\n"
            "  2. Используйте утилиты мониторинга из каталога (HWiNFO, AIDA64).\n"
            "• **Аппаратные меры:** Продувка радиаторов от пыли и замена термопасты раз в 1.5–2 года."
        ),
    },
    {
        "keywords": ["защитник", "defender", "антивирус", "smartscreen", "ложные"],
        "answer": (
            "🛡️ **Настройка Windows Defender (Защитника):**\n\n"
            "• **Влияние на скорость:** Встроенный антивирус сканирует каждый запускаемый exe-файл, что может вызывать задержки при запуске игр и тяжелых программ.\n"
            "• **Рекомендации:**\n"
            "  - Добавьте папки с играми (например, `C:\\Games` или папку Steam) в **Исключения Defender** (Защита от вирусов → Управление настройками → Исключения).\n"
            "  - Проверяйте подозрительные файлы через вкладку *VirusTotal* в нашем приложении (проверка по 70+ антивирусам одновременно)."
        ),
    },
    {
        "keywords": ["памят", "ram", "утечк", "озу", "не хватает памяти"],
        "answer": (
            "🧠 **Оптимизация оперативной памяти (RAM):**\n\n"
            "• **Кэш Standby List:** Windows кэширует прочитанные файлы в памяти. Если память забита, используйте утилиту Intelligent Standby List Cleaner (ISLC) или очистку в 1 клик через наш виджет здоровья системы.\n"
            "• **Файл подкачки (pagefile.sys):** Не отключайте его полностью даже при 32 ГБ RAM (многие игры требуют его наличия). Оптимально: фиксированный размер 4096-8192 МБ на самом быстром SSD."
        ),
    },
    {
        "keywords": ["youtube", "ютуб", "дискорд", "discord", "разблок", "запрет", "zapret", "byedpi"],
        "answer": (
            "🌐 **Разблокировка YouTube и Discord в России:**\n\n"
            "• В нашем каталоге программ есть готовые решения:\n"
            "  1. **Zapret** — мощная утилита обхода замедления TCP/UDP трафика на уровне сокетов Windows.\n"
            "  2. **Tg-WS Proxy / Opera Proxy** — прокси для мгновенного доступа к заблокированным ресурсам.\n"
            "  3. **YogaDNS** — перенаправление DNS-запросов через безопасный шифрованный DNS-over-HTTPS (DoH), исключающий подмену провайдером."
        ),
    },
    {
        "keywords": ["днс", "dns", "1.1.1.1", "8.8.8.8", "flushdns"],
        "answer": (
            "⚡ **Ускорение сетевого отклика и DNS:**\n\n"
            "• Провайдерские DNS часто работают медленно и фильтруют трафик.\n"
            "• **Рекомендуемые быстрые DNS:**\n"
            "  - **Cloudflare:** `1.1.1.1` и `1.0.0.1` (минимальный пинг в мире).\n"
            "  - **Google:** `8.8.8.8` и `8.8.4.4` (максимальная стабильность).\n"
            "  - **AdGuard DNS:** `94.140.14.14` (автоматическая блокировка рекламы на уровне сети).\n"
            "• Для сброса кэша DNS откройте CMD от админа и введите: `ipconfig /flushdns`."
        ),
    },
    {
        "keywords": ["питани", "энерго", "ultimate", "производительност", "powercfg"],
        "answer": (
            "🔋 **Схема «Максимальная производительность» (Ultimate Performance):**\n\n"
            "• Включает работу всех ядер процессора без микрозадержек перехода между состояниями C-states.\n"
            "• Включите твик *«Схема Максимальная производительность»* во вкладке «Твики».\n"
            "• Или активируйте через команду в CMD: `powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61`."
        ),
    },
    {
        "keywords": ["контекстн", "меню", "классическ", "меню 11", "win11 menu"],
        "answer": (
            "📋 **Классическое контекстное меню Windows 10 в Windows 11:**\n\n"
            "• В Windows 11 меню по правому клику скрывает большинство пунктов под кнопку «Показать дополнительные параметры».\n"
            "• Во вкладке «Твики» активируйте твик *«Классическое меню Windows 11»* — он возвращает полноценное и быстрое меню без сторонних утилит."
        ),
    },
    {
        "keywords": ["кортан", "cortana", "onedrive", "ван драйв"],
        "answer": (
            "🗑️ **Удаление OneDrive и Cortana:**\n\n"
            "• **OneDrive:** Перейдите во вкладку «Metro Apps» и нажмите «Удалить» рядом с OneDrive, либо воспользуйтесь системным удалением через раздел «Приложения».\n"
            "• **Cortana:** Во вкладке «Metro Apps» выберите Cortana и нажмите удалить — системный голосовой помощник будет безопасно отключен."
        ),
    },
]
class AIAssistant:
    """Менеджер обращений к ИИ-ассистенту."""

    def __init__(self):
        self.config_path = get_ai_config_path()
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        default_config = {
            "provider": "gemini",  # gemini, openrouter, openai, offline
            "api_key": "",
            "model": "gemini-1.5-flash",
            "temperature": 0.7,
        }
        if not self.config_path.exists():
            return default_config
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    default_config.update(data)
        except Exception as e:
            logger.warning(f"Error loading AI config: {e}")
        return default_config

    def save_config(self, provider: str, api_key: str, model: str = "") -> bool:
        self.config["provider"] = provider.strip()
        self.config["api_key"] = api_key.strip()
        if model:
            self.config["model"] = model.strip()
        elif provider.strip().lower() == "ollama":
            self.config["model"] = "llama3.2"
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving AI config: {e}")
            return False

    def get_config(self) -> dict[str, Any]:
        provider = self.config.get("provider", "gemini")
        key = self.config.get("api_key", "")
        masked_key = ""
        if key:
            masked_key = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
        elif provider == "ollama":
            masked_key = "Не требуется (Локальный сервер Ollama)"

        default_model = "llama3.2" if provider == "ollama" else "gemini-1.5-flash"
        return {
            "provider": provider,
            "has_key": bool(key) or provider == "ollama",
            "masked_key": masked_key,
            "model": self.config.get("model", default_model),
        }

    def ask(self, prompt: str, system_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Отправляет запрос ИИ или использует локальную базу знаний."""
        prompt_clean = prompt.strip()
        if not prompt_clean:
            return {"success": False, "error": "Пустой запрос"}

        api_key = self.config.get("api_key", "").strip()
        provider = self.config.get("provider", "gemini").lower()

        # Для Ollama ключ не требуется! Работает напрямую через локальный порт 11434
        if provider == "ollama":
            try:
                return self._call_ollama(prompt_clean, system_context)
            except Exception as e:
                logger.warning(f"Ollama call failed: {e}. Falling back to offline knowledge base.")
                offline_res = self._answer_from_offline_db(prompt_clean)
                offline_res["note"] = (
                    f"⚠️ Локальный сервис Ollama не отвечает ({e}).\n"
                    "Для использования локальной нейросети без ключей запустите Ollama (`ollama run llama3.2`)."
                )
                return offline_res

        # Если ключа нет — используем локальную базу знаний
        if not api_key:
            return self._answer_from_offline_db(prompt_clean)

        # Вызов внешнего API
        try:
            if provider == "gemini":
                return self._call_gemini(prompt_clean, api_key, system_context)
            elif provider == "openrouter":
                return self._call_openrouter(prompt_clean, api_key, system_context)
            elif provider == "openai":
                return self._call_openai(prompt_clean, api_key, system_context)
            else:
                return self._answer_from_offline_db(prompt_clean)
        except Exception as e:
            logger.warning(f"AI API call failed: {e}. Falling back to offline knowledge base.")
            offline_res = self._answer_from_offline_db(prompt_clean)
            offline_res["note"] = f"Внешний API недоступен ({e}). Показан локальный ответ."
            return offline_res

    def _answer_from_offline_db(self, prompt: str) -> dict[str, Any]:
        p_lower = prompt.lower()
        for item in OFFLINE_KNOWLEDGE_BASE:
            for kw in item["keywords"]:
                if kw in p_lower:
                    return {
                        "success": True,
                        "provider": "offline",
                        "answer": item["answer"],
                        "offline": True,
                    }

        # Дефолтный дружелюбный ответ о возможностях
        return {
            "success": True,
            "provider": "offline",
            "offline": True,
            "answer": (
                "🤖 **Ziabl AI Ассистент готов помочь!**\n\n"
                "Вы можете спросить меня о:\n"
                "• 🚀 **Ускорении игр и Windows** (оптимизация задержек, Nagle, Game Mode)\n"
                "• 🛡️ **Конфиденциальности и телеметрии** (какие твики безопасны)\n"
                "• ⚡ **Автозагрузке** (что можно отключить без риска)\n"
                "• 🧹 **Очистке диска C:** (кэш, дампы, гибернация)\n\n"
                "💡 *Совет:* Для получения развернутых ответов на любые нестандартные вопросы подключите бесплатный ключ **Google Gemini API** или **OpenRouter** в настройках ассистента."
            ),
        }

    def _build_system_instruction(self, system_context: dict[str, Any] | None = None) -> str:
        ctx_str = ""
        if system_context:
            ctx_str = (
                f"\nКонтекст системы пользователя: OS: {system_context.get('os', 'Windows 11')}, "
                f"RAM: {system_context.get('ram', 'N/A')}, "
                f"Диск C: {system_context.get('disk', 'N/A')} свободно."
            )
        return (
            "Ты — встроенный интеллектуальный ИИ-ассистент системной утилиты ZiablWinSetup для Windows 10/11. "
            "Твоя задача — профессионально, лаконично и понятно объяснять пользователю настройки Windows, "
            "безопасность твиков реестра, оптимизацию служб автозагрузки, очистку диска и работу с программами. "
            "Отвечай структурированно, с пунктами и эмодзи. Не рекомендуй сторонние твикеры или вредоносные скрипты. "
            f"Всегда учитывай безопасность системы.{ctx_str}"
        )

    def _call_gemini(self, prompt: str, api_key: str, context: dict[str, Any] | None) -> dict[str, Any]:
        model = self.config.get("model") or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        sys_inst = self._build_system_instruction(context)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{sys_inst}\n\nВопрос пользователя: {prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))

        candidates = res_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return {
                    "success": True,
                    "provider": "gemini",
                    "model": model,
                    "answer": parts[0].get("text", "").strip(),
                }

        return {"success": False, "error": "Не удалось получить ответ от Gemini API"}

    def _call_openrouter(self, prompt: str, api_key: str, context: dict[str, Any] | None) -> dict[str, Any]:
        model = self.config.get("model") or "meta-llama/llama-3.1-8b-instruct:free"
        url = "https://openrouter.ai/api/v1/chat/completions"
        sys_inst = self._build_system_instruction(context)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_inst},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/DanielCarti/ZiablWinSetup",
                "X-Title": "ZiablWinSetup",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))

        choices = res_data.get("choices", [])
        if choices:
            answer = choices[0].get("message", {}).get("content", "").strip()
            return {
                "success": True,
                "provider": "openrouter",
                "model": model,
                "answer": answer,
            }

        return {"success": False, "error": "Не удалось получить ответ от OpenRouter API"}

    def _call_openai(self, prompt: str, api_key: str, context: dict[str, Any] | None) -> dict[str, Any]:
        model = self.config.get("model") or "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"
        sys_inst = self._build_system_instruction(context)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_inst},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))

        choices = res_data.get("choices", [])
        if choices:
            answer = choices[0].get("message", {}).get("content", "").strip()
            return {
                "success": True,
                "provider": "openai",
                "model": model,
                "answer": answer,
            }

        return {"success": False, "error": "Не удалось получить ответ от OpenAI API"}


    def _call_ollama(self, prompt: str, context: dict[str, Any] | None) -> dict[str, Any]:
        model = self.config.get("model") or "llama3.2"
        url = "http://127.0.0.1:11434/api/chat"
        sys_inst = self._build_system_instruction(context)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_inst},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as res:
            res_data = json.loads(res.read().decode("utf-8"))

        msg = res_data.get("message", {})
        answer = msg.get("content", "").strip()
        if answer:
            return {
                "success": True,
                "provider": "ollama",
                "model": model,
                "answer": answer,
            }

        return {"success": False, "error": "Не удалось получить ответ от Ollama"}


ai_assistant = AIAssistant()
