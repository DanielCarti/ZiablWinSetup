"""
Health & Network API Mixin.
Мониторинг нагрузки CPU, RAM, диска C:, состояния системы, внешнего IP и сети.
"""

import ctypes
import json
import logging
import os
import shutil
import socket
import sys
import time
import urllib.request
from ctypes import wintypes
from typing import Any

logger = logging.getLogger("WinSetup")


class HealthApiMixin:
    """Миксин для мониторинга здоровья системы и сетевой информации."""

    def _get_cpu_usage(self) -> float:
        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        def ft_to_int(ft):
            return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            i = ft_to_int(idle)
            k = ft_to_int(kernel)
            u = ft_to_int(user)
            if not hasattr(self, "_last_sys_times") or not self._last_sys_times:
                self._last_sys_times = (i, k, u)
                return 0.0
            last_i, last_k, last_u = self._last_sys_times
            self._last_sys_times = (i, k, u)
            d_idle = i - last_i
            d_total = (k - last_k) + (u - last_u)
            if d_total > 0:
                cpu_load = max(0.0, min(100.0, ((d_total - d_idle) / d_total) * 100))
                return round(cpu_load, 1)
        return 0.0

    def _get_ram_usage(self) -> dict[str, Any]:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("sullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_gb = round(stat.ullTotalPhys / (1024**3), 1)
            avail_gb = round(stat.ullAvailPhys / (1024**3), 1)
            used_gb = round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3), 1)
            return {
                "percent": stat.dwMemoryLoad,
                "total_gb": total_gb,
                "used_gb": used_gb,
                "avail_gb": avail_gb,
            }
        return {"percent": 0, "total_gb": 0, "used_gb": 0, "avail_gb": 0}

    def _get_disk_c_usage(self) -> dict[str, Any]:
        try:
            total, used, free = shutil.disk_usage("C:\\")
            t_gb = round(total / (1024**3), 1)
            u_gb = round(used / (1024**3), 1)
            f_gb = round(free / (1024**3), 1)
            pct = round((used / total) * 100) if total > 0 else 0
            return {
                "total_gb": t_gb,
                "used_gb": u_gb,
                "free_gb": f_gb,
                "percent": pct,
            }
        except Exception:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}

    def get_system_health(self) -> dict[str, Any]:
        """Возвращает метрики загрузки CPU, RAM, диска C: и индекс здоровья системы."""
        try:
            cpu_pct = self._get_cpu_usage()
            ram_info = self._get_ram_usage()
            disk_info = self._get_disk_c_usage()

            score = 100
            issues = []
            if cpu_pct > 80:
                score -= 15
                issues.append("Высокая нагрузка CPU (>80%)")
            if ram_info["percent"] > 85:
                score -= 15
                issues.append("Оперативная память почти заполнена (>85%)")
            if disk_info["free_gb"] < 15:
                score -= 20
                issues.append("Мало места на диске C: (<15 GB)")

            status = "great" if score >= 85 else ("warning" if score >= 60 else "critical")

            return {
                "success": True,
                "cpu_percent": cpu_pct,
                "ram": ram_info,
                "disk": disk_info,
                "disk_c": disk_info,
                "ram_percent": ram_info.get("percent", 0),
                "ram_used_gb": ram_info.get("used_gb", 0),
                "ram_total_gb": ram_info.get("total_gb", 0),
                "score": max(0, score),
                "status": status,
                "issues": issues,
            }
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {"success": False, "error": str(e)}

    def get_network_ip_info(self) -> dict[str, Any]:
        """Возвращает внешний IP адрес, геолокацию, провайдера и код страны."""
        try:
            geo_data = {}
            for u in ["http://ip-api.com/json/?lang=ru", "https://ipwho.is/"]:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=3.5) as res:
                        geo_data = json.loads(res.read().decode("utf-8"))
                        if geo_data.get("status") == "success" or geo_data.get("success") is True or geo_data.get("ip") or geo_data.get("query"):
                            break
                except Exception:
                    continue

            ip = geo_data.get("query") or geo_data.get("ip") or ""
            if not ip:
                return {"success": False, "error": "Не удалось определить внешний IP (проверьте интернет)"}

            country = geo_data.get("country") or "Неизвестно"
            country_code = (geo_data.get("countryCode") or geo_data.get("country_code") or "").upper()
            city = geo_data.get("city") or ""
            isp = geo_data.get("isp") or geo_data.get("org") or ""

            flag = "🌐"
            if len(country_code) == 2:
                flag = "".join(chr(127397 + ord(c)) for c in country_code)

            latency_ms = None
            try:
                t0 = time.time()
                s = socket.create_connection(("ya.ru", 80), timeout=1.5)
                s.close()
                latency_ms = round((time.time() - t0) * 1000, 1)
            except Exception:
                pass

            return {
                "success": True,
                "ip": ip,
                "country": country,
                "country_code": country_code.lower(),
                "city": city,
                "isp": isp,
                "flag": flag,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            logger.error(f"Network info check failed: {e}")
            return {"success": False, "error": str(e)}
