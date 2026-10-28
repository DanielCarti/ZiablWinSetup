"""
Tweaks & Maintenance API Mixin.
Управление системными твиками, фоновым мониторингом SFC/DISM и очисткой.
"""

import ctypes
import logging
import threading
import time
from typing import Any
from app.history import action_history
from app.i18n import i18n
from app.tweaks import (
    apply_tweak_by_id,
    get_all_tweaks,
    revert_tweak_by_id,
)

logger = logging.getLogger("WinSetup")


class TweaksApiMixin:
    """Миксин для управления твиками системы и фоновыми оптимизациями."""

    def get_tweaks(self) -> list[dict]:
        return get_all_tweaks(i18n.lang)

    def apply_tweak(self, tweak_id: str, record_history: bool = True) -> dict[str, Any]:
        res = apply_tweak_by_id(tweak_id, lang=i18n.lang)
        if tweak_id == "clean_winsetup_installers":
            if hasattr(self, "_downloaded_results"):
                self._downloaded_results.clear()
            if hasattr(self, "call_js"):
                self.call_js("onLog", f"🗑️ {res.get('message', '')}")
        elif tweak_id in ("repair_system_files", "restore_health_dism") and res.get("success"):
            self._start_tweak_status_monitor(tweak_id)
        if record_history and res.get("success"):
            action_history.record_action(
                action_type="tweak_apply",
                title=f"Применен твик: {tweak_id}",
                title_en=f"Applied tweak: {tweak_id}",
                revert_data={"tweak_id": tweak_id, "action": "revert"},
                can_undo=True,
            )
        return res

    def get_tweak_running_status(self, tweak_id: str) -> dict[str, Any]:
        """Возвращает текущий статус выполнения длительного твика для надежного фронтенд-поллинга."""
        running_tweaks = getattr(self, "_running_tweaks", {})
        return running_tweaks.get(tweak_id, {"running": False, "completed": False})

    def _start_tweak_status_monitor(self, tweak_id: str) -> None:
        """Запускает фоновый поток мониторинга выполнения sfc /scannow или DISM RestoreHealth."""
        from app.tweaks import (
            TWEAKS,
            get_dism_status_file,
            get_sfc_status_file,
            get_tweak_process_handle,
            set_tweak_process_handle,
        )

        status_file = get_sfc_status_file() if tweak_id == "repair_system_files" else get_dism_status_file()
        tweak_name = "sfc" if tweak_id == "repair_system_files" else "dism"

        if not hasattr(self, "_running_tweaks"):
            self._running_tweaks = {}

        self._running_tweaks[tweak_id] = {
            "running": True,
            "completed": False,
            "id": tweak_id,
            "message": "Консоль запущена...",
        }

        def monitor():
            time.sleep(2)
            handle = get_tweak_process_handle(tweak_name)

            for _ in range(1800):  # До 30 минут
                time.sleep(1)

                # 1. Проверяем файл статуса
                if status_file.exists():
                    try:
                        content = status_file.read_text(encoding="utf-8").strip()
                        if content.startswith(("SUCCESS", "REPAIRED", "ERROR", "COMPLETED")):
                            if tweak_id == "repair_system_files":
                                if "SUCCESS" in content:
                                    msg_ru = "✅ Сканирование sfc /scannow завершено: повреждений целостности не обнаружено."
                                    msg_en = "✅ sfc /scannow scan complete: no integrity violations found."
                                else:
                                    msg_ru = "✅ Сканирование sfc /scannow завершено: поврежденные системные файлы восстановлены."
                                    msg_en = "✅ sfc /scannow scan complete: corrupted system files were repaired."
                            else:
                                if "SUCCESS" in content:
                                    msg_ru = "✅ Восстановление хранилища компонентов DISM успешно завершено."
                                    msg_en = "✅ DISM component store restore completed successfully."
                                else:
                                    msg_ru = "⚠️ Восстановление DISM завершено. Проверьте журнал CBS/DISM."
                                    msg_en = "⚠️ DISM restore completed. Check CBS/DISM logs."

                            res_data = {
                                "id": tweak_id,
                                "running": False,
                                "completed": True,
                                "success": True,
                                "message": msg_en if i18n.lang == "en" else msg_ru,
                                "message_ru": msg_ru,
                                "message_en": msg_en,
                            }
                            self._running_tweaks[tweak_id] = res_data

                            for t in TWEAKS:
                                if t.id == tweak_id:
                                    t.last_result = res_data["message"]
                                    t.last_result_ru = msg_ru
                                    t.last_result_en = msg_en

                            if hasattr(self, "call_js"):
                                self.call_js("onTweakCompleted", res_data)
                            try:
                                status_file.unlink(missing_ok=True)
                            except Exception:
                                pass
                            if handle:
                                try:
                                    ctypes.windll.kernel32.CloseHandle(handle)
                                except Exception:
                                    pass
                                set_tweak_process_handle(tweak_name, None)
                            return
                    except Exception as e:
                        logger.debug(f"Status file read error: {e}")

                # 2. Проверяем статус процесса через Windows Handle
                if handle:
                    try:
                        wait_code = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                        if wait_code == 0:  # Процесс завершился / окно закрыто
                            time.sleep(1)
                            if status_file.exists():
                                continue
                            msg_ru = "⚠️ Консоль была закрыта пользователем до завершения."
                            msg_en = "⚠️ Console was closed by user before completion."
                            res_data = {
                                "id": tweak_id,
                                "running": False,
                                "completed": True,
                                "success": False,
                                "message": msg_en if i18n.lang == "en" else msg_ru,
                                "message_ru": msg_ru,
                                "message_en": msg_en,
                            }
                            self._running_tweaks[tweak_id] = res_data
                            for t in TWEAKS:
                                if t.id == tweak_id:
                                    t.last_result = res_data["message"]
                                    t.last_result_ru = msg_ru
                                    t.last_result_en = msg_en
                            if hasattr(self, "call_js"):
                                self.call_js("onTweakCompleted", res_data)
                            try:
                                ctypes.windll.kernel32.CloseHandle(handle)
                            except Exception:
                                pass
                            set_tweak_process_handle(tweak_name, None)
                            return
                    except Exception as e:
                        logger.debug(f"Process handle wait error: {e}")

        threading.Thread(target=monitor, daemon=True).start()

    def revert_tweak(self, tweak_id: str, record_history: bool = True) -> dict[str, Any]:
        res = revert_tweak_by_id(tweak_id, lang=i18n.lang)
        if record_history and res.get("success"):
            action_history.record_action(
                action_type="tweak_revert",
                title=f"Откатан твик: {tweak_id}",
                title_en=f"Reverted tweak: {tweak_id}",
                revert_data={"tweak_id": tweak_id, "action": "apply"},
                can_undo=True,
            )
        return res
